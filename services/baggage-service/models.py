import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Float, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from shared.database import Base
import enum


class BaggageStatus(str, enum.Enum):
    REGISTERED = "registered"
    CHECKED_IN = "checked-in"
    SECURITY_CLEARED = "security-cleared"
    LOADED = "loaded"
    IN_TRANSIT = "in-transit"
    ARRIVED = "arrived"
    ON_CAROUSEL = "on-carousel"
    COLLECTED = "collected"
    LOST = "lost"
    FOUND = "found"


class Baggage(Base):
    __tablename__ = "baggage"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tag_number = Column(String(20), unique=True, nullable=False, index=True)
    booking_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    passenger_name = Column(String(255), nullable=False)
    passenger_email = Column(String(255), nullable=True)
    flight_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    weight_kg = Column(Float, default=0.0)
    status = Column(SAEnum(BaggageStatus), default=BaggageStatus.REGISTERED, nullable=False)
    last_location = Column(String(255), nullable=True)
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
