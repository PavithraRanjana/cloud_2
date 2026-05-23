from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class PaymentIntentCreate(BaseModel):
    """Client requests a PaymentIntent before confirming via Stripe.js."""
    booking_id: str
    amount: float = Field(..., gt=0)
    currency: str = "USD"
    idempotency_key: str


class PaymentIntentResponse(BaseModel):
    """Returned to the client so Stripe.js can mount a PaymentElement."""
    payment_id: str
    client_secret: str
    publishable_key: str
    amount: float
    currency: str


class PaymentResponse(BaseModel):
    id: str
    booking_id: str
    user_id: str
    amount: float
    currency: str
    status: str
    provider: str
    idempotency_key: str
    transaction_ref: Optional[str]
    failure_reason: Optional[str]
    stripe_payment_intent_id: Optional[str]
    payment_method_type: Optional[str]
    wallet_brand: Optional[str]
    last_four: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class RefundRequest(BaseModel):
    reason: Optional[str] = "Customer requested refund"
