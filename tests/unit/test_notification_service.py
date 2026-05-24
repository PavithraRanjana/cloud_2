"""Tests for services/notification-service/main.py."""
import sys
import os
import uuid
import json
import importlib.util
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.database import Base

# Pre-mock boto3 to prevent hang when shared.events is imported
_mock_boto3 = MagicMock()
sys.modules.setdefault("boto3", _mock_boto3)


@pytest.fixture
def notification_app(mock_db_session, auth_headers):
    svc_path = os.path.join(os.path.dirname(__file__), "..", "..", "services", "notification-service")
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


def test_process_event_payment_completed(notification_app):
    c, db, mod = notification_app
    mod.process_event({
        "detail-type": "PaymentCompleted",
        "detail": {
            "booking_reference": "ALTEST01",
            "passenger_name": "John Doe",
            "amount": "199.99",
            "currency": "EUR",
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


# ── Health ───────────────────────────────────────────────────────

def test_health_endpoint(notification_app):
    c, db, mod = notification_app
    resp = c.get("/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "notification-service"


# ── process_event – string detail ───────────────────────────────

def test_process_event_detail_as_json_string(notification_app):
    """detail can arrive as a JSON-encoded string (EventBridge re-serialises)."""
    c, db, mod = notification_app
    detail_dict = {
        "booking_reference": "AL1XYZ99",
        "passenger_name": "Alice",
        "flight_id": "flight-x",
        "total_price": "299.99",
    }
    mod.process_event({
        "detail-type": "BookingCreated",
        "detail": json.dumps(detail_dict),  # string, not dict
    })


def test_process_event_baggage_status_changed(notification_app):
    c, db, mod = notification_app
    mod.process_event({
        "detail-type": "BaggageStatusChanged",
        "detail": {"tag_number": "BAG-001", "status": "loaded", "location": "DUB"},
    })


def test_process_event_booking_cancelled(notification_app):
    c, db, mod = notification_app
    mod.process_event({
        "detail-type": "BookingCancelled",
        "detail": {"booking_reference": "ALCANCEL1"},
    })


# ── SQS polling enabled – starts background thread ───────────────

def test_sqs_polling_enabled_starts_thread():
    """When ENABLE_SQS_POLLING=true, lifespan should start a daemon thread."""
    svc_path = os.path.join(os.path.dirname(__file__), "..", "..", "services", "notification-service")
    if svc_path not in sys.path:
        sys.path.insert(0, svc_path)

    from shared.database import Base
    Base.metadata.clear()
    for mod_name in ["models", "schemas"]:
        sys.modules.pop(mod_name, None)

    mock_engine = MagicMock()
    mock_engine.begin.return_value = AsyncMock()
    mock_engine.dispose = AsyncMock()

    spec = importlib.util.spec_from_file_location(
        "notification_main_sqs",
        os.path.join(svc_path, "main.py"),
    )
    mod = importlib.util.module_from_spec(spec)

    started_threads = []

    class FakeThread:
        def __init__(self, target=None, daemon=None):
            self.target = target
            self.daemon = daemon

        def start(self):
            started_threads.append(self)

    with patch("shared.database.create_db_engine", return_value=mock_engine), \
         patch("shared.database.create_session_factory"), \
         patch("shared.logging.setup_logging"), \
         patch.dict(os.environ, {"ENABLE_SQS_POLLING": "true"}), \
         patch("threading.Thread", FakeThread):
        spec.loader.exec_module(mod)

        assert mod.ENABLE_SQS_POLLING is True

        with TestClient(mod.app, raise_server_exceptions=False):
            pass  # lifespan runs on enter

    assert len(started_threads) == 1

    for mod_name in ["models", "schemas", "notification_main_sqs"]:
        sys.modules.pop(mod_name, None)
    if svc_path in sys.path:
        sys.path.remove(svc_path)


# ── poll_events – consumer creation failure ───────────────────────

def test_ses_send_exception_silenced(notification_app):
    """SES send errors should be caught and not propagate."""
    c, db, mod = notification_app
    mod.ses.client.send_email.side_effect = Exception("SES unavailable")
    mod.ses.send(to_email="a@b.com", subject="Test", body="Body")  # must not raise


def test_ses_verify_sender_exception_silenced(notification_app):
    """SES verify_sender errors should be caught and not propagate."""
    c, db, mod = notification_app
    mod.ses.client.verify_email_identity.side_effect = Exception("SES error")
    mod.ses.verify_sender()  # must not raise


def test_process_event_deduplication_skips_duplicate(notification_app):
    """process_event should skip silently when dedup key already exists."""
    c, db, mod = notification_app
    mock_redis = MagicMock()
    mock_redis.set.return_value = None  # SET NX returns None → key exists → dedup fires
    mod.redis_client = mock_redis

    mod.process_event({
        "detail-type": "BookingCreated",
        "detail": {"booking_reference": "DUP001", "passenger_name": "Dup"},
        "id": "msg-dup-001",
    })
    # No notification should be persisted — SyncSessionFactory not called via dedup path
    # (the early return prevents DB access)


def test_process_event_creates_notification_in_db(notification_app):
    """process_event should persist notification via SyncSessionFactory."""
    c, db, mod = notification_app
    mock_redis = MagicMock()
    mock_redis.set.return_value = True  # SET NX succeeds → new key → proceed
    mod.redis_client = mock_redis

    mock_session = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_session)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    mod.SyncSessionFactory = MagicMock(return_value=mock_ctx)

    mod.process_event({
        "detail-type": "BookingCreated",
        "detail": {
            "booking_reference": "AL1NEW01",
            "passenger_name": "New Pax",
            "flight_id": "flight-3",
            "total_price": "199.00",
            "passenger_email": "pax@test.com",
        },
        "id": "msg-new-001",
    })
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()


def test_list_notifications_with_email_filter(notification_app):
    """list_notifications should add WHERE clause when user has email claim."""
    c, db, mod = notification_app
    from shared.auth import create_access_token
    import uuid as _uuid
    token = create_access_token({
        "sub": str(_uuid.uuid4()),
        "role": "passenger",
        "email": "filter@test.com",
    })
    headers = {"Authorization": f"Bearer {token}"}

    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = []
    db.execute.return_value = result_mock

    resp = c.get("/api/v1/notifications", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_mark_read_success(notification_app, auth_headers):
    c, db, mod = notification_app
    headers = auth_headers()

    notif = MagicMock()
    notif.id = uuid.uuid4()
    notif.recipient_email = "t@t.com"
    notif.recipient_name = "T"
    notif.notification_type = MagicMock(value="email")
    notif.subject = "S"
    notif.body = "B"
    notif.event_type = "E"
    notif.status = MagicMock(value="sent")
    notif.is_read = False
    notif.created_at = MagicMock()

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = notif
    db.execute.return_value = result_mock
    db.refresh = AsyncMock(return_value=None)

    resp = c.patch(f"/api/v1/notifications/{notif.id}/read", headers=headers)
    assert resp.status_code == 200
    assert notif.is_read is True


def test_mark_read_not_found(notification_app, auth_headers):
    c, db, mod = notification_app
    headers = auth_headers()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    resp = c.patch(f"/api/v1/notifications/{uuid.uuid4()}/read", headers=headers)
    assert resp.status_code == 404


def test_get_dlq_stats(notification_app, auth_headers):
    c, db, mod = notification_app
    headers = auth_headers(role="admin")

    mod._sqs = MagicMock()
    mod._sqs.get_queue_attributes.return_value = {
        "Attributes": {
            "ApproximateNumberOfMessages": "3",
            "ApproximateNumberOfMessagesNotVisible": "1",
        }
    }
    mod._sqs.receive_message.return_value = {
        "Messages": [
            {"MessageId": "m1", "Body": '{"detail-type":"test"}',
             "Attributes": {"ApproximateReceiveCount": "2"}},
        ]
    }

    resp = c.get("/api/v1/notifications/dlq", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["queue_depth"] == 3
    assert body["in_flight"] == 1
    assert len(body["samples"]) == 1


def test_reprocess_dlq(notification_app, auth_headers):
    c, db, mod = notification_app
    headers = auth_headers(role="admin")

    mod._sqs = MagicMock()
    # First poll returns 2 messages, second returns empty → loop ends
    mod._sqs.receive_message.side_effect = [
        {"Messages": [
            {"MessageId": "m1", "Body": "msg1", "ReceiptHandle": "rh1"},
            {"MessageId": "m2", "Body": "msg2", "ReceiptHandle": "rh2"},
        ]},
        {"Messages": []},
    ]

    resp = c.post("/api/v1/notifications/dlq/reprocess", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["moved"] == 2
    assert body["errors"] == 0
    assert mod._sqs.send_message.call_count == 2
    assert mod._sqs.delete_message.call_count == 2


def test_poll_events_consumer_creation_fails(notification_app):
    """If EventConsumer raises, poll_events should return early without crashing."""
    c, db, mod = notification_app

    import threading
    with patch.object(mod, "EventConsumer", side_effect=Exception("no SQS connection")):
        t = threading.Thread(target=mod.poll_events)
        t.start()
        t.join(timeout=2.0)

    assert not t.is_alive()
