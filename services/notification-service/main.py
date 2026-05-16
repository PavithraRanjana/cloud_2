import sys
import os
import time
import json
import asyncio
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import boto3
import structlog
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from shared.config import BaseConfig
from shared.database import create_db_engine, create_session_factory, Base
from shared.auth import get_current_user, RoleChecker
from shared.events import EventConsumer
from shared.cache import create_redis_client, redis_set_nx
from shared.logging import setup_logging
from shared.schemas import HealthResponse
from models import Notification, NotificationType, NotificationStatus
from schemas import NotificationResponse, NotificationCreate

config = BaseConfig(service_name="notification-service")
setup_logging(config.service_name)
logger = structlog.get_logger()

# Async engine for FastAPI request handlers
engine = create_db_engine(config.database_url)
SessionFactory = create_session_factory(engine)

# Sync engine for the background polling thread (avoids event-loop conflicts)
_sync_db_url = config.database_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
_sync_engine = create_engine(_sync_db_url)
SyncSessionFactory = sessionmaker(bind=_sync_engine)

# Redis for deduplication — prevents double-send when SQS redelivers a message
redis_client = create_redis_client(config.redis_url)
DEDUP_TTL = 300  # 5-minute dedup window (SQS visibility timeout default is 30s)

START_TIME = time.time()

SES_SENDER_EMAIL  = os.environ.get("SES_SENDER_EMAIL", "noreply@aerolink.com")
ENABLE_SQS_POLLING = os.environ.get("ENABLE_SQS_POLLING", "false").lower() == "true"

# In production these are injected from the CloudFormation stack outputs (real SQS URLs).
# Fall back to the LocalStack pattern for local dev.
_localstack_base = config.aws_endpoint_url or "http://localhost:4566"
MAIN_QUEUE_URL = os.environ.get(
    "SQS_QUEUE_URL",
    f"{_localstack_base}/000000000000/aerolink-notifications",
)
DLQ_URL = os.environ.get(
    "SQS_DLQ_URL",
    f"{_localstack_base}/000000000000/aerolink-notifications-dlq",
)

from shared.events import _boto3_kwargs as _aws_kwargs
_sqs = boto3.client("sqs", **_aws_kwargs(
    config.aws_endpoint_url, config.aws_region,
    config.aws_access_key_id, config.aws_secret_access_key,
))

TEMPLATES = {
    "BookingCreated": {
        "subject": "Booking Confirmed – {booking_reference}",
        "body": "Hi {passenger_name},\n\nYour booking {booking_reference} has been confirmed.\n\nFlight: {flight_id}\nCabin: {cabin_class}\nTotal: ${total_price}\n\nProceed to payment to complete your booking.\n\nAeroLink",
    },
    "PaymentCompleted": {
        "subject": "Payment Received – Booking {booking_reference}",
        "body": "Hi {passenger_name},\n\nYour payment of ${amount} {currency} has been received.\n\nTransaction: {transaction_ref}\nBooking: {booking_reference}\n\nYou can now check in online.\n\nAeroLink",
    },
    "CheckInCompleted": {
        "subject": "Check-In Confirmed – Seat {seat_number}",
        "body": "Hi {passenger_name},\n\nYou have successfully checked in.\n\nSeat: {seat_number}\nBoarding Group: {boarding_group}\nGate: {gate}\n\nPlease arrive at the gate at least 30 minutes before departure.\n\nHave a great flight!\nAeroLink",
    },
    "BaggageRegistered": {
        "subject": "Baggage Registered – {tag_number}",
        "body": "Hi {passenger_name},\n\nYour baggage has been registered.\n\nTag: {tag_number}\nWeight: {weight_kg} kg\n\nYou can track your baggage at any time through the app.\n\nAeroLink",
    },
    "BaggageStatusChanged": {
        "subject": "Baggage Update – {tag_number}",
        "body": "Hi {passenger_name},\n\nYour baggage {tag_number} status has been updated.\n\nStatus: {status}\nLocation: {location}\n\nAeroLink",
    },
    "BookingCancelled": {
        "subject": "Booking Cancelled – {booking_reference}",
        "body": "Hi {passenger_name},\n\nYour booking {booking_reference} has been cancelled.\n\nIf you made a payment, your refund will be processed within 5-7 business days.\n\nWe hope to see you again.\nAeroLink",
    },
    "PaymentRefunded": {
        "subject": "Refund Processed – ${amount}",
        "body": "Hi {passenger_name},\n\nA refund of ${amount} {currency} has been processed for booking {booking_id}.\n\nPlease allow 5-7 business days for the funds to appear in your account.\n\nAeroLink",
    },
    "FlightScheduleUpdated": {
        "subject": "Flight Schedule Update – {flight_number}",
        "body": "Hi there,\n\nFlight {flight_number} has been updated (action: {action}).\n\nPlease check the AeroLink app for the latest schedule information.\n\nAeroLink",
    },
}


class SESEmailSender:
    def __init__(self):
        self.client = boto3.client(
            "ses",
            **_aws_kwargs(config.aws_endpoint_url, config.aws_region,
                          config.aws_access_key_id, config.aws_secret_access_key),
        )
        self.sender = SES_SENDER_EMAIL

    def verify_sender(self):
        """Verify the sender identity with SES (required before sending)."""
        try:
            self.client.verify_email_identity(EmailAddress=self.sender)
            logger.info("ses_sender_verified", email=self.sender)
        except Exception as e:
            logger.error("ses_sender_verification_failed", error=str(e))

    def send(self, to_email: str, subject: str, body: str):
        """Send a plain-text email via SES."""
        try:
            self.client.send_email(
                Source=self.sender,
                Destination={"ToAddresses": [to_email]},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
                },
            )
            logger.info("email_sent", to=to_email, subject=subject)
        except Exception as e:
            logger.error("email_send_failed", to=to_email, error=str(e))


