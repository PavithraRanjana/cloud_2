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
from shared.config import BaseConfig
from shared.database import create_db_engine, create_session_factory, Base
from shared.auth import get_current_user
from shared.events import EventPublisher
from shared.encryption import tokenize_card, mask_card_number
from shared.audit import AuditLog, record_audit
from shared.logging import setup_logging
from shared.schemas import HealthResponse
from models import Payment, PaymentStatus, PaymentMethod
from schemas import PaymentCreate, PaymentResponse, RefundRequest

config = BaseConfig(service_name="payment-service")
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
        created_at=p.created_at,
    )


def simulate_payment_processing() -> tuple[bool, str]:
    """Simulate payment gateway - 95% success rate."""
    if random.random() < 0.95:
        return True, f"TXN-{uuid.uuid4().hex[:12].upper()}"
    return False, "Payment declined by issuing bank"


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(service="payment-service", uptime_seconds=time.time() - START_TIME,
                          dependencies={"database": "healthy"})


@app.post("/api/v1/payments", response_model=PaymentResponse, status_code=201)
async def process_payment(data: PaymentCreate, request: Request,
                          current_user: dict = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    # Idempotency check - return existing payment if same key
    existing = await db.execute(
        select(Payment).where(Payment.idempotency_key == data.idempotency_key))
    existing_payment = existing.scalar_one_or_none()
    if existing_payment:
        await record_audit(db, "payment-service", "payment.idempotent_hit", "payment",
                           resource_id=str(existing_payment.id),
                           actor_id=current_user["sub"], actor_role=current_user.get("role"),
                           detail=f"Idempotency key reused: {data.idempotency_key}")
        return _to_response(existing_payment)

    # PCI-DSS: Tokenize card data - NEVER store raw card numbers
    card_tok = tokenize_card(data.card_number) if data.card_number else None
    last_four = data.card_number[-4:] if data.card_number and len(data.card_number) >= 4 else None

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

        # Audit: payment succeeded
        await record_audit(db, "payment-service", "payment.completed", "payment",
                           resource_id=str(payment.id), actor_id=current_user["sub"],
                           actor_role=current_user.get("role"),
                           detail=f"TXN: {result}, Amount: {data.amount} {data.currency}",
                           ip_address=client_ip)

        # Update booking status via saga
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.put(
                    f"{config.booking_service_url}/api/v1/bookings/{data.booking_id}/status",
                    json={"status": "paid", "payment_id": str(payment.id)}
                )
        except Exception:
            pass

        if event_publisher:
            try:
                event_publisher.publish("payment-service", "PaymentProcessed", {
                    "payment_id": str(payment.id),
                    "booking_id": data.booking_id,
                    "amount": data.amount,
                    "currency": data.currency,
                    "transaction_ref": result,
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

    # Compensating transaction: update booking to refunded
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.put(
                f"{config.booking_service_url}/api/v1/bookings/{payment.booking_id}/status",
                json={"status": "refunded"}
            )
    except Exception:
        pass

    if event_publisher:
        try:
            event_publisher.publish("payment-service", "PaymentRefunded", {
                "payment_id": str(payment.id),
                "booking_id": str(payment.booking_id),
                "amount": payment.amount,
            })
        except Exception:
            pass

    return _to_response(payment)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
