import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from shared.health import check_db, check_redis
import httpx
import pybreaker
import stripe
import structlog
from shared.config import BaseConfig
from shared.database import create_db_engine, create_session_factory, Base
from shared.auth import get_current_user
from shared.events import EventPublisher
from shared.audit import record_audit
from shared.cache import create_redis_client, redis_get_json, redis_set_json
from shared.resilience import create_circuit_breaker, async_retry, breaker_call_async
from shared.logging import setup_logging
from shared.tracing import TraceMiddleware
from shared.schemas import HealthResponse
from models import Payment, PaymentStatus
from schemas import (PaymentIntentCreate, PaymentIntentResponse,
                     PaymentResponse, RefundRequest)

config = BaseConfig(service_name="payment-service")
setup_logging(config.service_name)
logger = structlog.get_logger()

# ── Stripe configuration ────────────────────────────────────────────────
STRIPE_SECRET_KEY      = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET  = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

if not STRIPE_SECRET_KEY:
    logger.warning("stripe_secret_key_missing — payment intent creation will fail")
stripe.api_key = STRIPE_SECRET_KEY

engine = create_db_engine(config.database_url)
SessionFactory = create_session_factory(engine)
START_TIME = time.time()

redis_client = create_redis_client(config.redis_url)
IDEMPOTENCY_TTL = 86400  # 24h

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

_INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")


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
            pass
        # Drop legacy card/bank/wallet columns no longer in the model
        for col in ("card_token", "card_last_four", "card_holder_name", "card_expiry",
                    "wallet_type", "wallet_account",
                    "bank_account_holder", "bank_account_masked",
                    "bank_routing_number", "bank_name",
                    "payment_method"):
            try:
                await conn.execute(text(
                    f"ALTER TABLE payments DROP COLUMN IF EXISTS {col}"
                ))
            except Exception:
                pass
        # Add new columns for Stripe-driven flow
        await conn.execute(text(
            "ALTER TABLE payments ADD COLUMN IF NOT EXISTS provider VARCHAR(20) NOT NULL DEFAULT 'stripe'"
        ))
        await conn.execute(text(
            "ALTER TABLE payments ADD COLUMN IF NOT EXISTS stripe_payment_intent_id VARCHAR(255)"
        ))
        await conn.execute(text(
            "ALTER TABLE payments ADD COLUMN IF NOT EXISTS payment_method_type VARCHAR(40)"
        ))
        await conn.execute(text(
            "ALTER TABLE payments ADD COLUMN IF NOT EXISTS wallet_brand VARCHAR(40)"
        ))
        await conn.execute(text(
            "ALTER TABLE payments ADD COLUMN IF NOT EXISTS last_four VARCHAR(4)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_payments_stripe_payment_intent_id "
            "ON payments (stripe_payment_intent_id)"
        ))
    yield
    await engine.dispose()


app = FastAPI(title="AeroLink Payment Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(TraceMiddleware)


def _to_response(p: Payment) -> PaymentResponse:
    return PaymentResponse(
        id=str(p.id), booking_id=str(p.booking_id), user_id=str(p.user_id),
        amount=p.amount, currency=p.currency, status=p.status.value,
        provider=p.provider or "stripe", idempotency_key=p.idempotency_key,
        transaction_ref=p.transaction_ref, failure_reason=p.failure_reason,
        stripe_payment_intent_id=p.stripe_payment_intent_id,
        payment_method_type=p.payment_method_type, wallet_brand=p.wallet_brand,
        last_four=p.last_four, created_at=p.created_at,
    )


async def _get_booking(booking_id: str, token: str) -> dict | None:
    async for attempt in async_retry():
        with attempt:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{config.booking_service_url}/api/v1/bookings/{booking_id}",
                    headers={"Authorization": f"Bearer {token}"} if token else {},
                )
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return resp.json()


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
                    headers={"X-Internal-API-Key": _INTERNAL_API_KEY},
                )
                resp.raise_for_status()


