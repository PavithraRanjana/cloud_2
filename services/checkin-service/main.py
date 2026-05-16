import sys
import os
import time
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx
import boto3
import structlog
from sqlalchemy import text
from shared.config import BaseConfig
from shared.database import create_db_engine, create_session_factory, Base
from shared.auth import get_current_user
from shared.events import EventPublisher
from shared.cache import create_redis_client, redis_get_json, redis_set_json, redis_delete
from shared.logging import setup_logging
from shared.schemas import HealthResponse
from models import CheckIn, CheckInStatus
from schemas import CheckInRequest, CheckInResponse

config = BaseConfig(service_name="checkin-service")
setup_logging(config.service_name)
logger = structlog.get_logger()

S3_BUCKET = "aerolink-documents"

_s3 = None
try:
    _s3 = boto3.client(
        "s3",
        endpoint_url=config.aws_endpoint_url,
        region_name=config.aws_region,
        aws_access_key_id=config.aws_access_key_id,
        aws_secret_access_key=config.aws_secret_access_key,
    )
except Exception:
    pass

engine = create_db_engine(config.database_url)
SessionFactory = create_session_factory(engine)
START_TIME = time.time()

redis_client = create_redis_client(config.redis_url)
CHECKIN_CACHE_TTL  = 3600  # check-in record — 1 hour (immutable once issued)
PDF_URL_CACHE_TTL  = 3300  # presigned URL — cache for 55 min (URL expires at 60 min)

event_publisher = None
try:
    event_publisher = EventPublisher(
        endpoint_url=config.aws_endpoint_url, region=config.aws_region,
        bus_name=config.event_bus_name,
    )
except Exception:
    pass


def resolve_seat(seat_preference: str | None) -> tuple[str, str]:
    seat = (seat_preference or "").strip().split(",")[0].strip()
    if not seat:
        # Safety fallback — should not occur; all bookings now require a seat
        row = random.randint(1, 35)
        col = random.choice(["A", "B", "C", "D", "E", "F"])
        seat = f"{row}{col}"
    row_str = "".join(c for c in seat if c.isdigit())
    row = int(row_str) if row_str else 15
    group = "A" if row <= 10 else "B" if row <= 20 else "C"
    return seat, group


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
        has_baggage=c.has_baggage,
        seat_selected_by_user=c.seat_selected_by_user if c.seat_selected_by_user is not None else True,
        created_at=c.created_at,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        try:
            await conn.run_sync(Base.metadata.create_all)
        except Exception:
            pass
        try:
            await conn.execute(text(
                "ALTER TABLE checkins ADD COLUMN IF NOT EXISTS seat_selected_by_user BOOLEAN DEFAULT TRUE"
            ))
        except Exception:
            pass
    yield
    await engine.dispose()


