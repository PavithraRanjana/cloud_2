from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class NotificationResponse(BaseModel):
    id: str
    recipient_email: str
    recipient_name: Optional[str]
    notification_type: str
    subject: str
    body: str
    event_type: str
    status: str
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationCreate(BaseModel):
    recipient_email: str
    recipient_name: Optional[str] = None
    subject: str
    body: str
    event_type: str
    notification_type: str = "email"