@app.get("/health", response_model=HealthResponse)
async def health(db: AsyncSession = Depends(get_db)):
    return HealthResponse(service="payment-service", uptime_seconds=time.time() - START_TIME,
                          dependencies={"database": await check_db(db),
                                        "redis": check_redis(redis_client)})


@app.get("/api/v1/payments/config")
async def payment_config():
    """Expose the publishable key to the frontend so it can mount Stripe.js."""
    return {"publishable_key": STRIPE_PUBLISHABLE_KEY}


# ── Intent creation ─────────────────────────────────────────────────────
@app.post("/api/v1/payments/intent", response_model=PaymentIntentResponse, status_code=201)
async def create_payment_intent(data: PaymentIntentCreate, request: Request,
                                current_user: dict = Depends(get_current_user),
                                db: AsyncSession = Depends(get_db)):
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe is not configured on the server")

    # Idempotency fast-path: Redis-cached intent response
    cache_key = f"intent:{data.idempotency_key}"
    cached = redis_get_json(redis_client, cache_key)
    if cached is not None:
        return cached

    # Look up existing payment by idempotency key — only short-circuit on COMPLETED
    existing = await db.execute(
        select(Payment).where(Payment.idempotency_key == data.idempotency_key))
    existing_payment = existing.scalar_one_or_none()

    if existing_payment and existing_payment.stripe_payment_intent_id:
        if existing_payment.status == PaymentStatus.COMPLETED:
            raise HTTPException(status_code=409, detail="Payment already completed")
        # Reuse existing PaymentIntent — Stripe stores client_secret on the intent
        try:
            intent = stripe.PaymentIntent.retrieve(existing_payment.stripe_payment_intent_id)
            response = PaymentIntentResponse(
                payment_id=str(existing_payment.id),
                client_secret=intent.client_secret,
                publishable_key=STRIPE_PUBLISHABLE_KEY,
                amount=data.amount, currency=data.currency,
            )
            redis_set_json(redis_client, cache_key, response.dict(), IDEMPOTENCY_TTL)
            return response
        except stripe.error.StripeError as e:
            logger.warning("stripe_intent_retrieve_failed", error=str(e))
            # Fall through and create a fresh intent

    # Create a new PaymentIntent at Stripe
    try:
        intent = stripe.PaymentIntent.create(
            amount=int(round(data.amount * 100)),  # cents
            currency=data.currency.lower(),
            automatic_payment_methods={"enabled": True},
            metadata={
                "booking_id":      data.booking_id,
                "user_id":         current_user["sub"],
                "idempotency_key": data.idempotency_key,
            },
            idempotency_key=f"intent_{data.idempotency_key}",
        )
    except stripe.error.StripeError as e:
        logger.error("stripe_intent_create_failed", error=str(e))
        raise HTTPException(status_code=502, detail=f"Stripe error: {str(e)}")

    payment = Payment(
        booking_id=data.booking_id,
        user_id=current_user["sub"],
        amount=data.amount,
        currency=data.currency,
        status=PaymentStatus.PROCESSING,
        idempotency_key=data.idempotency_key,
        provider="stripe",
        stripe_payment_intent_id=intent.id,
    )
    db.add(payment)
    await db.flush()
    await db.refresh(payment)

    client_ip = request.client.host if request.client else None
    await record_audit(db, "payment-service", "payment.intent_created", "payment",
                       resource_id=str(payment.id), actor_id=current_user["sub"],
                       actor_role=current_user.get("role"),
                       detail=f"intent={intent.id}, amount={data.amount} {data.currency}",
                       ip_address=client_ip)

    response = PaymentIntentResponse(
        payment_id=str(payment.id),
        client_secret=intent.client_secret,
        publishable_key=STRIPE_PUBLISHABLE_KEY,
        amount=data.amount, currency=data.currency,
    )
    redis_set_json(redis_client, cache_key, response.dict(), IDEMPOTENCY_TTL)
    return response


