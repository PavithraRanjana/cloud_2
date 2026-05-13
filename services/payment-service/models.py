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


class PaymentMethod(str, enum.Enum):
    CREDIT_CARD = "credit-card"
    DEBIT_CARD = "debit-card"
    BANK_TRANSFER = "bank-transfer"
    WALLET = "wallet"


class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default="EUR")
    status = Column(SAEnum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)
    payment_method = Column(SAEnum(PaymentMethod), default=PaymentMethod.CREDIT_CARD)
    idempotency_key = Column(String(255), unique=True, nullable=False, index=True)
    transaction_ref = Column(String(255), nullable=True)
    failure_reason = Column(String(500), nullable=True)
    # PCI-DSS: tokenized card reference (never store raw card numbers, never store CVV)
    card_token = Column(String(100), nullable=True)
    card_last_four = Column(String(4), nullable=True)
    card_holder_name = Column(String(255), nullable=True)
    card_expiry = Column(String(7), nullable=True)          # MM/YY – month+year only
    # Wallet
    wallet_type = Column(String(20), nullable=True)
    wallet_account = Column(String(255), nullable=True)     # masked email or phone
    # Bank transfer
    bank_account_holder = Column(String(255), nullable=True)
    bank_account_masked = Column(String(20), nullable=True) # last-4 only
    bank_routing_number = Column(String(20), nullable=True)
    bank_name = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
