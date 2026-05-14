import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from shared.config import BaseConfig
from shared.database import create_db_engine, create_session_factory, Base
from shared.auth import (hash_password, verify_password, create_access_token,
                         create_refresh_token, decode_token, get_current_user)
from shared.audit import AuditLog, record_audit
from shared.logging import setup_logging
from shared.schemas import HealthResponse
from models import User, UserRole, generate_api_key
from schemas import (UserRegister, UserLogin, TokenResponse,
                     RefreshRequest, UserResponse)

config = BaseConfig(service_name="auth-service")
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        try:
            await conn.run_sync(Base.metadata.create_all)
        except Exception:
            pass  # Table may already exist from another service starting concurrently
    yield
    await engine.dispose()


app = FastAPI(title="AeroLink Auth Service", version="1.0.0", lifespan=lifespan)


def _to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=str(user.id), email=user.email, username=user.username,
        full_name=user.full_name, role=user.role.value,
        is_active=user.is_active,
        airport_code=user.airport_code, airline_code=user.airline_code,
        api_key=user.api_key,
        created_at=user.created_at,
    )


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(service="auth-service", uptime_seconds=time.time() - START_TIME,
                          dependencies={"database": "healthy"})


@app.post("/api/v1/auth/register", response_model=UserResponse, status_code=201)
async def register(data: UserRegister, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(
        (User.email == data.email) | (User.username == data.username)))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User with this email or username already exists")

    role = UserRole(data.role) if data.role in [r.value for r in UserRole] else UserRole.PASSENGER

    # Generate API key for partner-api accounts
    api_key = generate_api_key() if role == UserRole.PARTNER_API else None

    user = User(
        email=data.email,
        username=data.username,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role=role,
        airport_code=data.airport_code if role == UserRole.AIRPORT_OPERATOR else None,
        airline_code=data.airline_code if role == UserRole.AIRLINE_STAFF else None,
        api_key=api_key,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return _to_user_response(user)


@app.post("/api/v1/auth/login", response_model=TokenResponse)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == data.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    # Include ABAC attributes in JWT claims
    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "username": user.username,
        "role": user.role.value,
        "airport_code": user.airport_code,
        "airline_code": user.airline_code,
    }
    access = create_access_token(token_data, secret=config.jwt_secret,
                                 expires_minutes=config.access_token_expire_minutes)
    refresh = create_refresh_token(token_data, secret=config.jwt_secret,
                                   expires_days=config.refresh_token_expire_days)
    return TokenResponse(access_token=access, refresh_token=refresh,
                         expires_in=config.access_token_expire_minutes * 60,
                         api_key=user.api_key)


@app.post("/api/v1/auth/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(data.refresh_token, secret=config.jwt_secret)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")
    token_data = {
        "sub": payload["sub"], "email": payload.get("email", ""),
        "username": payload["username"], "role": payload["role"],
        "airport_code": payload.get("airport_code"),
        "airline_code": payload.get("airline_code"),
    }
    access = create_access_token(token_data, secret=config.jwt_secret,
                                 expires_minutes=config.access_token_expire_minutes)
    refresh_tok = create_refresh_token(token_data, secret=config.jwt_secret,
                                       expires_days=config.refresh_token_expire_days)
    return TokenResponse(access_token=access, refresh_token=refresh_tok,
                         expires_in=config.access_token_expire_minutes * 60)


@app.get("/api/v1/auth/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == current_user["sub"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _to_user_response(user)


@app.get("/api/v1/auth/validate")
async def validate_token(current_user: dict = Depends(get_current_user)):
    return {
        "valid": True,
        "user_id": current_user["sub"],
        "role": current_user["role"],
        "airport_code": current_user.get("airport_code"),
        "airline_code": current_user.get("airline_code"),
    }


@app.post("/api/v1/auth/validate-api-key")
async def validate_api_key(api_key: str, db: AsyncSession = Depends(get_db)):
    """Validate an API key and return the associated user info."""
    result = await db.execute(select(User).where(User.api_key == api_key))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return {
        "valid": True,
        "user_id": str(user.id),
        "role": user.role.value,
        "rate_limit": 1000,  # Partner APIs get higher rate limit
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