app = FastAPI(title="AeroLink Check-In Service", version="1.0.0", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(service="checkin-service", uptime_seconds=time.time() - START_TIME,
                          dependencies={"database": "healthy",
                                        "redis": "healthy" if redis_client else "unavailable"})


@app.post("/api/v1/checkin", response_model=CheckInResponse, status_code=201)
async def check_in(data: CheckInRequest,
                   current_user: dict = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(CheckIn).where(CheckIn.booking_id == data.booking_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already checked in for this booking")

    seat, group = resolve_seat(data.seat_preference)
    selected_by_user = data.seat_selected_by_user if data.seat_selected_by_user is not None else (data.seat_preference is not None)
    checkin = CheckIn(
        booking_id=data.booking_id,
        flight_id=data.flight_id,
        passenger_name=data.passenger_name,
        seat_number=seat,
        seat_selected_by_user=selected_by_user,
        boarding_group=group,
        status=CheckInStatus.BOARDING_PASS_ISSUED,
        boarding_pass_url=f"/api/v1/checkin/{data.booking_id}/boarding-pass",
    )
    db.add(checkin)
    await db.flush()
    await db.refresh(checkin)

    # Cache the new check-in record
    redis_set_json(redis_client, f"checkin:{data.booking_id}", _to_response(checkin).dict(), CHECKIN_CACHE_TTL)

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
                "passenger_email": current_user.get("email", ""),
                "seat_number": seat,
                "boarding_group": group,
                "gate": checkin.gate or "TBA",
            })
        except Exception:
            pass

    return _to_response(checkin)


@app.get("/api/v1/checkin/{booking_id}", response_model=CheckInResponse)
async def get_checkin(booking_id: str, db: AsyncSession = Depends(get_db)):
    cached = redis_get_json(redis_client, f"checkin:{booking_id}")
    if cached is not None:
        return cached
    result = await db.execute(select(CheckIn).where(CheckIn.booking_id == booking_id))
    checkin = result.scalar_one_or_none()
    if not checkin:
        raise HTTPException(status_code=404, detail="Check-in not found")
    data = _to_response(checkin).dict()
    redis_set_json(redis_client, f"checkin:{booking_id}", data, CHECKIN_CACHE_TTL)
    return data


@app.get("/api/v1/checkin/{booking_id}/boarding-pass", response_class=HTMLResponse)
async def get_boarding_pass(
    booking_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(CheckIn).where(CheckIn.booking_id == booking_id))
    checkin = result.scalar_one_or_none()
    if not checkin:
        raise HTTPException(status_code=404, detail="Check-in not found")

    auth_header = request.headers.get("Authorization", "")

    flight, booking = None, None
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            fr = await client.get(f"{config.flight_service_url}/api/v1/flights/{checkin.flight_id}")
            if fr.status_code == 200:
                flight = fr.json()
        except Exception:
            pass
        try:
            br = await client.get(
                f"{config.booking_service_url}/api/v1/bookings/{booking_id}",
                headers={"Authorization": auth_header},
            )
            if br.status_code == 200:
                booking = br.json()
        except Exception:
            pass

    def fmt_time(t: str) -> str:
        if not t:
            return "—"
        parts = t[:5].split(":")
        h = int(parts[0])
        m = parts[1] if len(parts) > 1 else "00"
        period = "PM" if h >= 12 else "AM"
        return f"{h % 12 or 12}:{m} {period}"

    def fmt_date(d: str) -> str:
        if not d:
            return "—"
        from datetime import date as dt
        try:
            parsed = dt.fromisoformat(d)
            return parsed.strftime("%a, %b %-d %Y")
        except Exception:
            return d

    passenger_name = checkin.passenger_name.upper()
    seat           = checkin.seat_number or "—"
    group          = checkin.boarding_group or "—"
    gate           = checkin.gate or (flight or {}).get("gate") or "TBA"
    flight_num     = (flight or {}).get("flight_number", "—")
    airline        = (flight or {}).get("airline", "")
    origin         = (flight or {}).get("origin", "—")
    destination    = (flight or {}).get("destination", "—")
    dep_time       = fmt_time((flight or {}).get("departure_time", ""))
    arr_time       = fmt_time((flight or {}).get("arrival_time", ""))
    dep_date       = fmt_date((flight or {}).get("departure_date", ""))
    cabin          = ((booking or {}).get("cabin_class") or "economy").capitalize()
    ref            = (booking or {}).get("booking_reference", "—")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Boarding Pass – {passenger_name}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #f0f4ff; display: flex; justify-content: center;
         align-items: flex-start; min-height: 100vh; padding: 40px 16px; }}
  .card {{ background: #fff; border-radius: 20px; overflow: hidden;
           width: 480px; box-shadow: 0 8px 40px rgba(0,0,0,0.12); }}
  .header {{ background: linear-gradient(135deg, #1d4ed8, #3b82f6);
             padding: 24px 28px; color: #fff; }}
  .header-top {{ display: flex; justify-content: space-between; align-items: center;
                 margin-bottom: 16px; }}
  .logo {{ display: flex; align-items: center; gap: 8px;
           font-weight: 800; font-size: 13px; letter-spacing: 3px; }}
  .badge {{ background: rgba(255,255,255,0.2); border-radius: 100px;
            padding: 3px 12px; font-size: 11px; font-weight: 700;
            letter-spacing: 1px; text-transform: uppercase; }}
  .pax-label {{ font-size: 10px; color: rgba(255,255,255,0.6);
                letter-spacing: 3px; text-transform: uppercase; margin-bottom: 4px; }}
  .pax-name {{ font-size: 26px; font-weight: 800; letter-spacing: 1px; }}
  .route {{ background: #eff6ff; padding: 18px 28px;
            display: flex; align-items: center; gap: 12px;
            border-bottom: 1px solid #dbeafe; }}
  .airport {{ text-align: center; flex: 1; }}
  .airport-code {{ font-size: 28px; font-weight: 900; color: #1d4ed8;
                   font-family: 'Courier New', monospace; }}
  .airport-time {{ font-size: 12px; color: #6b7280; margin-top: 2px; }}
  .divider {{ flex: 1; display: flex; flex-direction: column; align-items: center; gap: 4px; }}
  .line {{ width: 100%; height: 1px; background: #bfdbfe; }}
  .flight-label {{ font-size: 10px; color: #93c5fd; font-weight: 600; }}
  .details {{ display: grid; grid-template-columns: repeat(3, 1fr);
              gap: 18px; padding: 22px 28px; }}
  .detail-label {{ font-size: 9px; font-weight: 700; text-transform: uppercase;
                   letter-spacing: 2px; color: #9ca3af; margin-bottom: 4px; }}
  .detail-value {{ font-size: 26px; font-weight: 900; color: #111827;
                   font-family: 'Courier New', monospace; line-height: 1; }}
  .detail-value.sm {{ font-size: 13px; font-weight: 700; padding-top: 6px; }}
  .tear {{ border-top: 2px dashed #bfdbfe; margin: 0 20px; }}
  .footer {{ padding: 16px 28px; background: #f9fafb;
             display: flex; justify-content: space-between; align-items: center; }}
  .barcode {{ display: flex; gap: 2px; align-items: center; }}
  .bar {{ background: #1f2937; border-radius: 2px; }}
  .status-block {{ text-align: right; }}
  .status-label {{ font-size: 9px; font-weight: 700; text-transform: uppercase;
                   letter-spacing: 2px; color: #9ca3af; }}
  .status-value {{ font-size: 13px; font-weight: 800; color: #059669;
                   text-transform: uppercase; letter-spacing: 1px; margin-top: 2px; }}
  @media print {{
    body {{ background: #fff; padding: 0; }}
    .card {{ box-shadow: none; width: 100%; border-radius: 0; }}
    .no-print {{ display: none !important; }}
  }}
  .download-btn {{
    display: block; margin: 28px auto 0; padding: 12px 36px;
    background: #2563eb; color: #fff; border: none; border-radius: 10px;
    font-size: 14px; font-weight: 700; cursor: pointer; letter-spacing: 0.5px;
  }}
  .download-btn:hover {{ background: #1d4ed8; }}
</style>
</head>
<body>
<div>
  <div class="card">
    <div class="header">
      <div class="header-top">
        <div class="logo">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
            <path d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/>
          </svg>
          AEROLINK
        </div>
        <span class="badge">Boarding Pass</span>
      </div>
      <div class="pax-label">Passenger</div>
      <div class="pax-name">{passenger_name}</div>
    </div>

    <div class="route">
      <div class="airport">
        <div class="airport-code">{origin}</div>
        <div class="airport-time">{dep_time}</div>
      </div>
      <div class="divider">
        <div class="line"></div>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="#93c5fd">
          <path d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/>
        </svg>
        <div class="line"></div>
        <div class="flight-label">{flight_num} · {airline}</div>
      </div>
      <div class="airport">
        <div class="airport-code">{destination}</div>
        <div class="airport-time">{arr_time}</div>
      </div>
    </div>

    <div class="details">
      <div>
        <div class="detail-label">Seat</div>
        <div class="detail-value">{seat}</div>
      </div>
      <div>
        <div class="detail-label">Group</div>
        <div class="detail-value">{group}</div>
      </div>
      <div>
        <div class="detail-label">Gate</div>
        <div class="detail-value">{gate}</div>
      </div>
      <div>
        <div class="detail-label">Date</div>
        <div class="detail-value sm">{dep_date}</div>
      </div>
      <div>
        <div class="detail-label">Cabin</div>
        <div class="detail-value sm">{cabin}</div>
      </div>
      <div>
        <div class="detail-label">Ref</div>
        <div class="detail-value sm" style="color:#2563eb;font-size:14px">{ref}</div>
      </div>
    </div>

    <div class="tear"></div>

    <div class="footer">
      <div class="barcode">
        {"".join(f'<div class="bar" style="width:{"3" if i%3==0 else "1"}px;height:{"32" if i%5==0 else "22"}px"></div>' for i in range(40))}
      </div>
      <div class="status-block">
        <div class="status-label">Status</div>
        <div class="status-value">Ready to board</div>
      </div>
    </div>
  </div>

  <button class="download-btn no-print" onclick="window.print()">
    Print / Save as PDF
  </button>
</div>
<script>window.onload = function() {{ window.print(); }}</script>
</body>
</html>"""

    return HTMLResponse(content=html)


@app.get("/api/v1/checkin/{booking_id}/boarding-pass/pdf")
async def get_boarding_pass_pdf(
    booking_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return a presigned S3 URL for the PDF boarding pass generated by the Lambda."""
    result = await db.execute(select(CheckIn).where(CheckIn.booking_id == booking_id))
    checkin = result.scalar_one_or_none()
    if not checkin:
        raise HTTPException(status_code=404, detail="Check-in not found")

    if not _s3:
        raise HTTPException(status_code=503, detail="S3 unavailable")

    s3_key = f"boarding-passes/{booking_id}.pdf"
    try:
        _s3.head_object(Bucket=S3_BUCKET, Key=s3_key)
    except Exception:
        raise HTTPException(status_code=404, detail="PDF boarding pass not yet generated")

    pdf_cache_key = f"pdf_url:{booking_id}"
    cached_url = redis_get_json(redis_client, pdf_cache_key)
    if cached_url is not None:
        return cached_url

    url = _s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET, "Key": s3_key},
        ExpiresIn=3600,
    )
    result_payload = {"url": url, "expires_in": 3600}
    redis_set_json(redis_client, pdf_cache_key, result_payload, PDF_URL_CACHE_TTL)
    return result_payload


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)