# ── Webhook handling ────────────────────────────────────────────────────
async def _mark_completed(payment: Payment, intent: dict, db: AsyncSession) -> None:
    payment.status = PaymentStatus.COMPLETED
    # Surface PCI-safe details from the latest charge, if present
    charges = (intent.get("charges") or {}).get("data") or []
    if charges:
        ch = charges[0]
        payment.transaction_ref = ch.get("id")
        pmd = ch.get("payment_method_details") or {}
        pmt = pmd.get("type")
        payment.payment_method_type = pmt
        # For card / wallet-funded payments Stripe nests card details
        card_block = pmd.get("card") or {}
        if pmt in ("apple_pay", "google_pay", "link"):
            wallet_block = (pmd.get(pmt) or {}) if isinstance(pmd.get(pmt), dict) else {}
            payment.wallet_brand = wallet_block.get("brand") or card_block.get("brand")
            payment.last_four    = wallet_block.get("last4")  or card_block.get("last4")
        elif pmt == "card":
            wallet = card_block.get("wallet") or {}
            wallet_type = wallet.get("type") if isinstance(wallet, dict) else None
            if wallet_type:
                payment.payment_method_type = wallet_type  # apple_pay/google_pay surfaced via card
            payment.wallet_brand = card_block.get("brand")
            payment.last_four    = card_block.get("last4")
    else:
        payment.transaction_ref = intent.get("id")

    await db.flush()


async def _handle_payment_succeeded(intent: dict, db: AsyncSession, request: Request) -> None:
    pi_id = intent.get("id")
    result = await db.execute(
        select(Payment).where(Payment.stripe_payment_intent_id == pi_id))
    payment = result.scalar_one_or_none()
    if not payment:
        logger.warning("webhook_intent_unknown", intent_id=pi_id)
        return
    already_completed = payment.status == PaymentStatus.COMPLETED

    if not already_completed:
        await _mark_completed(payment, intent, db)

        client_ip = request.client.host if request.client else None
        await record_audit(db, "payment-service", "payment.completed", "payment",
                           resource_id=str(payment.id), actor_id=str(payment.user_id),
                           detail=f"TXN: {payment.transaction_ref}, "
                                  f"method: {payment.payment_method_type}",
                           ip_address=client_ip)

    booking_id = str(payment.booking_id)

    if not already_completed:
        # Update booking status (saga — breaker + retry)
        try:
            await breaker_call_async(
                booking_breaker, _update_booking_status, booking_id,
                {"status": "paid", "payment_id": str(payment.id)},
            )
        except pybreaker.CircuitBreakerError:
            logger.warning("booking_status_update_skipped_circuit_open", booking_id=booking_id)
        except Exception as e:
            logger.warning("booking_status_update_failed", booking_id=booking_id, error=str(e))

    # Award loyalty points (skipped on replay — already awarded)
    loyalty_points = max(1, int(payment.amount * 10))
    if not already_completed:
        try:
            await breaker_call_async(passenger_breaker, _award_loyalty,
                                     str(payment.user_id), loyalty_points)
        except Exception as e:
            logger.warning("loyalty_award_failed", user_id=str(payment.user_id), error=str(e))

    # Fetch booking for accurate event payload (best-effort)
    booking_reference = booking_id
    passenger_email   = ""
    passenger_name    = ""
    try:
        bdata = await breaker_call_async(booking_breaker, _get_booking, booking_id, "")
        if bdata:
            booking_reference = bdata.get("booking_reference", booking_reference)
            passenger_email   = bdata.get("passenger_email") or ""
            passenger_name    = bdata.get("passenger_name") or ""
    except Exception:
        pass

    if event_publisher:
        try:
            event_publisher.publish("payment-service", "PaymentCompleted", {
                "payment_id":             str(payment.id),
                "booking_id":             booking_id,
                "booking_reference":      booking_reference,
                "amount":                 payment.amount,
                "currency":               payment.currency,
                "transaction_ref":        payment.transaction_ref,
                "passenger_email":        passenger_email,
                "passenger_name":         passenger_name,
                "loyalty_points_awarded": loyalty_points,
            })
        except Exception as e:
            logger.error("Failed to publish PaymentCompleted event", error=str(e))


