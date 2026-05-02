import uuid
import secrets
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Boolean, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from shared.database import Base
import enum


class UserRole(str, enum.Enum):
    PASSENGER = "passenger"
    AIRLINE_STAFF = "airline-staff"
    AIRPORT_OPERATOR = "airport-operator"
    ADMIN = "admin"
    PARTNER_API = "partner-api"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(SAEnum(UserRole), default=UserRole.PASSENGER, nullable=False)
    is_active = Column(Boolean, default=True)
    # ABAC: attribute-based access control fields
    airport_code = Column(String(3), nullable=True)  # for airport-operator: restricts to their airport
    airline_code = Column(String(3), nullable=True)  # for airline-staff: restricts to their airline
    # API key for partner-api role
    api_key = Column(String(64), unique=True, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    token_hash = Column(String(255), nullable=False, unique=True)
    is_revoked = Column(Boolean, default=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


def generate_api_key() -> str:
    """Generate a secure API key for partner-api accounts."""
    return f"ak_{secrets.token_hex(28)}"
