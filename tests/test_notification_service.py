"""Tests for services/notification-service/main.py."""
import sys
import os
import uuid
import json
import importlib.util
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.database import Base

# Pre-mock boto3 to prevent hang when shared.events is imported
_mock_boto3 = MagicMock()
sys.modules.setdefault("boto3", _mock_boto3)


@pytest.fixture
def notification_app(mock_db_session, auth_headers):
    svc_path = os.path.join(os.path.dirname(__file__), "..", "services", "notification-service")
    sys.path.insert(0, svc_path)
    Base.metadata.clear()
    for mod_name in ["models", "schemas"]:
        sys.modules.pop(mod_name, None)

    mock_engine = MagicMock()
    mock_engine.begin.return_value = AsyncMock()
    mock_engine.dispose = AsyncMock()

    spec = importlib.util.spec_from_file_location(
        "notification_main", os.path.join(svc_path, "main.py"))
    mod = importlib.util.module_from_spec(spec)
    with patch("shared.database.create_db_engine", return_value=mock_engine), \
         patch("shared.database.create_session_factory"), \
         patch("shared.logging.setup_logging"), \
         patch.dict(os.environ, {"ENABLE_SQS_POLLING": "false"}):
        spec.loader.exec_module(mod)

    async def mock_get_db():
        yield mock_db_session

    mod.app.dependency_overrides[mod.get_db] = mock_get_db
    with TestClient(mod.app, raise_server_exceptions=False) as c:
        yield c, mock_db_session, mod
    mod.app.dependency_overrides.clear()
    for mod_name in ["models", "schemas"]:
        sys.modules.pop(mod_name, None)
    if svc_path in sys.path:
        sys.path.remove(svc_path)


# ── process_event ────────────────────────────────────────────────

def test_process_event_booking_created(notification_app):
    c, db, mod = notification_app
    # Should not raise
    mod.process_event({
        "detail-type": "BookingCreated",
        "detail": {
            "booking_reference": "AL1ABC23",
            "passenger_name": "John Doe",
            "flight_id": "flight-1",
            "total_price": "199.99",
        },
    })


def test_process_event_payment_processed(notification_app):
    c, db, mod = notification_app
    mod.process_event({
        "detail-type": "PaymentProcessed",
        "detail": {
            "booking_id": "booking-1",
            "amount": "199.99",
            "transaction_ref": "TXN-123",
        },
    })


def test_process_event_checkin_completed(notification_app):
    c, db, mod = notification_app
    mod.process_event({
        "detail-type": "CheckInCompleted",
        "detail": {
            "passenger_name": "Jane Doe",
            "seat_number": "12A",
            "flight_id": "flight-2",
        },
    })


def test_process_event_unknown_type_skipped(notification_app):
    c, db, mod = notification_app
    # Should not raise - just logs and skips
    mod.process_event({
        "detail-type": "UnknownEventType",
        "detail": {"key": "value"},
    })


def test_process_event_missing_fields_uses_na(notification_app):
    c, db, mod = notification_app
    # Should not raise — missing template fields are replaced with N/A
    mod.process_event({
        "detail-type": "BookingCreated",
        "detail": {},  # missing all fields
    })


# ── HTTP endpoints ───────────────────────────────────────────────

def test_create_notification_endpoint(notification_app):
    c, db, mod = notification_app

    def fake_refresh(obj):
        obj.id = uuid.uuid4()
        obj.recipient_email = "test@example.com"
        obj.recipient_name = "Test"
        obj.notification_type = MagicMock(value="email")
        obj.subject = "Test Subject"
        obj.body = "Test Body"
        obj.event_type = "TestEvent"
        obj.status = MagicMock(value="sent")
        obj.is_read = False
        obj.created_at = MagicMock()

    db.refresh = AsyncMock(side_effect=fake_refresh)

    resp = c.post("/api/v1/notifications", json={
        "recipient_email": "test@example.com",
        "recipient_name": "Test",
        "subject": "Test Subject",
        "body": "Test Body",
        "event_type": "TestEvent",
        "notification_type": "email",
    })
    assert resp.status_code == 201


def test_list_notifications_endpoint(notification_app, auth_headers):
    c, db, mod = notification_app
    headers = auth_headers()

    notif = MagicMock()
    notif.id = uuid.uuid4()
    notif.recipient_email = "test@example.com"
    notif.recipient_name = "Test"
    notif.notification_type = MagicMock(value="email")
    notif.subject = "Test"
    notif.body = "Test"
    notif.event_type = "TestEvent"
    notif.status = MagicMock(value="sent")
    notif.is_read = False
    notif.created_at = MagicMock()

    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [notif]
    db.execute.return_value = result_mock

    resp = c.get("/api/v1/notifications", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── SQS polling config ──────────────────────────────────────────

def test_sqs_polling_disabled_by_default(notification_app):
    c, db, mod = notification_app
    assert mod.ENABLE_SQS_POLLING is False
