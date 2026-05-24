"""Tests for services/payment-service/main.py (Stripe-based API)."""
import sys
import os
import uuid
import importlib.util
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.database import Base

# Pre-mock boto3 and stripe to prevent import hang / missing package errors
_mock_boto3 = MagicMock()
sys.modules.setdefault("boto3", _mock_boto3)

if "stripe" not in sys.modules:
    sys.modules["stripe"] = MagicMock()
# Always reference the shared mock (test_integration.py may have inserted it first)
_mock_stripe = sys.modules["stripe"]

# Make stripe.error.* real exception classes so `except stripe.error.X:` works
class _StripeError(Exception):
    pass

class _SignatureVerificationError(_StripeError):
    pass

_mock_stripe.error = MagicMock()
_mock_stripe.error.StripeError = _StripeError
_mock_stripe.error.SignatureVerificationError = _SignatureVerificationError


@pytest.fixture
def payment_app(mock_db_session, auth_headers):
    svc_path = os.path.join(os.path.dirname(__file__), "..", "services", "payment-service")
    sys.path.insert(0, svc_path)
    Base.metadata.clear()
    for mod_name in ["models", "schemas"]:
        sys.modules.pop(mod_name, None)

    mock_engine = MagicMock()
    mock_engine.begin.return_value = AsyncMock()
    mock_engine.dispose = AsyncMock()

    spec = importlib.util.spec_from_file_location(
        "payment_main", os.path.join(svc_path, "main.py"))
    mod = importlib.util.module_from_spec(spec)
    mock_redis = MagicMock()
    mock_redis.get = MagicMock(return_value=None)  # cache always misses
    with patch("shared.database.create_db_engine", return_value=mock_engine), \
         patch("shared.database.create_session_factory"), \
         patch("shared.logging.setup_logging"), \
         patch("shared.resilience.create_circuit_breaker", return_value=MagicMock()), \
         patch("shared.cache.create_redis_client", return_value=mock_redis), \
         patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_fake",
                                  "STRIPE_WEBHOOK_SECRET": "whsec_test"}):
        spec.loader.exec_module(mod)

    async def mock_get_db():
        yield mock_db_session

    mod.app.dependency_overrides[mod.get_db] = mock_get_db
    mod.event_publisher = None
    with TestClient(mod.app, raise_server_exceptions=False) as c:
        yield c, mock_db_session, mod
    mod.app.dependency_overrides.clear()
    for mod_name in ["models", "schemas"]:
        sys.modules.pop(mod_name, None)
    if svc_path in sys.path:
        sys.path.remove(svc_path)


def _mock_httpx_client():
    """Returns a mock httpx.AsyncClient that always succeeds."""
    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "booking_reference": "ALTEST01", "passenger_email": "t@t.com",
        "passenger_name": "Test User",
    }
    mock_resp.raise_for_status = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.put = AsyncMock(return_value=mock_resp)
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ── Payment Intent Creation ──────────────────────────────────────

def test_create_payment_intent_success(payment_app, auth_headers, sample_payment):
    c, db, mod = payment_app
    headers = auth_headers()

    pi_id = "pi_test_intent_123"
    _mock_stripe.PaymentIntent.create.return_value = MagicMock(
        id=pi_id, client_secret=f"{pi_id}_secret_xxx")

    no_existing = MagicMock()
    no_existing.scalar_one_or_none.return_value = None
    db.execute.return_value = no_existing

    def fake_refresh(obj):
        obj.id = uuid.uuid4()
        obj.booking_id = str(uuid.uuid4())
        obj.user_id = str(uuid.uuid4())
        obj.amount = 199.99
        obj.currency = "EUR"
        obj.status = MagicMock(value="processing")
        obj.provider = "stripe"
        obj.idempotency_key = "idem-intent-1"
        obj.transaction_ref = None
        obj.failure_reason = None
        obj.stripe_payment_intent_id = pi_id
        obj.payment_method_type = None
        obj.wallet_brand = None
        obj.last_four = None
        obj.created_at = datetime.now(timezone.utc)

    db.refresh = AsyncMock(side_effect=fake_refresh)

    with patch.object(mod, "record_audit", new_callable=AsyncMock):
        resp = c.post("/api/v1/payments/intent", headers=headers, json={
            "booking_id": str(uuid.uuid4()),
            "amount": 199.99,
            "currency": "EUR",
            "idempotency_key": "idem-intent-1",
        })
    assert resp.status_code == 201
    assert "client_secret" in resp.json()
    assert resp.json()["client_secret"] == f"{pi_id}_secret_xxx"


