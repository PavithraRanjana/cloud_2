import sys
import os
import time
import uuid
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx
import pybreaker
import boto3
import structlog
from shared.config import BaseConfig
from shared.database import create_db_engine, create_session_factory, Base
from shared.auth import get_current_user
from shared.events import EventPublisher
from shared.encryption import tokenize_card, mask_card_number
from shared.audit import AuditLog, record_audit
from shared.cache import create_redis_client, redis_set_nx, redis_get_json, redis_set_json
from shared.resilience import create_circuit_breaker, async_retry
from shared.logging import setup_logging
from shared.schemas import HealthResponse
from models import Payment, PaymentStatus, PaymentMethod
from schemas import PaymentCreate, PaymentResponse, RefundRequest

config = BaseConfig(service_name="payment-service")
setup_logging(config.service_name)
logger = structlog.get_logger()

engine = create_db_engine(config.database_url)
SessionFactory = create_session_factory(engine)
START_TIME = time.time()

redis_client = create_redis_client(config.redis_url)
IDEMPOTENCY_TTL = 86400  # 24 hours — matches DynamoDB TTL

booking_breaker   = create_circuit_breaker("booking-service")
passenger_breaker = create_circuit_breaker("passenger-service")

event_publisher = None
try:
    event_publisher = EventPublisher(
        endpoint_url=config.aws_endpoint_url, region=config.aws_region,
        bus_name=config.event_bus_name,
    )
except Exception:
    pass

# DynamoDB client for idempotency key fast-path (pre-check before PostgreSQL hit)
_dynamo = None
try:
    _dynamo = boto3.client(
        "dynamodb",
        endpoint_url=config.aws_endpoint_url,
        region_name=config.aws_region,
        aws_access_key_id=config.aws_access_key_id,
        aws_secret_access_key=config.aws_secret_access_key,
    )
    _dynamo.describe_table(TableName="payment-idempotency")
    logger.info("dynamodb_idempotency_connected")
except Exception as e:
    logger.warning("dynamodb_idempotency_unavailable", error=str(e))
    _dynamo = None


def _dynamo_check(key: str) -> bool:
    """Return True if this idempotency key has already been processed."""
    if not _dynamo:
        return False
    try:
        resp = _dynamo.get_item(
            TableName="payment-idempotency",
            Key={"idempotency_key": {"S": key}},
        )
        return "Item" in resp
    except Exception:
        return False


def _dynamo_record(key: str, payment_id: str):
    """Write idempotency key to DynamoDB with 24-hour TTL."""
    if not _dynamo:
        return
    try:
        ttl = int(time.time()) + 86400
        _dynamo.put_item(
            TableName="payment-idempotency",
            Item={
                "idempotency_key": {"S": key},
                "payment_id": {"S": payment_id},
                "ttl": {"N": str(ttl)},
            },
            ConditionExpression="attribute_not_exists(idempotency_key)",
        )
    except Exception:
        pass


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


app = FastAPI(title="AeroLink Payment Service", version="1.0.0", lifespan=lifespan)


def _to_response(p: Payment) -> PaymentResponse:
    return PaymentResponse(
        id=str(p.id), booking_id=str(p.booking_id), user_id=str(p.user_id),
        amount=p.amount, currency=p.currency, status=p.status.value,
        payment_method=p.payment_method.value, idempotency_key=p.idempotency_key,
        transaction_ref=p.transaction_ref, failure_reason=p.failure_reason,
        card_token=p.card_token, card_last_four=p.card_last_four,
        card_holder_name=p.card_holder_name, card_expiry=p.card_expiry,
        wallet_type=p.wallet_type, wallet_account=p.wallet_account,
        bank_account_holder=p.bank_account_holder, bank_account_masked=p.bank_account_masked,
        bank_routing_number=p.bank_routing_number, bank_name=p.bank_name,
        created_at=p.created_at,
    )


async def _get_booking(booking_id: str, token: str) -> dict | None:
    async for attempt in async_retry():
        with attempt:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{config.booking_service_url}/api/v1/bookings/{booking_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code == 200:
                    return resp.json()
                return None


async def _update_booking_status(booking_id: str, payload: dict) -> None:
    async for attempt in async_retry():
        with attempt:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.put(
                    f"{config.booking_service_url}/api/v1/bookings/{booking_id}/status",
                    json=payload,
                )
                resp.raise_for_status()


async def _award_loyalty(user_id: str, points: int) -> None:
    async for attempt in async_retry():
        with attempt:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{config.passenger_service_url}/api/v1/passengers/loyalty/award",
                    json={"user_id": user_id, "points": points},
                )
                resp.raise_for_status()


