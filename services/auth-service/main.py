import sys
import os
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from shared.health import check_db, check_redis
from sqlalchemy.dialects.postgresql import insert as pg_insert
from shared.config import BaseConfig
from shared.database import create_db_engine, create_session_factory, Base
from shared.auth import (hash_password, verify_password, create_access_token,
                         create_refresh_token, decode_token, get_current_user)
from shared.audit import AuditLog, record_audit
from shared.cache import create_redis_client, redis_incr_with_ttl, redis_delete
from shared.logging import setup_logging
from shared.tracing import TraceMiddleware
from shared.schemas import HealthResponse
from models import User, UserRole
from schemas import (UserRegister, UserLogin, TokenResponse,
                     RefreshRequest, UserResponse)

config = BaseConfig(service_name="auth-service")
setup_logging(config.service_name)

engine = create_db_engine(config.database_url)
SessionFactory = create_session_factory(engine)
START_TIME = time.time()

redis_client = create_redis_client(config.redis_url)

LOGIN_FAIL_TTL   = 300   # 5-minute sliding window
LOGIN_FAIL_LIMIT = 10    # block after 10 failures within the window


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
app.add_middleware(TraceMiddleware)


def _rate_limit_key(username: str) -> str:
    return f"login_fail:{username}"


def _to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=str(user.id), email=user.email, username=user.username,
        full_name=user.full_name, role=user.role.value,
        is_active=user.is_active, created_at=user.created_at,
    )


@app.get("/health", response_model=HealthResponse)
async def health(db: AsyncSession = Depends(get_db)):
    return HealthResponse(service="auth-service", uptime_seconds=time.time() - START_TIME,
                          dependencies={"database": await check_db(db),
                                        "redis": check_redis(redis_client)})


@app.post("/api/v1/auth/register", response_model=UserResponse, status_code=201)
async def register(data: UserRegister, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(
        (User.email == data.email) | (User.username == data.username)))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User with this email or username already exists")

    role = UserRole(data.role) if data.role in [r.value for r in UserRole] else UserRole.PASSENGER

    user = User(
        email=data.email,
        username=data.username,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role=role,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return _to_user_response(user)


@app.post("/api/v1/auth/login", response_model=TokenResponse)
async def login(data: UserLogin, request: Request, db: AsyncSession = Depends(get_db)):
    fail_key = _rate_limit_key(data.username)
    try:
        current_fails = int(redis_client.get(fail_key) or 0) if redis_client else 0
    except Exception:
        current_fails = 0
    if current_fails >= LOGIN_FAIL_LIMIT:
        raise HTTPException(status_code=429, detail="Too many failed login attempts. Try again in 5 minutes.")

    result = await db.execute(select(User).where(User.username == data.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.hashed_password):
        redis_incr_with_ttl(redis_client, fail_key, LOGIN_FAIL_TTL)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    # Successful login: clear the failure counter
    redis_delete(redis_client, fail_key)

    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "username": user.username,
        "role": user.role.value,
    }
    access = create_access_token(token_data, secret=config.jwt_secret,
                                 expires_minutes=config.access_token_expire_minutes)
    refresh = create_refresh_token(token_data, secret=config.jwt_secret,
                                   expires_days=config.refresh_token_expire_days)
    return TokenResponse(access_token=access, refresh_token=refresh,
                         expires_in=config.access_token_expire_minutes * 60)


@app.post("/api/v1/auth/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(data.refresh_token, secret=config.jwt_secret)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")
    token_data = {
        "sub": payload["sub"], "email": payload.get("email", ""),
        "username": payload["username"], "role": payload["role"],
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


@app.post("/api/v1/auth/cognito-sync", response_model=UserResponse, status_code=200)
async def cognito_sync(current_user: dict = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    """Upsert the Cognito user into the local users table.

    Called by the frontend on every login so that a DB record exists for new
    Cognito sign-ups before any other service tries to reference users.id.
    """
    role_str = current_user.get("role", "passenger")
    role = UserRole(role_str) if role_str in [r.value for r in UserRole] else UserRole.PASSENGER

    stmt = (
        pg_insert(User)
        .values(
            id=uuid.UUID(current_user["sub"]),
            email=current_user.get("email", ""),
            username=current_user.get("username", current_user["sub"]),
            full_name=current_user.get("full_name", "") or current_user.get("username", ""),
            hashed_password="!cognito-sso",  # placeholder; Cognito users never use password auth
            role=role,
            is_active=True,
        )
        .on_conflict_do_update(
            index_elements=["id"],
            set_=dict(
                email=current_user.get("email", ""),
                full_name=current_user.get("full_name", "") or current_user.get("username", ""),
                role=role,
            ),
        )
        .returning(User)
    )
    result = await db.execute(stmt)
    user = result.scalar_one()
    return _to_user_response(user)


@app.get("/api/v1/auth/validate")
async def validate_token(current_user: dict = Depends(get_current_user)):
    return {
        "valid": True,
        "user_id": current_user["sub"],
        "role": current_user["role"],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
