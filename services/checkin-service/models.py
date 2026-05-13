import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Boolean, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from shared.database import Base
import enum


class CheckInStatus(str, enum.Enum):
    NOT_CHECKED_IN = "not-checked-in"
    CHECKED_IN = "checked-in"
    BOARDING_PASS_ISSUED = "boarding-pass-issued"
    BOARDED = "boarded"


class CheckIn(Base):
    __tablename__ = "checkins"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id = Column(UUID(as_uuid=True), nullable=False, unique=True, index=True)
    flight_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    passenger_name = Column(String(255), nullable=False)
    seat_number = Column(String(10), nullable=True)
    boarding_group = Column(String(5), nullable=True)
    gate = Column(String(10), nullable=True)
    status = Column(SAEnum(CheckInStatus), default=CheckInStatus.CHECKED_IN, nullable=False)
    boarding_pass_url = Column(String(500), nullable=True)
    has_baggage = Column(Boolean, default=False)
    seat_selected_by_user = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
