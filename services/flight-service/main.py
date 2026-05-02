import sys
import os
import time
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update
import redis
import structlog
from shared.config import BaseConfig
from shared.database import create_db_engine, create_session_factory, Base
from shared.auth import get_current_user, RoleChecker
from shared.events import EventPublisher
from shared.logging import setup_logging
from shared.schemas import HealthResponse
from models import Flight, FlightStatus
from schemas import FlightCreate, FlightUpdate, FlightResponse, SeatUpdate

config = BaseConfig(service_name="flight-service")
setup_logging(config.service_name)
logger = structlog.get_logger()

engine = create_db_engine(config.database_url)
SessionFactory = create_session_factory(engine)
START_TIME = time.time()

event_publisher = None
try:
    event_publisher = EventPublisher(
        endpoint_url=config.aws_endpoint_url, region=config.aws_region,
        bus_name=config.event_bus_name,
    )
except Exception:
    pass

# CQRS Read Model: Redis cache for flight search queries
redis_client = None
try:
    redis_client = redis.Redis.from_url(config.redis_url, decode_responses=True)
    redis_client.ping()
    logger.info("redis_connected", url=config.redis_url)
except Exception as e:
    logger.warning("redis_unavailable", error=str(e))
    redis_client = None

CACHE_TTL = 300  # 5 minutes


def _cache_key(origin: str = None, destination: str = None, departure_date: str = None) -> str:
    """Generate cache key for CQRS read model."""
    return f"flights:{origin or '*'}:{destination or '*'}:{departure_date or '*'}"


def _invalidate_cache_for_flight(flight):
    """Invalidate CQRS read cache when write model changes."""
    if not redis_client:
        return
    try:
        # Invalidate all cached searches that might include this flight
        pattern = f"flights:*{flight.origin}*"
        keys = redis_client.keys(pattern)
        pattern2 = f"flights:*:{flight.destination}:*"
        keys += redis_client.keys(pattern2)
        if keys:
            redis_client.delete(*keys)
        # Also invalidate single-flight cache
        redis_client.delete(f"flight:{flight.id}")
        logger.info("cache_invalidated", flight_id=str(flight.id))
    except Exception as e:
        logger.warning("cache_invalidation_failed", error=str(e))


async def get_db():
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        try:
            await conn.run_sync(Base.metadata.create_all)
        except Exception:
            pass  # Table may already exist from another service starting concurrently
    yield
    await engine.dispose()


app = FastAPI(title="AeroLink Flight Service", version="1.0.0", lifespan=lifespan)


def _to_response(f: Flight) -> FlightResponse:
    return FlightResponse(
        id=str(f.id), flight_number=f.flight_number, airline=f.airline,
        origin=f.origin, destination=f.destination,
        departure_date=f.departure_date, departure_time=f.departure_time,
        arrival_date=f.arrival_date, arrival_time=f.arrival_time,
        status=f.status.value, aircraft_type=f.aircraft_type,
        available_seats_economy=f.available_seats_economy,
        available_seats_business=f.available_seats_business,
        available_seats_first=f.available_seats_first,
        price_economy=f.price_economy, price_business=f.price_business,
        price_first=f.price_first, gate=f.gate, terminal=f.terminal,
        created_at=f.created_at,
    )


