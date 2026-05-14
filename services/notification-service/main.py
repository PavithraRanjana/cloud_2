import sys
import os
import time
import json
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog
from shared.config import BaseConfig
from shared.database import create_db_engine, create_session_factory, Base
from shared.auth import get_current_user
from shared.events import EventConsumer
from shared.logging import setup_logging
from shared.schemas import HealthResponse
from models import Notification, NotificationType, NotificationStatus
from schemas import NotificationResponse, NotificationCreate

config = BaseConfig(service_name="notification-service")
setup_logging(config.service_name)
logger = structlog.get_logger()

engine = create_db_engine(config.database_url)
SessionFactory = create_session_factory(engine)
START_TIME = time.time()

# Notification templates
TEMPLATES = {
    "BookingCreated": {
        "subject": "Booking Confirmation - {booking_reference}",
        "body": "Dear {passenger_name},\n\nYour booking {booking_reference} has been created successfully.\n\nFlight: {flight_id}\nTotal: EUR {total_price}\n\nPlease proceed to payment to confirm your booking.\n\nThank you for choosing AeroLink!",
    },
    "PaymentProcessed": {
        "subject": "Payment Confirmed - Booking {booking_id}",
        "body": "Dear Customer,\n\nYour payment of EUR {amount} has been processed successfully.\n\nTransaction Reference: {transaction_ref}\nBooking: {booking_id}\n\nYou can now check in online.\n\nThank you for choosing AeroLink!",
    },
    "CheckInCompleted": {
        "subject": "Check-In Complete - Seat {seat_number}",
        "body": "Dear {passenger_name},\n\nYou have been checked in successfully.\n\nSeat: {seat_number}\nFlight: {flight_id}\n\nYour boarding pass is ready. Please arrive at the gate at least 30 minutes before departure.\n\nHave a great flight!",
    },
    "BaggageStatusChanged": {
        "subject": "Baggage Update - {tag_number}",
        "body": "Baggage {tag_number} status update:\n\nNew Status: {status}\nLocation: {location}\n\nTrack your baggage at any time through our app.",
    },
    "BookingCancelled": {
        "subject": "Booking Cancelled - {booking_reference}",
        "body": "Your booking {booking_reference} has been cancelled.\n\nIf you made a payment, a refund will be processed within 5-7 business days.\n\nWe hope to see you again soon.",
    },
}


def _to_response(n: Notification) -> NotificationResponse:
    return NotificationResponse(
        id=str(n.id), recipient_email=n.recipient_email,
        recipient_name=n.recipient_name,
        notification_type=n.notification_type.value,
        subject=n.subject, body=n.body,
        event_type=n.event_type, status=n.status.value,
        is_read=n.is_read, created_at=n.created_at,
    )


ENABLE_SQS_POLLING = os.environ.get("ENABLE_SQS_POLLING", "false").lower() == "true"


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        try:
            await conn.run_sync(Base.metadata.create_all)
        except Exception:
            pass  # Table may already exist from another service starting concurrently
    if ENABLE_SQS_POLLING:
        # Start SQS polling in background thread (disabled by default; Lambda handles SQS)
        poller = threading.Thread(target=poll_events, daemon=True)
        poller.start()
        logger.info("sqs_polling_enabled", msg="Background SQS polling thread started")
    else:
        logger.info("sqs_polling_disabled", msg="SQS polling disabled; Lambda handles dispatch")
    yield
    await engine.dispose()


app = FastAPI(title="AeroLink Notification Service", version="1.0.0", lifespan=lifespan)


async def get_db():
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def poll_events():
    """Background thread that polls SQS for events from EventBridge."""
    try:
        consumer = EventConsumer(
            endpoint_url=config.aws_endpoint_url,
            region=config.aws_region,
            queue_url=f"{config.aws_endpoint_url}/000000000000/aerolink-notifications",
        )
    except Exception as e:
        logger.error("failed_to_create_consumer", error=str(e))
        return

    logger.info("notification_consumer_started")
    while True:
        try:
            messages = consumer.poll(max_messages=10, wait_seconds=5)
            for msg in messages:
                try:
                    process_event(msg["body"])
                    consumer.ack(msg["receipt_handle"])
                except Exception as e:
                    logger.error("event_processing_failed", error=str(e))
        except Exception as e:
            logger.error("poll_error", error=str(e))
            time.sleep(10)


def process_event(event_body: dict):
    """Process an event from EventBridge via SQS."""
    detail_type = event_body.get("detail-type", "")
    detail = event_body.get("detail", {})
    if isinstance(detail, str):
        detail = json.loads(detail)

    template = TEMPLATES.get(detail_type)
    if not template:
        logger.info("no_template_for_event", detail_type=detail_type)
        return

    class _SafeDict(dict):
        def __missing__(self, key):
            return "N/A"

    safe = _SafeDict(detail)
    subject = template["subject"].format_map(safe)
    body = template["body"].format_map(safe)

    logger.info("notification_sent",
                event_type=detail_type,
                subject=subject,
                recipient=detail.get("passenger_email", "unknown"))


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(service="notification-service",
                          uptime_seconds=time.time() - START_TIME,
                          dependencies={"database": "healthy", "sqs": "healthy"})


@app.post("/api/v1/notifications", response_model=NotificationResponse, status_code=201)
async def create_notification(data: NotificationCreate,
                              db: AsyncSession = Depends(get_db)):
    notification = Notification(
        recipient_email=data.recipient_email,
        recipient_name=data.recipient_name,
        notification_type=NotificationType(data.notification_type),
        subject=data.subject,
        body=data.body,
        event_type=data.event_type,
        status=NotificationStatus.SENT,
    )
    db.add(notification)
    await db.flush()
    await db.refresh(notification)
    logger.info("notification_created", subject=data.subject, recipient=data.recipient_email)
    return _to_response(notification)


@app.get("/api/v1/notifications", response_model=list[NotificationResponse])
async def list_notifications(current_user: dict = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    user_email = current_user.get("email", "")
    query = select(Notification).order_by(Notification.created_at.desc()).limit(50)
    if user_email:
        query = query.where(Notification.recipient_email == user_email)
    result = await db.execute(query)
    return [_to_response(n) for n in result.scalars().all()]


@app.patch("/api/v1/notifications/{notification_id}/read", response_model=NotificationResponse)
async def mark_read(notification_id: str,
                    current_user: dict = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Notification).where(Notification.id == notification_id))
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.is_read = True
    await db.flush()
    await db.refresh(notification)
    return _to_response(notification)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8008)