async def _handle_payment_failed(intent: dict, db: AsyncSession, request: Request) -> None:
    pi_id = intent.get("id")
    result = await db.execute(
        select(Payment).where(Payment.stripe_payment_intent_id == pi_id))
    payment = result.scalar_one_or_none()
    if not payment:
        logger.warning("webhook_intent_unknown", intent_id=pi_id)
        return
    if payment.status == PaymentStatus.FAILED:
        return

    err = (intent.get("last_payment_error") or {}).get("message") or "Payment declined"
    payment.status = PaymentStatus.FAILED
    payment.failure_reason = err[:500]
    await db.flush()

    client_ip = request.client.host if request.client else None
    await record_audit(db, "payment-service", "payment.failed", "payment",
                       resource_id=str(payment.id), actor_id=str(payment.user_id),
                       detail=f"Reason: {err}", ip_address=client_ip, status="failure")

    if event_publisher:
        try:
            event_publisher.publish("payment-service", "PaymentFailed", {
                "payment_id": str(payment.id),
                "booking_id": str(payment.booking_id),
                "reason":     err,
            })
        except Exception as e:
            logger.error("Failed to publish PaymentFailed event", error=str(e))


@app.post("/api/v1/payments/stripe/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    etype = event["type"]
    obj   = event["data"]["object"]
    logger.info("stripe_webhook_received", event_type=etype, event_id=event.get("id"))

    if etype == "payment_intent.succeeded":
        await _handle_payment_succeeded(obj, db, request)
    elif etype == "payment_intent.payment_failed":
        await _handle_payment_failed(obj, db, request)
    elif etype == "charge.refunded":
        # Optional: keep DB in sync if refund issued via Stripe dashboard
        pi_id = obj.get("payment_intent")
        if pi_id:
            result = await db.execute(
                select(Payment).where(Payment.stripe_payment_intent_id == pi_id))
            payment = result.scalar_one_or_none()
            if payment and payment.status != PaymentStatus.REFUNDED:
                payment.status = PaymentStatus.REFUNDED
                await db.flush()
    else:
        logger.debug("stripe_webhook_ignored", event_type=etype)

    return {"received": True}


# ── Read endpoints ──────────────────────────────────────────────────────
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


# ── Refund ──────────────────────────────────────────────────────────────
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
    if not payment.stripe_payment_intent_id:
        raise HTTPException(status_code=400, detail="Missing Stripe PaymentIntent reference")

    try:
        stripe.Refund.create(
            payment_intent=payment.stripe_payment_intent_id,
            reason="requested_by_customer",
            metadata={"reason_text": data.reason or ""},
        )
    except stripe.error.StripeError as e:
        logger.error("stripe_refund_failed", error=str(e))
        raise HTTPException(status_code=502, detail=f"Stripe refund failed: {str(e)}")

    payment.status = PaymentStatus.REFUNDED
    await db.flush()
    await db.refresh(payment)

    client_ip = request.client.host if request.client else None
    await record_audit(db, "payment-service", "payment.refunded", "payment",
                       resource_id=str(payment.id), actor_id=current_user["sub"],
                       actor_role=current_user.get("role"),
                       detail=f"Amount: {payment.amount} {payment.currency}, Reason: {data.reason}",
                       ip_address=client_ip)

    # Compensating transaction: cancel the booking
    try:
        await breaker_call_async(
            booking_breaker, _update_booking_status, str(payment.booking_id),
            {"status": "cancelled"},
        )
    except pybreaker.CircuitBreakerError:
        logger.warning("refund_booking_cancel_skipped_circuit_open", payment_id=payment_id)
    except Exception as e:
        logger.warning("refund_booking_cancel_failed", payment_id=payment_id, error=str(e))

    if event_publisher:
        try:
            event_publisher.publish("payment-service", "PaymentRefunded", {
                "payment_id":      str(payment.id),
                "booking_id":      str(payment.booking_id),
                "amount":          payment.amount,
                "currency":        payment.currency,
                "passenger_email": current_user.get("email", ""),
                "passenger_name":  current_user.get("username", ""),
            })
        except Exception as e:
            logger.error("Failed to publish PaymentRefunded event", error=str(e))

    return _to_response(payment)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