def test_create_payment_intent_completed_idempotency_returns_409(payment_app, auth_headers, sample_payment):
    c, db, mod = payment_app
    headers = auth_headers()

    existing = sample_payment(idempotency_key="idem-done")
    existing.stripe_payment_intent_id = "pi_completed_123"
    existing.status = mod.PaymentStatus.COMPLETED

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = existing
    db.execute.return_value = result_mock

    resp = c.post("/api/v1/payments/intent", headers=headers, json={
        "booking_id": str(uuid.uuid4()),
        "amount": 199.99,
        "currency": "EUR",
        "idempotency_key": "idem-done",
    })
    assert resp.status_code == 409


def test_create_payment_intent_processing_idempotency_retrieves_intent(payment_app, auth_headers, sample_payment):
    c, db, mod = payment_app
    headers = auth_headers()

    pi_id = "pi_existing_processing_123"
    existing = sample_payment(idempotency_key="idem-proc")
    existing.stripe_payment_intent_id = pi_id
    existing.status = mod.PaymentStatus.PROCESSING

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = existing
    db.execute.return_value = result_mock

    _mock_stripe.PaymentIntent.retrieve.return_value = MagicMock(
        client_secret=f"{pi_id}_secret_yyy")

    resp = c.post("/api/v1/payments/intent", headers=headers, json={
        "booking_id": str(uuid.uuid4()),
        "amount": 199.99,
        "currency": "EUR",
        "idempotency_key": "idem-proc",
    })
    assert resp.status_code == 201
    assert resp.json()["client_secret"] == f"{pi_id}_secret_yyy"


# ── Webhook Handling ─────────────────────────────────────────────

