import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Float, Integer, Enum as SAEnum, Text
from sqlalchemy.dialects.postgresql import UUID
from shared.database import Base
import enum


class BookingStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PAYMENT_PENDING = "payment-pending"
    PAID = "paid"
    CHECKED_IN = "checked-in"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_reference = Column(String(10), unique=True, nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    flight_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    passenger_name = Column(String(255), nullable=False)
    passenger_email = Column(String(255), nullable=False)
    cabin_class = Column(String(20), nullable=False, default="economy")
    num_passengers = Column(Integer, default=1)
    total_price = Column(Float, nullable=False)
    status = Column(SAEnum(BookingStatus), default=BookingStatus.PENDING, nullable=False)
    payment_id = Column(UUID(as_uuid=True), nullable=True)
    seat_numbers = Column(Text, nullable=True)
    special_requests = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
