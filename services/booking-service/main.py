import sys
import os
import time
import random
import string

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from shared.health import check_db, check_redis
import httpx
import pybreaker
from shared.config import BaseConfig
from shared.database import create_db_engine, create_session_factory, Base
from shared.auth import get_current_user
from shared.events import EventPublisher
from shared.resilience import create_circuit_breaker, async_retry
from shared.cache import create_redis_client, redis_get_json, redis_set_json, redis_delete, redis_set_nx
import structlog
from shared.logging import setup_logging
from shared.tracing import TraceMiddleware
from shared.schemas import HealthResponse
from models import Booking, BookingStatus
from schemas import BookingCreate, BookingResponse, BookingStatusUpdate, SeatAvailabilityResponse

config = BaseConfig(service_name="booking-service")
setup_logging(config.service_name)
logger = structlog.get_logger()

engine = create_db_engine(config.database_url)
SessionFactory = create_session_factory(engine)
START_TIME = time.time()

redis_client = create_redis_client(config.redis_url)

SEAT_LOCK_TTL    = 15   # seconds — long enough to complete the HTTP + DB round-trip
BOOKINGS_LIST_TTL = 60  # seconds — short enough to feel live

flight_breaker = create_circuit_breaker("flight-service")
payment_breaker = create_circuit_breaker("payment-service")

event_publisher = None
try:
    event_publisher = EventPublisher(
        endpoint_url=config.aws_endpoint_url, region=config.aws_region,
        bus_name=config.event_bus_name,
    )
except Exception:
    pass


def generate_booking_ref() -> str:
    return "AL" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


async def get_db():
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _to_response(b: Booking) -> BookingResponse:
    return BookingResponse(
        id=str(b.id), booking_reference=b.booking_reference, user_id=str(b.user_id),
        flight_id=str(b.flight_id), passenger_name=b.passenger_name,
        passenger_email=b.passenger_email, cabin_class=b.cabin_class,
        num_passengers=b.num_passengers, total_price=b.total_price,
        status=b.status.value, payment_id=str(b.payment_id) if b.payment_id else None,
        seat_numbers=b.seat_numbers, special_requests=b.special_requests,
        trip_type=b.trip_type,
        group_booking_id=str(b.group_booking_id) if b.group_booking_id else None,
        created_at=b.created_at,
        title=b.title, gender=b.gender,
        first_name=b.first_name, middle_name=b.middle_name, last_name=b.last_name,
        date_of_birth=b.date_of_birth, nationality=b.nationality,
        passport_number=b.passport_number, passport_expiry=b.passport_expiry,
        country_code=b.country_code, phone_number=b.phone_number,
    )


