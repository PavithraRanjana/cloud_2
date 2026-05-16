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
import httpx
from shared.config import BaseConfig
from shared.database import create_db_engine, create_session_factory, Base
from shared.auth import get_current_user
from shared.events import EventPublisher
from shared.resilience import create_circuit_breaker
from shared.logging import setup_logging
from shared.schemas import HealthResponse
from models import Booking, BookingStatus
from schemas import BookingCreate, BookingResponse, BookingStatusUpdate, SeatAvailabilityResponse

config = BaseConfig(service_name="booking-service")
setup_logging(config.service_name)

engine = create_db_engine(config.database_url)
SessionFactory = create_session_factory(engine)
START_TIME = time.time()

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


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(service="booking-service", uptime_seconds=time.time() - START_TIME,
                          dependencies={"database": "healthy", "flight-service": "healthy"})


@app.post("/api/v1/bookings", response_model=BookingResponse, status_code=201)
async def create_booking(data: BookingCreate,
                         current_user: dict = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    # Step 1: Check flight availability
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{config.flight_service_url}/api/v1/flights/{data.flight_id}")
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Flight not found")
        resp.raise_for_status()
        flight = resp.json()

    available_key = f"available_seats_{data.cabin_class}"
    if flight.get(available_key, 0) < data.num_passengers:
        raise HTTPException(status_code=409, detail=f"Not enough {data.cabin_class} seats available")

    # Step 2: Reserve seats
    price_key = f"price_{data.cabin_class}"
    total_price = flight.get(price_key, 0) * data.num_passengers

    async with httpx.AsyncClient(timeout=10.0) as client:
        seat_resp = await client.put(
            f"{config.flight_service_url}/api/v1/flights/{data.flight_id}/seats",
            json={"cabin_class": data.cabin_class, "change": -data.num_passengers}
        )
        if seat_resp.status_code == 409:
            raise HTTPException(status_code=409, detail="Seats no longer available (concurrent booking)")
        seat_resp.raise_for_status()

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
        # Passenger identity
        title=data.title,
        gender=data.gender,
        first_name=data.first_name,
        middle_name=data.middle_name,
        last_name=data.last_name,
        date_of_birth=data.date_of_birth,
        nationality=data.nationality,
        passport_number=data.passport_number,
        passport_expiry=data.passport_expiry,
        # Contact
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
        except Exception:
            pass

    return _to_response(booking)


@app.get("/api/v1/bookings", response_model=list[BookingResponse])
async def list_bookings(current_user: dict = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    if current_user.get("role") == "admin":
        # Return only bookings made by passenger-role users
        passenger_ids = text(
            "SELECT id FROM users WHERE UPPER(role) = 'PASSENGER'"
        )
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
    return [_to_response(b) for b in result.scalars().all()]


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

    # Compensating transaction: release seats back
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.put(
                f"{config.flight_service_url}/api/v1/flights/{booking.flight_id}/seats",
                json={"cabin_class": booking.cabin_class, "change": booking.num_passengers}
            )
    except Exception:
        pass

    booking.status = BookingStatus.CANCELLED
    await db.flush()
    await db.refresh(booking)

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
        except Exception:
            pass

    return _to_response(booking)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
