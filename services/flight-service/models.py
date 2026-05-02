import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Float, Integer, Date, Time, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from shared.database import Base
import enum


class FlightStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    BOARDING = "boarding"
    DEPARTED = "departed"
    IN_FLIGHT = "in-flight"
    LANDED = "landed"
    ARRIVED = "arrived"
    CANCELLED = "cancelled"
    DELAYED = "delayed"


class Flight(Base):
    __tablename__ = "flights"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    flight_number = Column(String(10), nullable=False, index=True)
    airline = Column(String(100), nullable=False)
    origin = Column(String(3), nullable=False, index=True)
    destination = Column(String(3), nullable=False, index=True)
    departure_date = Column(Date, nullable=False, index=True)
    departure_time = Column(Time, nullable=False)
    arrival_date = Column(Date, nullable=False)
    arrival_time = Column(Time, nullable=False)
    status = Column(SAEnum(FlightStatus), default=FlightStatus.SCHEDULED, nullable=False)
    aircraft_type = Column(String(50))
    total_seats_economy = Column(Integer, default=150)
    total_seats_business = Column(Integer, default=30)
    total_seats_first = Column(Integer, default=10)
    available_seats_economy = Column(Integer, default=150)
    available_seats_business = Column(Integer, default=30)
    available_seats_first = Column(Integer, default=10)
    price_economy = Column(Float, default=199.99)
    price_business = Column(Float, default=599.99)
    price_first = Column(Float, default=1299.99)
    gate = Column(String(10))
    terminal = Column(String(10))
    # Optimistic locking: prevents double-booking via version check
    version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
