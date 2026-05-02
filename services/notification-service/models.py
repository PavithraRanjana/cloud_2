import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text, Enum as SAEnum, Boolean
from sqlalchemy.dialects.postgresql import UUID
from shared.database import Base
import enum


class NotificationType(str, enum.Enum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"


class NotificationStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_email = Column(String(255), nullable=False, index=True)
    recipient_name = Column(String(255), nullable=True)
    notification_type = Column(SAEnum(NotificationType), default=NotificationType.EMAIL)
    subject = Column(String(500), nullable=False)
    body = Column(Text, nullable=False)
    event_type = Column(String(100), nullable=False)
    event_source = Column(String(100), nullable=True)
    status = Column(SAEnum(NotificationStatus), default=NotificationStatus.PENDING)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
