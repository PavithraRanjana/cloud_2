import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Float, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from shared.database import Base
import enum


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default="USD")
    status = Column(SAEnum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)
    idempotency_key = Column(String(255), unique=True, nullable=False, index=True)
    transaction_ref = Column(String(255), nullable=True)  # Stripe charge id
    failure_reason = Column(String(500), nullable=True)

    # Stripe-managed payment data
    provider = Column(String(20), default="stripe", nullable=False)
    stripe_payment_intent_id = Column(String(255), nullable=True, index=True)
    payment_method_type = Column(String(40), nullable=True)  # card | apple_pay | google_pay | link | …
    wallet_brand = Column(String(40), nullable=True)         # visa | mastercard | … (PCI-safe brand only)
    last_four = Column(String(4), nullable=True)             # PCI-safe; Stripe surfaces this directly

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
