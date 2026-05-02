from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, time, datetime


class FlightCreate(BaseModel):
    flight_number: str = Field(..., min_length=2, max_length=10)
    airline: str = Field(..., min_length=1)
    origin: str = Field(..., min_length=3, max_length=3)
    destination: str = Field(..., min_length=3, max_length=3)
    departure_date: date
    departure_time: time
    arrival_date: date
    arrival_time: time
    aircraft_type: Optional[str] = None
    total_seats_economy: int = 150
    total_seats_business: int = 30
    total_seats_first: int = 10
    price_economy: float = 199.99
    price_business: float = 599.99
    price_first: float = 1299.99
    gate: Optional[str] = None
    terminal: Optional[str] = None


class FlightUpdate(BaseModel):
    status: Optional[str] = None
    gate: Optional[str] = None
    terminal: Optional[str] = None
    departure_time: Optional[time] = None
    arrival_time: Optional[time] = None
    price_economy: Optional[float] = None
    price_business: Optional[float] = None
    price_first: Optional[float] = None


class FlightResponse(BaseModel):
    id: str
    flight_number: str
    airline: str
    origin: str
    destination: str
    departure_date: date
    departure_time: time
    arrival_date: date
    arrival_time: time
    status: str
    aircraft_type: Optional[str]
    available_seats_economy: int
    available_seats_business: int
    available_seats_first: int
    price_economy: float
    price_business: float
    price_first: float
    gate: Optional[str]
    terminal: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class SeatUpdate(BaseModel):
    cabin_class: str
    change: int  # positive = release seats, negative = reserve seats
