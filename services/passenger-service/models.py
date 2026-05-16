import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Integer, Date, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID
from shared.database import Base


class PassengerProfile(Base):
    __tablename__ = "passenger_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, unique=True, index=True)
    first_name = Column(String(100), nullable=False)
    middle_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=False)
    date_of_birth = Column(Date, nullable=True)
    nationality = Column(String(3), nullable=True)
    # PII: encrypted at rest via field-level encryption
    passport_number_encrypted = Column(String(500), nullable=True)
    phone_number = Column(String(20), nullable=True)
    loyalty_tier = Column(String(20), default="bronze")
    loyalty_points = Column(Integer, default=0)
    meal_preference = Column(String(50), nullable=True)
    seat_preference = Column(String(20), nullable=True)
    emergency_contact = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class GDPRConsent(Base):
    """GDPR consent tracking per data processing purpose."""
    __tablename__ = "gdpr_consents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    purpose = Column(String(100), nullable=False)  # e.g. "marketing", "analytics", "flight-operations"
    granted = Column(Boolean, default=False, nullable=False)
    granted_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
