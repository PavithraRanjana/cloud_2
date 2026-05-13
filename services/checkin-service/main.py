import sys
import os
import time
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx
from shared.config import BaseConfig
from shared.database import create_db_engine, create_session_factory, Base
from shared.auth import get_current_user
from shared.events import EventPublisher
from shared.logging import setup_logging
from shared.schemas import HealthResponse
from models import CheckIn, CheckInStatus
from schemas import CheckInRequest, CheckInResponse

config = BaseConfig(service_name="checkin-service")
setup_logging(config.service_name)

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


def resolve_seat(seat_preference: str | None) -> tuple[str, str]:
    """Use the booked seat if provided; otherwise fall back to random assignment."""
    if seat_preference:
        seat = seat_preference.strip().split(",")[0].strip()
        if seat:
            row_str = "".join(c for c in seat if c.isdigit())
            row = int(row_str) if row_str else 15
            group = "A" if row <= 10 else "B" if row <= 20 else "C"
            return seat, group
    row = random.randint(1, 35)
    col = random.choice(["A", "B", "C", "D", "E", "F"])
    group = "A" if row <= 10 else "B" if row <= 20 else "C"
    return f"{row}{col}", group


async def get_db():
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _to_response(c: CheckIn) -> CheckInResponse:
    return CheckInResponse(
        id=str(c.id), booking_id=str(c.booking_id), flight_id=str(c.flight_id),
        passenger_name=c.passenger_name, seat_number=c.seat_number or "",
        boarding_group=c.boarding_group or "", gate=c.gate,
        status=c.status.value, boarding_pass_url=c.boarding_pass_url,
        has_baggage=c.has_baggage, created_at=c.created_at,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        try:
            await conn.run_sync(Base.metadata.create_all)
        except Exception:
            pass  # Table may already exist from another service starting concurrently
    yield
    await engine.dispose()


app = FastAPI(title="AeroLink Check-In Service", version="1.0.0", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(service="checkin-service", uptime_seconds=time.time() - START_TIME,
                          dependencies={"database": "healthy"})


@app.post("/api/v1/checkin", response_model=CheckInResponse, status_code=201)
async def check_in(data: CheckInRequest,
                   current_user: dict = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(CheckIn).where(CheckIn.booking_id == data.booking_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already checked in for this booking")

    seat, group = resolve_seat(data.seat_preference)
    checkin = CheckIn(
        booking_id=data.booking_id,
        flight_id=data.flight_id,
        passenger_name=data.passenger_name,
        seat_number=seat,
        boarding_group=group,
        status=CheckInStatus.BOARDING_PASS_ISSUED,
        boarding_pass_url=f"/api/v1/checkin/{data.booking_id}/boarding-pass",
    )
    db.add(checkin)
    await db.flush()
    await db.refresh(checkin)

    # Update booking status via saga
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.put(
                f"{config.booking_service_url}/api/v1/bookings/{data.booking_id}/status",
                json={"status": "checked-in"}
            )
    except Exception:
        pass

    if event_publisher:
        try:
            event_publisher.publish("checkin-service", "CheckInCompleted", {
                "booking_id": data.booking_id,
                "flight_id": data.flight_id,
                "passenger_name": data.passenger_name,
                "seat_number": seat,
                "boarding_group": group,
                "gate": checkin.gate or "TBA",
            })
        except Exception:
            pass

    return _to_response(checkin)


@app.get("/api/v1/checkin/{booking_id}", response_model=CheckInResponse)
async def get_checkin(booking_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CheckIn).where(CheckIn.booking_id == booking_id))
    checkin = result.scalar_one_or_none()
    if not checkin:
        raise HTTPException(status_code=404, detail="Check-in not found")
    return _to_response(checkin)


@app.get("/api/v1/checkin/{booking_id}/boarding-pass")
async def get_boarding_pass(booking_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CheckIn).where(CheckIn.booking_id == booking_id))
    checkin = result.scalar_one_or_none()
    if not checkin:
        raise HTTPException(status_code=404, detail="Check-in not found")
    return {
        "boarding_pass": {
            "passenger": checkin.passenger_name,
            "seat": checkin.seat_number,
            "boarding_group": checkin.boarding_group,
            "gate": checkin.gate or "TBA",
            "flight_id": str(checkin.flight_id),
            "status": "READY TO BOARD",
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)
