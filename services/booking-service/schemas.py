from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class BookingCreate(BaseModel):
    flight_id: str
    passenger_name: str = Field(..., min_length=1)
    passenger_email: str = Field(..., min_length=5)
    cabin_class: str = "economy"
    num_passengers: int = Field(1, ge=1, le=9)
    special_requests: Optional[str] = None
    trip_type: str = "one_way"              # one_way | return
    group_booking_id: Optional[str] = None  # UUID linking both legs of a return trip


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

    class Config:
        from_attributes = True


class BookingStatusUpdate(BaseModel):
    status: str
    payment_id: Optional[str] = None
