from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class PaymentCreate(BaseModel):
    booking_id: str
    amount: float = Field(..., gt=0)
    currency: str = "EUR"
    payment_method: str = "credit-card"
    idempotency_key: str
    # PCI-DSS: card number is accepted but NEVER stored - only tokenized
    card_number: Optional[str] = None


class PaymentResponse(BaseModel):
    id: str
    booking_id: str
    user_id: str
    amount: float
    currency: str
    status: str
    payment_method: str
    idempotency_key: str
    transaction_ref: Optional[str]
    failure_reason: Optional[str]
    # PCI-DSS: only token and last 4 digits exposed, never full card
    card_token: Optional[str] = None
    card_last_four: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class RefundRequest(BaseModel):
    reason: Optional[str] = "Customer requested refund"
