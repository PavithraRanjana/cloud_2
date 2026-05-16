import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
import httpx
from shared.config import BaseConfig
from shared.database import create_db_engine, create_session_factory, Base
from shared.auth import get_current_user
from shared.encryption import encrypt_field, decrypt_field
from shared.audit import AuditLog, record_audit
from shared.logging import setup_logging
from shared.schemas import HealthResponse
from models import PassengerProfile, GDPRConsent
from schemas import (ProfileCreate, ProfileUpdate, ProfileResponse,
                     ConsentRequest, ConsentResponse)

config = BaseConfig(service_name="passenger-service")
setup_logging(config.service_name)

engine = create_db_engine(config.database_url)
SessionFactory = create_session_factory(engine)
START_TIME = time.time()


async def get_db():
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _to_response(p: PassengerProfile) -> ProfileResponse:
    # Decrypt passport number on read
    passport = None
    if p.passport_number_encrypted:
        try:
            passport = decrypt_field(p.passport_number_encrypted)
        except Exception:
            passport = "***ENCRYPTED***"

    return ProfileResponse(
        id=str(p.id), user_id=str(p.user_id),
        first_name=p.first_name, middle_name=p.middle_name, last_name=p.last_name,
        date_of_birth=p.date_of_birth, nationality=p.nationality,
        passport_number=passport, phone_number=p.phone_number,
        loyalty_tier=p.loyalty_tier, loyalty_points=p.loyalty_points,
        meal_preference=p.meal_preference, seat_preference=p.seat_preference,
        created_at=p.created_at,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        try:
            await conn.run_sync(Base.metadata.create_all)
        except Exception:
            pass  # Table may already exist from another service starting concurrently
        await conn.execute(text(
            "ALTER TABLE passenger_profiles ADD COLUMN IF NOT EXISTS middle_name VARCHAR(100)"
        ))
        await conn.execute(text(
            "ALTER TABLE passenger_profiles ALTER COLUMN nationality TYPE VARCHAR(100)"
        ))
    yield
    await engine.dispose()


app = FastAPI(title="AeroLink Passenger Service", version="1.0.0", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(service="passenger-service", uptime_seconds=time.time() - START_TIME,
                          dependencies={"database": "healthy"})


@app.post("/api/v1/passengers/profile", response_model=ProfileResponse, status_code=201)
async def create_profile(data: ProfileCreate,
                         current_user: dict = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(PassengerProfile).where(PassengerProfile.user_id == current_user["sub"]))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Profile already exists")

    # Encrypt PII fields before storage
    encrypted_passport = encrypt_field(data.passport_number) if data.passport_number else None

    profile = PassengerProfile(
        user_id=current_user["sub"],
        first_name=data.first_name,
        middle_name=data.middle_name,
        last_name=data.last_name,
        date_of_birth=data.date_of_birth,
        nationality=data.nationality,
        passport_number_encrypted=encrypted_passport,
        phone_number=data.phone_number,
        meal_preference=data.meal_preference,
        seat_preference=data.seat_preference,
        emergency_contact=data.emergency_contact,
    )
    db.add(profile)
    await db.flush()
    await db.refresh(profile)
    return _to_response(profile)


@app.get("/api/v1/passengers/profile", response_model=ProfileResponse)
async def get_profile(current_user: dict = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PassengerProfile).where(PassengerProfile.user_id == current_user["sub"]))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return _to_response(profile)


@app.put("/api/v1/passengers/profile", response_model=ProfileResponse)
async def update_profile(data: ProfileUpdate,
                         current_user: dict = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PassengerProfile).where(PassengerProfile.user_id == current_user["sub"]))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    update_data = data.dict(exclude_unset=True)
    # Encrypt passport if being updated
    if "passport_number" in update_data:
        val = update_data.pop("passport_number")
        profile.passport_number_encrypted = encrypt_field(val) if val else None
    for key, value in update_data.items():
        setattr(profile, key, value)
    await db.flush()
    await db.refresh(profile)
    return _to_response(profile)


@app.delete("/api/v1/passengers/profile", status_code=204)
async def delete_profile(request: Request,
                         current_user: dict = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    """GDPR right to erasure - delete passenger profile and cascade to related services."""
    result = await db.execute(
        select(PassengerProfile).where(PassengerProfile.user_id == current_user["sub"]))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Delete consent records
    consents = await db.execute(
        select(GDPRConsent).where(GDPRConsent.user_id == current_user["sub"]))
    for consent in consents.scalars().all():
        await db.delete(consent)

    # Audit the deletion
    client_ip = request.client.host if request.client else None
    await record_audit(db, "passenger-service", "gdpr.erasure", "passenger_profile",
                       resource_id=str(profile.id), actor_id=current_user["sub"],
                       actor_role=current_user.get("role"),
                       detail="GDPR right to erasure exercised - profile and consents deleted",
                       ip_address=client_ip)

    # Cascade: request deletion from other services
    for service_url, path in [
        (config.booking_service_url, f"/api/v1/bookings/user/{current_user['sub']}/anonymize"),
        (config.notification_service_url, f"/api/v1/notifications/user/{current_user['sub']}/anonymize"),
    ]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(f"{service_url}{path}")
        except Exception:
            pass  # Best-effort cascade

    await db.delete(profile)


# ─── GDPR Consent Management ────────────────────────────────

@app.post("/api/v1/passengers/consent", response_model=ConsentResponse, status_code=201)
async def grant_consent(data: ConsentRequest, request: Request,
                        current_user: dict = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    """Record GDPR consent for a specific data processing purpose."""
    # Check for existing consent for this purpose
    existing = await db.execute(
        select(GDPRConsent).where(
            GDPRConsent.user_id == current_user["sub"],
            GDPRConsent.purpose == data.purpose))
    consent = existing.scalar_one_or_none()

    client_ip = request.client.host if request.client else None

    if consent:
        consent.granted = data.granted
        if data.granted:
            consent.granted_at = datetime.now(timezone.utc)
            consent.revoked_at = None
        else:
            consent.revoked_at = datetime.now(timezone.utc)
        consent.ip_address = client_ip
    else:
        consent = GDPRConsent(
            user_id=current_user["sub"],
            purpose=data.purpose,
            granted=data.granted,
            granted_at=datetime.now(timezone.utc) if data.granted else None,
            ip_address=client_ip,
        )
        db.add(consent)

    await db.flush()
    await db.refresh(consent)

    await record_audit(db, "passenger-service",
                       f"consent.{'granted' if data.granted else 'revoked'}",
                       "gdpr_consent", resource_id=str(consent.id),
                       actor_id=current_user["sub"],
                       detail=f"Purpose: {data.purpose}", ip_address=client_ip)

    return ConsentResponse(
        id=str(consent.id), user_id=str(consent.user_id),
        purpose=consent.purpose, granted=consent.granted,
        granted_at=consent.granted_at, revoked_at=consent.revoked_at,
        created_at=consent.created_at,
    )


@app.get("/api/v1/passengers/consent", response_model=list[ConsentResponse])
async def list_consents(current_user: dict = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    """List all GDPR consents for the current user."""
    result = await db.execute(
        select(GDPRConsent).where(GDPRConsent.user_id == current_user["sub"]))
    return [ConsentResponse(
        id=str(c.id), user_id=str(c.user_id), purpose=c.purpose,
        granted=c.granted, granted_at=c.granted_at, revoked_at=c.revoked_at,
        created_at=c.created_at,
    ) for c in result.scalars().all()]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8007)