_MIGRATION_QUERIES = [
    "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS title VARCHAR(20)",
    "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS gender VARCHAR(10)",
    "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS first_name VARCHAR(100)",
    "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS middle_name VARCHAR(100)",
    "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS last_name VARCHAR(100)",
    "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS date_of_birth DATE",
    "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS nationality VARCHAR(100)",
    "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS passport_number VARCHAR(50)",
    "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS passport_expiry DATE",
    "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS country_code VARCHAR(10)",
    "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS phone_number VARCHAR(30)",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        try:
            await conn.run_sync(Base.metadata.create_all)
        except Exception:
            pass
        for q in _MIGRATION_QUERIES:
            try:
                await conn.execute(text(q))
            except Exception:
                pass
    yield
    await engine.dispose()


app = FastAPI(title="AeroLink Booking Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(TraceMiddleware)


# ── Protected inter-service helpers ─────────────────────────────────────────

async def _flight_get(flight_id: str) -> dict:
    """GET flight with retry; raises on network failure so breaker tracks it."""
    async for attempt in async_retry():
        with attempt:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{config.flight_service_url}/api/v1/flights/{flight_id}")
                resp.raise_for_status()
                return resp.json()


async def _flight_update_seats(flight_id: str, cabin_class: str, change: int) -> None:
    async for attempt in async_retry():
        with attempt:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.put(
                    f"{config.flight_service_url}/api/v1/flights/{flight_id}/seats",
                    json={"cabin_class": cabin_class, "change": change},
                )
                if resp.status_code == 409:
                    raise HTTPException(409, "Seats no longer available (concurrent booking)")
                resp.raise_for_status()


@app.get("/health", response_model=HealthResponse)
async def health(db: AsyncSession = Depends(get_db)):
    return HealthResponse(service="booking-service", uptime_seconds=time.time() - START_TIME,
                          dependencies={"database": await check_db(db),
                                        "redis": check_redis(redis_client)})


@app.post("/api/v1/bookings", response_model=BookingResponse, status_code=201)
async def create_booking(data: BookingCreate,
                         current_user: dict = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    # Distributed seat lock: prevent double-booking the same flight+cabin concurrently
    lock_key = f"seat_lock:{data.flight_id}:{data.cabin_class}"
    acquired = redis_set_nx(redis_client, lock_key, current_user["sub"], SEAT_LOCK_TTL)
    if not acquired:
        raise HTTPException(status_code=409, detail="Seat reservation in progress for this flight. Please try again.")

    try:
        # Step 1: Check flight availability (circuit breaker + retry)
        try:
            flight = await flight_breaker.call_async(_flight_get, data.flight_id)
        except pybreaker.CircuitBreakerError:
            raise HTTPException(status_code=503, detail="Flight service temporarily unavailable")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise HTTPException(status_code=404, detail="Flight not found")
            raise HTTPException(status_code=502, detail="Flight service error")

        available_key = f"available_seats_{data.cabin_class}"
        if flight.get(available_key, 0) < data.num_passengers:
            raise HTTPException(status_code=409, detail=f"Not enough {data.cabin_class} seats available")

        # Step 2: Reserve seats (circuit breaker + retry)
        price_key = f"price_{data.cabin_class}"
        total_price = flight.get(price_key, 0) * data.num_passengers

        try:
            await flight_breaker.call_async(
                _flight_update_seats, data.flight_id, data.cabin_class, -data.num_passengers
            )
        except pybreaker.CircuitBreakerError:
            raise HTTPException(status_code=503, detail="Flight service temporarily unavailable")

        # Step 3: Create booking record
        import uuid as _uuid
        group_id = _uuid.UUID(data.group_booking_id) if data.group_booking_id else None
        booking = Booking(
            booking_reference=generate_booking_ref(),
            user_id=current_user["sub"],
            flight_id=data.flight_id,
            passenger_name=data.passenger_name,
            passenger_email=data.passenger_email,
            cabin_class=data.cabin_class,
            num_passengers=data.num_passengers,
            total_price=total_price,
            status=BookingStatus.PENDING,
            special_requests=data.special_requests,
            trip_type=data.trip_type,
            group_booking_id=group_id,
            seat_numbers=data.seat_number,
            title=data.title,
            gender=data.gender,
            first_name=data.first_name,
            middle_name=data.middle_name,
            last_name=data.last_name,
            date_of_birth=data.date_of_birth,
            nationality=data.nationality,
            passport_number=data.passport_number,
            passport_expiry=data.passport_expiry,
            country_code=data.country_code,
            phone_number=data.phone_number,
        )
        db.add(booking)
        await db.flush()
        await db.refresh(booking)

        # Step 4: Emit BookingCreated event
        if event_publisher:
            try:
                event_publisher.publish("booking-service", "BookingCreated", {
                    "booking_id": str(booking.id),
                    "booking_reference": booking.booking_reference,
                    "user_id": str(booking.user_id),
                    "flight_id": str(booking.flight_id),
                    "passenger_name": booking.passenger_name,
                    "passenger_email": booking.passenger_email,
                    "total_price": booking.total_price,
                    "cabin_class": booking.cabin_class,
                })
            except Exception as e:
                logger.error("Failed to publish BookingCreated event", error=str(e))

        # Invalidate booking list cache for this user
        redis_delete(redis_client, f"bookings:{current_user['sub']}", "bookings:admin")

        return _to_response(booking)
    finally:
        redis_delete(redis_client, lock_key)


@app.get("/api/v1/bookings", response_model=list[BookingResponse])
async def list_bookings(current_user: dict = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    is_admin = current_user.get("role") == "admin"
    cache_key = "bookings:admin" if is_admin else f"bookings:{current_user['sub']}"

    cached = redis_get_json(redis_client, cache_key)
    if cached is not None:
        return cached

    if is_admin:
        passenger_ids = text("SELECT id FROM users WHERE role::text = 'PASSENGER'")
        result_ids = await db.execute(passenger_ids)
        passenger_user_ids = [str(row[0]) for row in result_ids.fetchall()]
        query = (
            select(Booking)
            .where(Booking.user_id.in_(passenger_user_ids))
            .order_by(Booking.created_at.desc())
        )
    else:
        query = (
            select(Booking)
            .where(Booking.user_id == current_user["sub"])
            .order_by(Booking.created_at.desc())
        )
    result = await db.execute(query)
    bookings = [_to_response(b).dict() for b in result.scalars().all()]
    redis_set_json(redis_client, cache_key, bookings, BOOKINGS_LIST_TTL)
    return bookings


# NOTE: this must be defined BEFORE /{booking_id} to avoid path shadowing
@app.get("/api/v1/bookings/seat-availability", response_model=SeatAvailabilityResponse)
async def get_seat_availability(
    flight_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all taken seat numbers for a flight (used to render the seat map)."""
    result = await db.execute(
        select(Booking.seat_numbers).where(
            Booking.flight_id == flight_id,
            Booking.status.not_in([BookingStatus.CANCELLED, BookingStatus.REFUNDED]),
            Booking.seat_numbers.isnot(None),
        )
    )
    booked: list[str] = []
    for row in result.scalars().all():
        if row:
            booked.extend(s.strip() for s in row.split(",") if s.strip())
    return SeatAvailabilityResponse(booked_seats=booked)


@app.get("/api/v1/bookings/{booking_id}", response_model=BookingResponse)
async def get_booking(booking_id: str, current_user: dict = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return _to_response(booking)


@app.put("/api/v1/bookings/{booking_id}/status", response_model=BookingResponse)
async def update_booking_status(booking_id: str, data: BookingStatusUpdate,
                                db: AsyncSession = Depends(get_db)):
    """Internal endpoint for other services to update booking status."""
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    new_status = BookingStatus(data.status)
    booking.status = new_status
    if data.payment_id:
        booking.payment_id = data.payment_id

    # For return trips: cascade status to the other leg in the same group
    if booking.group_booking_id:
        linked = await db.execute(
            select(Booking).where(
                Booking.group_booking_id == booking.group_booking_id,
                Booking.id != booking.id,
            )
        )
        for sibling in linked.scalars().all():
            sibling.status = new_status

    await db.flush()
    await db.refresh(booking)
    return _to_response(booking)


@app.post("/api/v1/bookings/{booking_id}/cancel", response_model=BookingResponse)
async def cancel_booking(booking_id: str, current_user: dict = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.status in (BookingStatus.CANCELLED, BookingStatus.REFUNDED):
        raise HTTPException(status_code=400, detail="Booking already cancelled")

    # Compensating transaction: release seats back (saga compensation)
    try:
        await flight_breaker.call_async(
            _flight_update_seats, str(booking.flight_id), booking.cabin_class, booking.num_passengers
        )
    except Exception as e:
        # Seat release failed — log for manual reconciliation. The booking is still
        # cancelled (correct from the customer's perspective) but inventory is
        # understated until the flight service recovers or a reconciliation job runs.
        logger.error("seat_release_failed_on_cancel",
                     booking_id=booking_id,
                     flight_id=str(booking.flight_id),
                     cabin_class=booking.cabin_class,
                     num_passengers=booking.num_passengers,
                     error=str(e))

    booking.status = BookingStatus.CANCELLED
    await db.flush()
    await db.refresh(booking)

    # Bust cache for this user and admin
    redis_delete(redis_client, f"bookings:{current_user['sub']}", "bookings:admin")

    if event_publisher:
        try:
            event_publisher.publish("booking-service", "BookingCancelled", {
                "booking_id": str(booking.id),
                "booking_reference": booking.booking_reference,
                "flight_id": str(booking.flight_id),
                "user_id": str(booking.user_id),
                "passenger_name": booking.passenger_name,
                "passenger_email": booking.passenger_email,
            })
        except Exception as e:
            logger.error("Failed to publish BookingCancelled event", error=str(e))

    return _to_response(booking)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