ses = SESEmailSender()


def _to_response(n: Notification) -> NotificationResponse:
    return NotificationResponse(
        id=str(n.id), recipient_email=n.recipient_email,
        recipient_name=n.recipient_name,
        notification_type=n.notification_type.value,
        subject=n.subject, body=n.body,
        event_type=n.event_type, status=n.status.value,
        is_read=n.is_read, created_at=n.created_at,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        try:
            await conn.run_sync(Base.metadata.create_all)
        except Exception:
            pass
    ses.verify_sender()
    if ENABLE_SQS_POLLING:
        poller = threading.Thread(target=poll_events, daemon=True)
        poller.start()
        logger.info("sqs_polling_enabled")
    else:
        logger.info("sqs_polling_disabled")
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


async def _persist_notification(recipient_email: str, recipient_name: str,
                                event_type: str, subject: str, body: str):
    """Persist a notification to the database."""
    async with SessionFactory() as session:
        notification = Notification(
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            notification_type=NotificationType.EMAIL,
            subject=subject,
            body=body,
            event_type=event_type,
            status=NotificationStatus.SENT,
        )
        session.add(notification)
        await session.commit()


def process_event(event_body: dict):
    """Process an SQS event: persist to DB then send email."""
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
    body    = template["body"].format_map(safe)

    recipient_email = detail.get("passenger_email", "")
    recipient_name  = detail.get("passenger_name", "")

    if not recipient_email:
        logger.warning("no_recipient_email_in_event", detail_type=detail_type)
        return

    # Deduplication: skip if we already processed this event+recipient within the window
    dedup_key = f"notif:dedup:{detail_type}:{recipient_email}"
    if not redis_set_nx(redis_client, dedup_key, "1", DEDUP_TTL):
        logger.info("notification_deduplicated", event_type=detail_type, recipient=recipient_email)
        return

    try:
        with SyncSessionFactory() as session:
            notification = Notification(
                recipient_email=recipient_email,
                recipient_name=recipient_name,
                notification_type=NotificationType.EMAIL,
                subject=subject,
                body=body,
                event_type=detail_type,
                status=NotificationStatus.SENT,
            )
            session.add(notification)
            session.commit()
        logger.info("notification_persisted", event_type=detail_type, recipient=recipient_email)
    except Exception as e:
        logger.error("notification_persist_failed", error=str(e), detail_type=detail_type)

    ses.send(to_email=recipient_email, subject=subject, body=body)


def poll_events():
    """Background thread that polls SQS for events from EventBridge."""
    try:
        consumer = EventConsumer(
            endpoint_url=config.aws_endpoint_url,
            region=config.aws_region,
            queue_url=MAIN_QUEUE_URL,
            aws_access_key_id=config.aws_access_key_id,
            aws_secret_access_key=config.aws_secret_access_key,
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


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(service="notification-service",
                          uptime_seconds=time.time() - START_TIME,
                          dependencies={"database": "healthy", "sqs": "healthy",
                                        "redis": "healthy" if redis_client else "unavailable"})


@app.post("/api/v1/notifications", response_model=NotificationResponse, status_code=201)
async def create_notification(data: NotificationCreate,
                              background_tasks: BackgroundTasks,
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
    background_tasks.add_task(ses.send, data.recipient_email, data.subject, data.body)
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


@app.get("/api/v1/notifications/dlq")
async def get_dlq_stats(current_user: dict = Depends(RoleChecker(["admin"]))):
    """Return DLQ depth and sample failed messages so admins can investigate."""
    try:
        attrs = _sqs.get_queue_attributes(
            QueueUrl=DLQ_URL,
            AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"],
        )
        depth = int(attrs["Attributes"].get("ApproximateNumberOfMessages", 0))
        in_flight = int(attrs["Attributes"].get("ApproximateNumberOfMessagesNotVisible", 0))

        # Peek without consuming (VisibilityTimeout=0 means messages stay visible immediately)
        peek = _sqs.receive_message(
            QueueUrl=DLQ_URL,
            MaxNumberOfMessages=10,
            VisibilityTimeout=0,
            AttributeNames=["All"],
        ).get("Messages", [])

        samples = []
        for m in peek:
            try:
                body = json.loads(m["Body"])
            except Exception:
                body = m["Body"]
            samples.append({
                "message_id": m["MessageId"],
                "receive_count": m.get("Attributes", {}).get("ApproximateReceiveCount", "?"),
                "body": body,
            })

        return {"queue_depth": depth, "in_flight": in_flight, "samples": samples}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DLQ unavailable: {e}")


@app.post("/api/v1/notifications/dlq/reprocess")
async def reprocess_dlq(current_user: dict = Depends(RoleChecker(["admin"]))):
    """
    Move all DLQ messages back to the main queue for reprocessing.
    Uses SQS redrive (receive + re-send + delete pattern).
    """
    moved = 0
    errors = 0
    while True:
        resp = _sqs.receive_message(
            QueueUrl=DLQ_URL,
            MaxNumberOfMessages=10,
            VisibilityTimeout=30,
        )
        messages = resp.get("Messages", [])
        if not messages:
            break
        for m in messages:
            try:
                _sqs.send_message(QueueUrl=MAIN_QUEUE_URL, MessageBody=m["Body"])
                _sqs.delete_message(QueueUrl=DLQ_URL, ReceiptHandle=m["ReceiptHandle"])
                moved += 1
            except Exception as e:
                logger.error("dlq_reprocess_error", error=str(e), message_id=m["MessageId"])
                errors += 1

    logger.info("dlq_reprocess_complete", moved=moved, errors=errors)
    return {"moved": moved, "errors": errors}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8008)