def _to_dict(f: Flight) -> dict:
    """Serialize flight to dict for Redis cache."""
    return {
        "id": str(f.id), "flight_number": f.flight_number, "airline": f.airline,
        "origin": f.origin, "destination": f.destination,
        "departure_date": str(f.departure_date), "departure_time": str(f.departure_time),
        "arrival_date": str(f.arrival_date), "arrival_time": str(f.arrival_time),
        "status": f.status.value, "aircraft_type": f.aircraft_type,
        "available_seats_economy": f.available_seats_economy,
        "available_seats_business": f.available_seats_business,
        "available_seats_first": f.available_seats_first,
        "price_economy": f.price_economy, "price_business": f.price_business,
        "price_first": f.price_first, "gate": f.gate, "terminal": f.terminal,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


@app.get("/health", response_model=HealthResponse)
async def health():
    deps = {"database": "healthy"}
    deps["redis_cache"] = "healthy" if redis_client else "unavailable"
    return HealthResponse(service="flight-service", uptime_seconds=time.time() - START_TIME,
                          dependencies=deps)


@app.get("/api/v1/flights")
async def search_flights(
    origin: str = Query(None), destination: str = Query(None),
    departure_date: str = Query(None), cabin_class: str = Query(None),
    min_price: float = Query(None), max_price: float = Query(None),
    cursor: str = Query(None, description="Cursor for pagination (flight ID)"),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    CQRS: Search reads from Redis cache first (read model), falls back to PostgreSQL (write model).
    Supports cursor-based pagination for efficient large dataset traversal.
    """
    cache_key = _cache_key(origin, destination, departure_date)

    # CQRS: Try read model (Redis cache) first
    if redis_client and not cursor and not min_price and not max_price:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                logger.info("cache_hit", key=cache_key)
                return {"items": json.loads(cached), "source": "cache", "next_cursor": None}
        except Exception:
            pass

    # Fall back to write model (PostgreSQL)
    query = select(Flight)
    conditions = []
    if origin:
        conditions.append(Flight.origin == origin.upper())
    if destination:
        conditions.append(Flight.destination == destination.upper())
    if departure_date:
        from datetime import date as dt_date
        conditions.append(Flight.departure_date == dt_date.fromisoformat(departure_date))
    if cabin_class and min_price is not None:
        price_col = getattr(Flight, f"price_{cabin_class}", Flight.price_economy)
        conditions.append(price_col >= min_price)
    if cabin_class and max_price is not None:
        price_col = getattr(Flight, f"price_{cabin_class}", Flight.price_economy)
        conditions.append(price_col <= max_price)

    # Cursor-based pagination: fetch flights after the cursor ID
    if cursor:
        conditions.append(Flight.id > cursor)

    if conditions:
        query = query.where(and_(*conditions))

    query = query.order_by(Flight.id).limit(page_size + 1)
    result = await db.execute(query)
    flights = result.scalars().all()

    has_next = len(flights) > page_size
    flights = flights[:page_size]
    next_cursor = str(flights[-1].id) if has_next and flights else None

    items = [_to_dict(f) for f in flights]

    # CQRS: Populate read model (cache) on miss
    if redis_client and not cursor and not min_price and not max_price:
        try:
            redis_client.setex(cache_key, CACHE_TTL, json.dumps(items, default=str))
            logger.info("cache_populated", key=cache_key)
        except Exception:
            pass

    return {"items": items, "source": "database", "next_cursor": next_cursor}


@app.get("/api/v1/flights/{flight_id}", response_model=FlightResponse)
async def get_flight(flight_id: str, db: AsyncSession = Depends(get_db)):
    # CQRS: Check cache first
    if redis_client:
        try:
            cached = redis_client.get(f"flight:{flight_id}")
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    result = await db.execute(select(Flight).where(Flight.id == flight_id))
    flight = result.scalar_one_or_none()
    if not flight:
        raise HTTPException(status_code=404, detail="Flight not found")

    resp = _to_response(flight)

    # Cache individual flight
    if redis_client:
        try:
            redis_client.setex(f"flight:{flight_id}", CACHE_TTL, resp.json())
        except Exception:
            pass

    return resp


@app.post("/api/v1/flights", response_model=FlightResponse, status_code=201)
async def create_flight(data: FlightCreate,
                        current_user: dict = Depends(RoleChecker(["admin", "airline-staff"])),
                        db: AsyncSession = Depends(get_db)):
    flight = Flight(
        flight_number=data.flight_number, airline=data.airline,
        origin=data.origin.upper(), destination=data.destination.upper(),
        departure_date=data.departure_date, departure_time=data.departure_time,
        arrival_date=data.arrival_date, arrival_time=data.arrival_time,
        aircraft_type=data.aircraft_type,
        total_seats_economy=data.total_seats_economy,
        total_seats_business=data.total_seats_business,
        total_seats_first=data.total_seats_first,
        available_seats_economy=data.total_seats_economy,
        available_seats_business=data.total_seats_business,
        available_seats_first=data.total_seats_first,
        price_economy=data.price_economy, price_business=data.price_business,
        price_first=data.price_first, gate=data.gate, terminal=data.terminal,
    )
    db.add(flight)
    await db.flush()
    await db.refresh(flight)

    # CQRS: Invalidate read model on write
    _invalidate_cache_for_flight(flight)

    if event_publisher:
        try:
            event_publisher.publish("flight-service", "FlightScheduleUpdated", {
                "flight_id": str(flight.id), "flight_number": flight.flight_number,
                "action": "created",
            })
        except Exception:
            pass

    return _to_response(flight)


@app.put("/api/v1/flights/{flight_id}", response_model=FlightResponse)
async def update_flight(flight_id: str, data: FlightUpdate,
                        current_user: dict = Depends(RoleChecker(["admin", "airline-staff"])),
                        db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Flight).where(Flight.id == flight_id))
    flight = result.scalar_one_or_none()
    if not flight:
        raise HTTPException(status_code=404, detail="Flight not found")

    update_data = data.dict(exclude_unset=True)
    for key, value in update_data.items():
        if key == "status":
            value = FlightStatus(value)
        setattr(flight, key, value)
    await db.flush()
    await db.refresh(flight)

    # CQRS: Invalidate read model on write
    _invalidate_cache_for_flight(flight)

    if event_publisher:
        try:
            event_publisher.publish("flight-service", "FlightScheduleUpdated", {
                "flight_id": str(flight.id), "flight_number": flight.flight_number,
                "action": "updated", "changes": list(update_data.keys()),
            })
        except Exception:
            pass

    return _to_response(flight)


@app.put("/api/v1/flights/{flight_id}/seats")
async def update_seats(flight_id: str, data: SeatUpdate,
                       db: AsyncSession = Depends(get_db)):
    """
    Internal endpoint for booking service to reserve/release seats.
    Uses OPTIMISTIC LOCKING to prevent double-booking race conditions.
    """
    result = await db.execute(select(Flight).where(Flight.id == flight_id))
    flight = result.scalar_one_or_none()
    if not flight:
        raise HTTPException(status_code=404, detail="Flight not found")

    seat_field = f"available_seats_{data.cabin_class}"
    current = getattr(flight, seat_field, None)
    if current is None:
        raise HTTPException(status_code=400, detail=f"Invalid cabin class: {data.cabin_class}")

    new_count = current + data.change
    if new_count < 0:
        raise HTTPException(status_code=409, detail="Not enough seats available")

    # OPTIMISTIC LOCKING: Only update if version hasn't changed (prevents double-booking)
    current_version = flight.version
    stmt = (
        update(Flight)
        .where(Flight.id == flight_id, Flight.version == current_version)
        .values(**{seat_field: new_count, "version": current_version + 1})
    )
    update_result = await db.execute(stmt)

    if update_result.rowcount == 0:
        # Another transaction modified this row - concurrent booking detected
        raise HTTPException(
            status_code=409,
            detail="Concurrent modification detected. Please retry the booking."
        )

    # CQRS: Invalidate read model on write
    _invalidate_cache_for_flight(flight)

    if event_publisher:
        try:
            event_publisher.publish("flight-service", "SeatAvailabilityChanged", {
                "flight_id": str(flight.id), "cabin_class": data.cabin_class,
                "available": new_count,
            })
        except Exception:
            pass

    return {"flight_id": flight_id, "cabin_class": data.cabin_class,
            "available_seats": new_count, "version": current_version + 1}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
