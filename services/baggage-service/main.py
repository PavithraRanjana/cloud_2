import sys
import os
import time
import random
import string

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from shared.health import check_db, check_redis
from shared.config import BaseConfig
from shared.database import create_db_engine, create_session_factory, Base
from shared.auth import get_current_user, RoleChecker
from shared.events import EventPublisher
from shared.cache import create_redis_client, redis_get_json, redis_set_json, redis_delete
from shared.logging import setup_logging
from shared.tracing import TraceMiddleware
from shared.schemas import HealthResponse
from models import Baggage, BaggageStatus
from schemas import BaggageRegister, BaggageResponse, BaggageStatusUpdate

config = BaseConfig(service_name="baggage-service")
setup_logging(config.service_name)

engine = create_db_engine(config.database_url)
SessionFactory = create_session_factory(engine)
START_TIME = time.time()

redis_client = create_redis_client(config.redis_url)
TAG_CACHE_TTL   = 300  # baggage status — 5 min, invalidated on update
ADMIN_CACHE_TTL = 30   # admin list — 30 sec (staff need fresher data)

event_publisher = None
try:
    event_publisher = EventPublisher(
        endpoint_url=config.aws_endpoint_url, region=config.aws_region,
        bus_name=config.event_bus_name,
    )
except Exception:
    pass


def generate_tag() -> str:
    return "BAG-" + "".join(random.choices(string.digits, k=10))


async def get_db():
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _to_response(b: Baggage) -> BaggageResponse:
    return BaggageResponse(
        id=str(b.id), tag_number=b.tag_number, booking_id=str(b.booking_id),
        passenger_name=b.passenger_name, flight_id=str(b.flight_id),
        weight_kg=b.weight_kg, status=b.status.value,
        last_location=b.last_location, description=b.description,
        created_at=b.created_at,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        try:
            await conn.run_sync(Base.metadata.create_all)
        except Exception:
            pass
        await conn.execute(text(
            "ALTER TABLE baggage ADD COLUMN IF NOT EXISTS passenger_email VARCHAR(255)"
        ))
    yield
    await engine.dispose()


app = FastAPI(title="AeroLink Baggage Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(TraceMiddleware)


@app.get("/health", response_model=HealthResponse)
async def health(db: AsyncSession = Depends(get_db)):
    return HealthResponse(service="baggage-service", uptime_seconds=time.time() - START_TIME,
                          dependencies={"database": await check_db(db),
                                        "redis": check_redis(redis_client)})


@app.get("/api/v1/baggage", response_model=list[BaggageResponse])
async def list_all_baggage(
    current_user: dict = Depends(RoleChecker(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    """Admin endpoint: return all baggage items across all passengers."""
    cached = redis_get_json(redis_client, "baggage:admin")
    if cached is not None:
        return cached
    result = await db.execute(select(Baggage).order_by(Baggage.created_at.desc()))
    items = [_to_response(b).dict() for b in result.scalars().all()]
    redis_set_json(redis_client, "baggage:admin", items, ADMIN_CACHE_TTL)
    return items


@app.post("/api/v1/baggage", response_model=BaggageResponse, status_code=201)
async def register_baggage(data: BaggageRegister,
                           current_user: dict = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    baggage = Baggage(
        tag_number=generate_tag(),
        booking_id=data.booking_id,
        passenger_name=data.passenger_name,
        passenger_email=data.passenger_email,
        flight_id=data.flight_id,
        weight_kg=data.weight_kg,
        description=data.description,
    )
    db.add(baggage)
    await db.flush()
    await db.refresh(baggage)

    # New baggage busts the admin list cache
    redis_delete(redis_client, "baggage:admin")

    if event_publisher:
        try:
            event_publisher.publish("baggage-service", "BaggageRegistered", {
                "tag_number": baggage.tag_number,
                "booking_id": str(baggage.booking_id),
                "passenger_name": baggage.passenger_name,
                "passenger_email": baggage.passenger_email or "",
                "weight_kg": baggage.weight_kg,
            })
        except Exception:
            pass

    return _to_response(baggage)


@app.get("/api/v1/baggage/{tag_number}", response_model=BaggageResponse)
async def track_baggage(tag_number: str, db: AsyncSession = Depends(get_db)):
    cache_key = f"baggage:tag:{tag_number}"
    cached = redis_get_json(redis_client, cache_key)
    if cached is not None:
        return cached
    result = await db.execute(select(Baggage).where(Baggage.tag_number == tag_number))
    baggage = result.scalar_one_or_none()
    if not baggage:
        raise HTTPException(status_code=404, detail="Baggage not found")
    data = _to_response(baggage).dict()
    redis_set_json(redis_client, cache_key, data, TAG_CACHE_TTL)
    return data


@app.get("/api/v1/baggage/booking/{booking_id}", response_model=list[BaggageResponse])
async def get_baggage_by_booking(booking_id: str,
                                 current_user: dict = Depends(get_current_user),
                                 db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Baggage).where(Baggage.booking_id == booking_id))
    return [_to_response(b) for b in result.scalars().all()]


@app.put("/api/v1/baggage/{tag_number}/status", response_model=BaggageResponse)
async def update_baggage_status(tag_number: str, data: BaggageStatusUpdate,
                                current_user: dict = Depends(RoleChecker(["admin", "airport-operator"])),
                                db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Baggage).where(Baggage.tag_number == tag_number))
    baggage = result.scalar_one_or_none()
    if not baggage:
        raise HTTPException(status_code=404, detail="Baggage not found")

    baggage.status = BaggageStatus(data.status)
    if data.location:
        baggage.last_location = data.location
    await db.flush()
    await db.refresh(baggage)

    # Bust tag cache and admin list cache on status change
    redis_delete(redis_client, f"baggage:tag:{tag_number}", "baggage:admin")

    if event_publisher:
        try:
            event_publisher.publish("baggage-service", "BaggageStatusChanged", {
                "tag_number": baggage.tag_number,
                "booking_id": str(baggage.booking_id),
                "passenger_name": baggage.passenger_name,
                "passenger_email": baggage.passenger_email or "",
                "status": baggage.status.value,
                "location": baggage.last_location or "N/A",
            })
        except Exception:
            pass

    return _to_response(baggage)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
