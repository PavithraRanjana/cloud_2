from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class CheckInRequest(BaseModel):
    booking_id: str
    flight_id: str
    passenger_name: str
    seat_preference: Optional[str] = None
    seat_selected_by_user: Optional[bool] = True


class CheckInResponse(BaseModel):
    id: str
    booking_id: str
    flight_id: str
    passenger_name: str
    seat_number: str
    boarding_group: str
    gate: Optional[str]
    status: str
    boarding_pass_url: Optional[str]
    has_baggage: bool
    seat_selected_by_user: bool
    created_at: datetime

    class Config:
        from_attributes = True
