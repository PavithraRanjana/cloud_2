from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime


class ProfileCreate(BaseModel):
    title: Optional[str] = Field(None, max_length=20)
    gender: Optional[str] = Field(None, max_length=20)
    first_name: str = Field(..., min_length=1, max_length=100)
    middle_name: Optional[str] = Field(None, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    date_of_birth: Optional[date] = None
    nationality: Optional[str] = None
    passport_number: Optional[str] = None
    passport_expiry: Optional[date] = None
    phone_number: Optional[str] = None
    meal_preference: Optional[str] = None
    seat_preference: Optional[str] = None
    emergency_contact: Optional[str] = None


class ProfileUpdate(BaseModel):
    title: Optional[str] = None
    gender: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    nationality: Optional[str] = None
    passport_number: Optional[str] = None
    passport_expiry: Optional[date] = None
    phone_number: Optional[str] = None
    meal_preference: Optional[str] = None
    seat_preference: Optional[str] = None
    emergency_contact: Optional[str] = None


class ProfileResponse(BaseModel):
    id: str
    user_id: str
    title: Optional[str]
    gender: Optional[str]
    first_name: str
    middle_name: Optional[str]
    last_name: str
    date_of_birth: Optional[date]
    nationality: Optional[str]
    passport_number: Optional[str]  # decrypted on read
    passport_expiry: Optional[date]
    phone_number: Optional[str]
    loyalty_tier: str
    loyalty_points: int
    meal_preference: Optional[str]
    seat_preference: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class ConsentRequest(BaseModel):
    purpose: str = Field(..., min_length=1)
    granted: bool


class ConsentResponse(BaseModel):
    id: str
    user_id: str
    purpose: str
    granted: bool
    granted_at: Optional[datetime]
    revoked_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True