def test_stripe_webhook_payment_succeeded_marks_completed(payment_app, auth_headers, sample_payment):
    c, db, mod = payment_app

    pi_id = "pi_webhook_success_123"
    payment = sample_payment()
    payment.stripe_payment_intent_id = pi_id
    payment.status = mod.PaymentStatus.PROCESSING

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = payment
    db.execute.return_value = result_mock

    _mock_stripe.Webhook.construct_event.return_value = {
        "type": "payment_intent.succeeded",
        "id": "evt_test_123",
        "data": {"object": {"id": pi_id, "charges": {"data": []}}},
    }

    with patch("httpx.AsyncClient", return_value=_mock_httpx_client()), \
         patch.object(mod, "record_audit", new_callable=AsyncMock):
        resp = c.post(
            "/api/v1/payments/stripe/webhook",
            content=b'{"type":"payment_intent.succeeded"}',
            headers={"stripe-signature": "t=123,v1=abc"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"received": True}
    assert payment.status == mod.PaymentStatus.COMPLETED


def test_stripe_webhook_payment_failed_marks_failed(payment_app, auth_headers, sample_payment):
    c, db, mod = payment_app

    pi_id = "pi_webhook_fail_123"
    payment = sample_payment()
    payment.stripe_payment_intent_id = pi_id
    payment.status = mod.PaymentStatus.PROCESSING

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = payment
    db.execute.return_value = result_mock

    _mock_stripe.Webhook.construct_event.return_value = {
        "type": "payment_intent.payment_failed",
        "id": "evt_fail_123",
        "data": {"object": {
            "id": pi_id,
            "last_payment_error": {"message": "Card declined"},
        }},
    }

    with patch.object(mod, "record_audit", new_callable=AsyncMock):
        resp = c.post(
            "/api/v1/payments/stripe/webhook",
            content=b'{"type":"payment_intent.payment_failed"}',
            headers={"stripe-signature": "t=123,v1=abc"},
        )
    assert resp.status_code == 200
    assert payment.status == mod.PaymentStatus.FAILED
    assert payment.failure_reason == "Card declined"


def test_stripe_webhook_unknown_type_returns_received(payment_app):
    c, db, mod = payment_app

    _mock_stripe.Webhook.construct_event.return_value = {
        "type": "charge.updated",
        "id": "evt_unknown_123",
        "data": {"object": {}},
    }

    resp = c.post(
        "/api/v1/payments/stripe/webhook",
        content=b'{"type":"charge.updated"}',
        headers={"stripe-signature": "t=123,v1=abc"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"received": True}


def test_stripe_webhook_invalid_signature_returns_400(payment_app):
    c, db, mod = payment_app

    _mock_stripe.Webhook.construct_event.side_effect = _SignatureVerificationError("bad sig")

    resp = c.post(
        "/api/v1/payments/stripe/webhook",
        content=b'bad-payload',
        headers={"stripe-signature": "t=bad,v1=bad"},
    )
    assert resp.status_code == 400
    # Reset for other tests
    _mock_stripe.Webhook.construct_event.side_effect = None


def test_stripe_webhook_publishes_payment_completed_event(payment_app, sample_payment):
    c, db, mod = payment_app

    mock_pub = MagicMock()
    mod.event_publisher = mock_pub

    pi_id = "pi_pub_event_123"
    payment = sample_payment()
    payment.stripe_payment_intent_id = pi_id
    payment.status = mod.PaymentStatus.PROCESSING
    payment.amount = 150.0
    payment.currency = "EUR"

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = payment
    db.execute.return_value = result_mock

    _mock_stripe.Webhook.construct_event.return_value = {
        "type": "payment_intent.succeeded",
        "id": "evt_pub_123",
        "data": {"object": {"id": pi_id, "charges": {"data": []}}},
    }

    with patch("httpx.AsyncClient", return_value=_mock_httpx_client()), \
         patch.object(mod, "record_audit", new_callable=AsyncMock):
        c.post(
            "/api/v1/payments/stripe/webhook",
            content=b'{"type":"payment_intent.succeeded"}',
            headers={"stripe-signature": "t=123,v1=abc"},
        )

    mock_pub.publish.assert_called_once()
    assert mock_pub.publish.call_args[0][1] == "PaymentCompleted"


def test_stripe_webhook_publishes_payment_failed_event(payment_app, sample_payment):
    c, db, mod = payment_app

    mock_pub = MagicMock()
    mod.event_publisher = mock_pub

    pi_id = "pi_pub_fail_event_123"
    payment = sample_payment()
    payment.stripe_payment_intent_id = pi_id
    payment.status = mod.PaymentStatus.PROCESSING

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = payment
    db.execute.return_value = result_mock

    _mock_stripe.Webhook.construct_event.return_value = {
        "type": "payment_intent.payment_failed",
        "id": "evt_fail_pub_123",
        "data": {"object": {
            "id": pi_id,
            "last_payment_error": {"message": "Insufficient funds"},
        }},
    }

    with patch.object(mod, "record_audit", new_callable=AsyncMock):
        c.post(
            "/api/v1/payments/stripe/webhook",
            content=b'{"type":"payment_intent.payment_failed"}',
            headers={"stripe-signature": "t=123,v1=abc"},
        )

    mock_pub.publish.assert_called_once()
    assert mock_pub.publish.call_args[0][1] == "PaymentFailed"


# ── Get Payment ──────────────────────────────────────────────────

def test_get_payment_success(payment_app, auth_headers, sample_payment):
    c, db, mod = payment_app
    headers = auth_headers()
    p = sample_payment()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = p
    db.execute.return_value = result_mock

    resp = c.get(f"/api/v1/payments/{p.id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


def test_get_payment_not_found(payment_app, auth_headers):
    c, db, mod = payment_app
    headers = auth_headers()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    resp = c.get(f"/api/v1/payments/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404


def test_get_payments_by_booking(payment_app, sample_payment):
    c, db, mod = payment_app
    p = sample_payment()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [p]
    db.execute.return_value = result_mock

    resp = c.get(f"/api/v1/payments/booking/{p.booking_id}")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── Refund ───────────────────────────────────────────────────────

def test_refund_payment_success(payment_app, auth_headers, sample_payment):
    c, db, mod = payment_app
    headers = auth_headers()

    p = sample_payment()
    p.status = mod.PaymentStatus.COMPLETED
    p.stripe_payment_intent_id = "pi_refund_test_123"
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = p
    db.execute.return_value = result_mock
    db.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "status", MagicMock(value="refunded")))

    with patch("httpx.AsyncClient", return_value=_mock_httpx_client()), \
         patch.object(mod, "record_audit", new_callable=AsyncMock):
        resp = c.post(f"/api/v1/payments/{p.id}/refund", headers=headers, json={
            "reason": "Customer request",
        })
    assert resp.status_code == 200
    assert resp.json()["status"] == "refunded"


def test_refund_payment_not_completed_rejected(payment_app, auth_headers, sample_payment):
    c, db, mod = payment_app
    headers = auth_headers()

    p = sample_payment(status="pending")
    p.status = mod.PaymentStatus.PENDING
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = p
    db.execute.return_value = result_mock

    resp = c.post(f"/api/v1/payments/{p.id}/refund", headers=headers, json={
        "reason": "Test",
    })
    assert resp.status_code == 400


def test_refund_payment_missing_stripe_id_rejected(payment_app, auth_headers, sample_payment):
    c, db, mod = payment_app
    headers = auth_headers()

    p = sample_payment()
    p.status = mod.PaymentStatus.COMPLETED
    p.stripe_payment_intent_id = None  # Missing Stripe PI
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = p
    db.execute.return_value = result_mock

    resp = c.post(f"/api/v1/payments/{p.id}/refund", headers=headers, json={
        "reason": "Test",
    })
    assert resp.status_code == 400


def test_refund_payment_not_found(payment_app, auth_headers):
    c, db, mod = payment_app
    headers = auth_headers()

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    resp = c.post(f"/api/v1/payments/{uuid.uuid4()}/refund", headers=headers, json={
        "reason": "Customer request",
    })
    assert resp.status_code == 404


def test_refund_updates_booking_status(payment_app, auth_headers, sample_payment):
    c, db, mod = payment_app
    headers = auth_headers()

    p = sample_payment()
    p.status = mod.PaymentStatus.COMPLETED
    p.stripe_payment_intent_id = "pi_refund_bk_123"
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = p
    db.execute.return_value = result_mock
    db.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "status", MagicMock(value="refunded")))

    mock_httpx_instance = _mock_httpx_client()
    with patch("httpx.AsyncClient", return_value=mock_httpx_instance), \
         patch.object(mod, "record_audit", new_callable=AsyncMock):
        c.post(f"/api/v1/payments/{p.id}/refund", headers=headers, json={"reason": "Test"})

    mock_httpx_instance.put.assert_called_once()


