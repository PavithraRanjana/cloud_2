from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, date


class BookingCreate(BaseModel):
    flight_id: str
    passenger_name: str = Field(..., min_length=1)
    passenger_email: str = Field(..., min_length=5)
    cabin_class: str = "economy"
    num_passengers: int = Field(1, ge=1, le=9)
    special_requests: Optional[str] = None
    trip_type: str = "one_way"
    group_booking_id: Optional[str] = None
    seat_number: Optional[str] = None
    # Passenger identity
    title: Optional[str] = None
    gender: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    nationality: Optional[str] = None
    passport_number: Optional[str] = None
    passport_expiry: Optional[date] = None
    # Contact
    country_code: Optional[str] = None
    phone_number: Optional[str] = None


class BookingResponse(BaseModel):
    id: str
    booking_reference: str
    user_id: str
    flight_id: str
    passenger_name: str
    passenger_email: str
    cabin_class: str
    num_passengers: int
    total_price: float
    status: str
    payment_id: Optional[str]
    seat_numbers: Optional[str]
    special_requests: Optional[str]
    trip_type: str
    group_booking_id: Optional[str]
    created_at: datetime
    # Passenger identity
    title: Optional[str] = None
    gender: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    nationality: Optional[str] = None
    passport_number: Optional[str] = None
    passport_expiry: Optional[date] = None
    # Contact
    country_code: Optional[str] = None
    phone_number: Optional[str] = None

    class Config:
        from_attributes = True


class BookingStatusUpdate(BaseModel):
    status: str
    payment_id: Optional[str] = None


class SeatAvailabilityResponse(BaseModel):
    booked_seats: list[str]
