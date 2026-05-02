from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class BaggageRegister(BaseModel):
    booking_id: str
    flight_id: str
    passenger_name: str
    weight_kg: float = Field(0.0, ge=0, le=50)
    description: Optional[str] = None


class BaggageResponse(BaseModel):
    id: str
    tag_number: str
    booking_id: str
    passenger_name: str
    flight_id: str
    weight_kg: float
    status: str
    last_location: Optional[str]
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class BaggageStatusUpdate(BaseModel):
    status: str
    location: Optional[str] = None