# ── Health ───────────────────────────────────────────────────────

def test_health_endpoint(payment_app):
    c, db, mod = payment_app
    resp = c.get("/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "payment-service"


# ── Exception silencing ──────────────────────────────────────────

def test_webhook_httpx_failure_silenced(payment_app, sample_payment):
    """httpx failures in webhook handler should not abort the 200 response."""
    c, db, mod = payment_app

    pi_id = "pi_httpx_silence_123"
    payment = sample_payment()
    payment.stripe_payment_intent_id = pi_id
    payment.status = mod.PaymentStatus.PROCESSING

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = payment
    db.execute.return_value = result_mock

    _mock_stripe.Webhook.construct_event.return_value = {
        "type": "payment_intent.succeeded",
        "id": "evt_silence_123",
        "data": {"object": {"id": pi_id, "charges": {"data": []}}},
    }

    failing_client = AsyncMock()
    failing_client.get = AsyncMock(side_effect=Exception("booking service down"))
    failing_client.put = AsyncMock(side_effect=Exception("booking service down"))
    failing_client.post = AsyncMock(side_effect=Exception("passenger service down"))
    failing_client.__aenter__ = AsyncMock(return_value=failing_client)
    failing_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=failing_client), \
         patch.object(mod, "record_audit", new_callable=AsyncMock):
        resp = c.post(
            "/api/v1/payments/stripe/webhook",
            content=b'{"type":"payment_intent.succeeded"}',
            headers={"stripe-signature": "t=123,v1=abc"},
        )
    assert resp.status_code == 200


def test_refund_httpx_exception_silenced(payment_app, auth_headers, sample_payment):
    """Booking status update httpx failure during refund should not abort the refund."""
    c, db, mod = payment_app
    headers = auth_headers()

    p = sample_payment()
    p.status = mod.PaymentStatus.COMPLETED
    p.stripe_payment_intent_id = "pi_refund_err_123"
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = p
    db.execute.return_value = result_mock
    db.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "status", MagicMock(value="refunded")))
    mod.event_publisher = None

    failing_client = AsyncMock()
    failing_client.put = AsyncMock(side_effect=Exception("booking service down"))
    failing_client.__aenter__ = AsyncMock(return_value=failing_client)
    failing_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=failing_client), \
         patch.object(mod, "record_audit", new_callable=AsyncMock):
        resp = c.post(f"/api/v1/payments/{p.id}/refund", headers=headers, json={
            "reason": "Test",
        })
    assert resp.status_code == 200


def test_refund_publisher_exception_silenced(payment_app, auth_headers, sample_payment):
    """Event publisher failure during refund should not abort the response."""
    c, db, mod = payment_app
    headers = auth_headers()

    mock_pub = MagicMock()
    mock_pub.publish.side_effect = Exception("eventbridge down")
    mod.event_publisher = mock_pub

    p = sample_payment()
    p.status = mod.PaymentStatus.COMPLETED
    p.stripe_payment_intent_id = "pi_refund_pub_err_123"
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = p
    db.execute.return_value = result_mock
    db.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "status", MagicMock(value="refunded")))

    with patch("httpx.AsyncClient", return_value=_mock_httpx_client()), \
         patch.object(mod, "record_audit", new_callable=AsyncMock):
        resp = c.post(f"/api/v1/payments/{p.id}/refund", headers=headers, json={
            "reason": "Test",
        })
    assert resp.status_code == 200


# ── Validation (422) ─────────────────────────────────────────────

def test_payment_intent_missing_required_fields_422(payment_app, auth_headers):
    c, db, mod = payment_app
    headers = auth_headers()
    resp = c.post("/api/v1/payments/intent", headers=headers, json={
        "booking_id": str(uuid.uuid4()),
        # amount, currency, idempotency_key omitted
    })
    assert resp.status_code == 422
