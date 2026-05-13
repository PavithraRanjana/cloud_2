import re
from pydantic import BaseModel, Field, model_validator
from typing import Optional
from datetime import datetime, date


class PaymentCreate(BaseModel):
    booking_id: str
    amount: float = Field(..., gt=0)
    currency: str = "USD"
    payment_method: str = "credit-card"
    idempotency_key: str

    # ── Card fields (credit-card / debit-card) ──────────────────────────────
    card_number: Optional[str] = None       # tokenised immediately, never stored raw
    card_holder_name: Optional[str] = None
    card_expiry: Optional[str] = None       # MM/YY  – month+year stored, CVV never stored
    card_cvv: Optional[str] = None          # validated here, NEVER persisted (PCI-DSS)

    # ── Digital wallet fields ────────────────────────────────────────────────
    wallet_type: Optional[str] = None       # paypal | google_pay | apple_pay | samsung_pay
    wallet_email: Optional[str] = None
    wallet_phone: Optional[str] = None

    # ── Bank transfer fields ─────────────────────────────────────────────────
    bank_account_holder: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None   # only last-4 stored
    bank_routing_number: Optional[str] = None   # routing (US) / sort code (UK)

    @model_validator(mode="after")
    def validate_by_payment_method(self) -> "PaymentCreate":
        method = self.payment_method

        if method in ("credit-card", "debit-card"):
            missing = [
                label for label, val in [
                    ("card_holder_name", self.card_holder_name),
                    ("card_number",      self.card_number),
                    ("card_expiry",      self.card_expiry),
                    ("card_cvv",         self.card_cvv),
                ]
                if not val
            ]
            if missing:
                raise ValueError(f"Missing required card fields: {', '.join(missing)}")

            # Expiry format and not-in-the-past
            if self.card_expiry:
                if not re.match(r"^\d{2}/\d{2}$", self.card_expiry):
                    raise ValueError("card_expiry must be MM/YY")
                mm, yy = self.card_expiry.split("/")
                exp_month, exp_year = int(mm), 2000 + int(yy)
                today = date.today()
                if exp_year < today.year or (exp_year == today.year and exp_month < today.month):
                    raise ValueError("Card has expired")
                if not (1 <= exp_month <= 12):
                    raise ValueError("Invalid expiry month")

            # CVV length: Amex = 4 digits, others = 3
            if self.card_cvv:
                card_num = (self.card_number or "").replace(" ", "")
                is_amex = card_num.startswith("34") or card_num.startswith("37")
                expected_len = 4 if is_amex else 3
                if not re.match(r"^\d{3,4}$", self.card_cvv):
                    raise ValueError("CVV must be 3 or 4 digits")
                if len(self.card_cvv) != expected_len:
                    raise ValueError(f"CVV must be {expected_len} digits for this card type")

        elif method == "wallet":
            if not self.wallet_type:
                raise ValueError("wallet_type is required (paypal, google_pay, apple_pay, samsung_pay)")
            if self.wallet_type in ("paypal", "google_pay"):
                if not self.wallet_email:
                    raise ValueError(f"wallet_email is required for {self.wallet_type}")
                if not re.match(r"^[^@]+@[^@]+\.[^@]+$", self.wallet_email):
                    raise ValueError("wallet_email is not a valid email address")
            elif self.wallet_type in ("apple_pay", "samsung_pay"):
                if not self.wallet_phone and not self.wallet_email:
                    raise ValueError(f"wallet_phone or wallet_email is required for {self.wallet_type}")

        elif method == "bank-transfer":
            missing = [
                label for label, val in [
                    ("bank_account_holder", self.bank_account_holder),
                    ("bank_name",           self.bank_name),
                    ("bank_account_number", self.bank_account_number),
                    ("bank_routing_number", self.bank_routing_number),
                ]
                if not val
            ]
            if missing:
                raise ValueError(f"Missing required bank transfer fields: {', '.join(missing)}")
            if not re.match(r"^\d{6,17}$", (self.bank_account_number or "").replace(" ", "")):
                raise ValueError("bank_account_number must be 6–17 digits")

        return self


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
    # Card (PCI-safe fields only)
    card_holder_name: Optional[str] = None
    card_last_four: Optional[str] = None
    card_expiry: Optional[str] = None
    card_token: Optional[str] = None
    # Wallet
    wallet_type: Optional[str] = None
    wallet_account: Optional[str] = None   # masked
    # Bank
    bank_account_holder: Optional[str] = None
    bank_account_masked: Optional[str] = None
    bank_routing_number: Optional[str] = None
    bank_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class RefundRequest(BaseModel):
    reason: Optional[str] = "Customer requested refund"