def simulate_payment_processing() -> tuple[bool, str]:
    """Simulate payment gateway - 95% success rate."""
    if random.random() < 0.95:
        return True, f"TXN-{uuid.uuid4().hex[:12].upper()}"
    return False, "Payment declined by issuing bank"


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(service="payment-service", uptime_seconds=time.time() - START_TIME,
                          dependencies={"database": "healthy",
                                        "redis": "healthy" if redis_client else "unavailable"})


@app.post("/api/v1/payments", response_model=PaymentResponse, status_code=201)
async def process_payment(data: PaymentCreate, request: Request,
                          current_user: dict = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    # Idempotency fast-path: Redis (fastest) → DynamoDB → PostgreSQL
    redis_idem_key = f"idem:{data.idempotency_key}"
    cached_payment = redis_get_json(redis_client, redis_idem_key)
    if cached_payment is not None:
        return cached_payment

    # DynamoDB pre-check (avoids PostgreSQL hit for dupes)
    if _dynamo_check(data.idempotency_key):
        existing = await db.execute(
            select(Payment).where(Payment.idempotency_key == data.idempotency_key))
        existing_payment = existing.scalar_one_or_none()
        if existing_payment:
            return _to_response(existing_payment)

    # Idempotency check via PostgreSQL (authoritative)
    existing = await db.execute(
        select(Payment).where(Payment.idempotency_key == data.idempotency_key))
    existing_payment = existing.scalar_one_or_none()
    if existing_payment:
        await record_audit(db, "payment-service", "payment.idempotent_hit", "payment",
                           resource_id=str(existing_payment.id),
                           actor_id=current_user["sub"], actor_role=current_user.get("role"),
                           detail=f"Idempotency key reused: {data.idempotency_key}")
        _dynamo_record(data.idempotency_key, str(existing_payment.id))
        return _to_response(existing_payment)

    # PCI-DSS: Tokenize card number; CVV validated in schema but NEVER stored
    card_raw = (data.card_number or "").replace(" ", "")
    card_tok = tokenize_card(card_raw) if card_raw else None
    last_four = card_raw[-4:] if len(card_raw) >= 4 else None

    # Wallet: mask account identifier for storage
    wallet_account_stored: str | None = None
    if data.wallet_email:
        local, domain = data.wallet_email.split("@", 1)
        wallet_account_stored = local[:2] + "***@" + domain
    elif data.wallet_phone:
        wallet_account_stored = "***" + data.wallet_phone[-4:]

    # Bank: store last-4 of account number only
    bank_masked: str | None = None
    if data.bank_account_number:
        acct = data.bank_account_number.replace(" ", "")
        bank_masked = "****" + acct[-4:]

    payment = Payment(
        booking_id=data.booking_id,
        user_id=current_user["sub"],
        amount=data.amount,
        currency=data.currency,
        status=PaymentStatus.PROCESSING,
        payment_method=PaymentMethod(data.payment_method),
        idempotency_key=data.idempotency_key,
        card_token=card_tok,
        card_last_four=last_four,
        card_holder_name=data.card_holder_name,
        card_expiry=data.card_expiry,
        wallet_type=data.wallet_type,
        wallet_account=wallet_account_stored,
        bank_account_holder=data.bank_account_holder,
        bank_account_masked=bank_masked,
        bank_routing_number=data.bank_routing_number,
        bank_name=data.bank_name,
    )
    db.add(payment)
    await db.flush()

    # Audit: payment initiated
    client_ip = request.client.host if request.client else None
    await record_audit(db, "payment-service", "payment.initiated", "payment",
                       resource_id=str(payment.id), actor_id=current_user["sub"],
                       actor_role=current_user.get("role"),
                       detail=f"Amount: {data.amount} {data.currency}, Booking: {data.booking_id}",
                       ip_address=client_ip)

    # Simulate payment processing
    success, result = simulate_payment_processing()

    if success:
        payment.status = PaymentStatus.COMPLETED
        payment.transaction_ref = result
        # Record in Redis (fastest) and DynamoDB for idempotency
        response_data = _to_response(payment)
        redis_set_json(redis_client, redis_idem_key, response_data.dict(), IDEMPOTENCY_TTL)
        _dynamo_record(data.idempotency_key, str(payment.id))

        # Audit: payment succeeded
        await record_audit(db, "payment-service", "payment.completed", "payment",
                           resource_id=str(payment.id), actor_id=current_user["sub"],
                           actor_role=current_user.get("role"),
                           detail=f"TXN: {result}, Amount: {data.amount} {data.currency}",
                           ip_address=client_ip)

        # Fetch booking details for accurate event payload (best-effort, breaker-protected)
        booking_reference = data.booking_id  # fallback
        passenger_name    = current_user.get("full_name") or current_user.get("username", "")
        passenger_email   = current_user.get("email", "")
        try:
            bdata = await booking_breaker.call_async(
                _get_booking, data.booking_id, current_user.get("_token", "")
            )
            if bdata:
                booking_reference = bdata.get("booking_reference", booking_reference)
                passenger_name    = bdata.get("passenger_name") or passenger_name
                passenger_email   = bdata.get("passenger_email") or passenger_email
        except Exception:
            pass

        # Update booking status via saga (circuit breaker + retry)
        try:
            await booking_breaker.call_async(
                _update_booking_status, data.booking_id,
                {"status": "paid", "payment_id": str(payment.id)}
            )
        except pybreaker.CircuitBreakerError:
            logger.warning("booking_status_update_skipped_circuit_open", booking_id=data.booking_id)
        except Exception:
            logger.warning("booking_status_update_failed", booking_id=data.booking_id)

        # Award loyalty points (best-effort, breaker-protected)
        loyalty_points = max(1, int(data.amount * 10))
        try:
            await passenger_breaker.call_async(_award_loyalty, current_user["sub"], loyalty_points)
        except Exception:
            pass

        if event_publisher:
            try:
                event_publisher.publish("payment-service", "PaymentCompleted", {
                    "payment_id": str(payment.id),
                    "booking_id": data.booking_id,
                    "booking_reference": booking_reference,
                    "amount": data.amount,
                    "currency": data.currency,
                    "transaction_ref": result,
                    "passenger_email": passenger_email,
                    "passenger_name": passenger_name,
                    "loyalty_points_awarded": loyalty_points,
                })
            except Exception:
                pass
    else:
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = result

        # Audit: payment failed
        await record_audit(db, "payment-service", "payment.failed", "payment",
                           resource_id=str(payment.id), actor_id=current_user["sub"],
                           actor_role=current_user.get("role"),
                           detail=f"Reason: {result}", ip_address=client_ip, status="failure")

        if event_publisher:
            try:
                event_publisher.publish("payment-service", "PaymentFailed", {
                    "payment_id": str(payment.id),
                    "booking_id": data.booking_id,
                    "reason": result,
                })
            except Exception:
                pass

    await db.flush()
    await db.refresh(payment)
    return _to_response(payment)


@app.get("/api/v1/payments/{payment_id}", response_model=PaymentResponse)
async def get_payment(payment_id: str, current_user: dict = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return _to_response(payment)


@app.get("/api/v1/payments/booking/{booking_id}", response_model=list[PaymentResponse])
async def get_payments_by_booking(booking_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Payment).where(Payment.booking_id == booking_id))
    return [_to_response(p) for p in result.scalars().all()]


@app.post("/api/v1/payments/{payment_id}/refund", response_model=PaymentResponse)
async def refund_payment(payment_id: str, data: RefundRequest, request: Request,
                         current_user: dict = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status != PaymentStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Can only refund completed payments")

    payment.status = PaymentStatus.REFUNDED
    await db.flush()
    await db.refresh(payment)

    # Audit: refund processed
    client_ip = request.client.host if request.client else None
    await record_audit(db, "payment-service", "payment.refunded", "payment",
                       resource_id=str(payment.id), actor_id=current_user["sub"],
                       actor_role=current_user.get("role"),
                       detail=f"Amount: {payment.amount} {payment.currency}, Reason: {data.reason}",
                       ip_address=client_ip)

    # Compensating transaction: cancel the booking (circuit breaker + retry)
    try:
        await booking_breaker.call_async(
            _update_booking_status, str(payment.booking_id), {"status": "cancelled"}
        )
    except pybreaker.CircuitBreakerError:
        logger.warning("refund_booking_cancel_skipped_circuit_open", payment_id=payment_id)
    except Exception:
        logger.warning("refund_booking_cancel_failed", payment_id=payment_id)

    if event_publisher:
        try:
            event_publisher.publish("payment-service", "PaymentRefunded", {
                "payment_id": str(payment.id),
                "booking_id": str(payment.booking_id),
                "amount": payment.amount,
                "currency": payment.currency,
                "passenger_email": current_user.get("email", ""),
                "passenger_name": current_user.get("username", ""),
            })
        except Exception:
            pass

    return _to_response(payment)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
