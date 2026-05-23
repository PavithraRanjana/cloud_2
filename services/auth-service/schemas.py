from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class UserRegister(BaseModel):
    email: str = Field(..., min_length=5)
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=1, max_length=255)
    role: str = "passenger"
    # ABAC attributes
    airport_code: Optional[str] = None  # for airport-operator role
    airline_code: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    api_key: Optional[str] = None  # returned only for partner-api role


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    full_name: str
    role: str
    is_active: bool
    airport_code: Optional[str] = None
    airline_code: Optional[str] = None
    api_key: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
