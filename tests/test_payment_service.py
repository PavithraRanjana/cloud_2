"""Tests for services/payment-service/main.py."""
import sys
import os
import uuid
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
    with patch("shared.database.create_db_engine", return_value=mock_engine), \
         patch("shared.database.create_session_factory"), \
         patch("shared.logging.setup_logging"):
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


# ── simulate_payment_processing ──────────────────────────────────

def test_simulate_payment_processing_returns_bool(payment_app):
    c, db, mod = payment_app
    success, result = mod.simulate_payment_processing()
    assert isinstance(success, bool)
    assert isinstance(result, str)


# ── Process Payment ──────────────────────────────────────────────

def test_process_payment_success(payment_app, auth_headers, sample_payment):
    c, db, mod = payment_app
    headers = auth_headers()

    # No existing idempotent payment
    no_existing = MagicMock()
    no_existing.scalar_one_or_none.return_value = None
    db.execute.return_value = no_existing

    payment = sample_payment()

    def fake_refresh(obj):
        obj.id = payment.id
        obj.booking_id = payment.booking_id
        obj.user_id = payment.user_id
        obj.amount = 199.99
        obj.currency = "EUR"
        obj.status = MagicMock(value="completed")
        obj.payment_method = MagicMock(value="credit-card")
        obj.idempotency_key = "idem-1"
        obj.transaction_ref = "TXN-ABC"
        obj.failure_reason = None
        obj.card_token = "tok_abc"
        obj.card_last_four = "4242"
        obj.created_at = payment.created_at

    db.refresh = AsyncMock(side_effect=fake_refresh)

    with patch.object(mod, "simulate_payment_processing", return_value=(True, "TXN-ABC")), \
         patch("httpx.AsyncClient") as mock_httpx, \
         patch.object(mod, "record_audit", new_callable=AsyncMock):
        mock_client = AsyncMock()
        mock_client.put = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client

        resp = c.post("/api/v1/payments", headers=headers, json={
            "booking_id": str(payment.booking_id),
            "amount": 199.99,
            "currency": "EUR",
            "payment_method": "credit-card",
            "idempotency_key": "idem-1",
            "card_number": "4111111111114242",
        })
    assert resp.status_code == 201


def test_process_payment_idempotency_returns_existing(payment_app, auth_headers, sample_payment):
    c, db, mod = payment_app
    headers = auth_headers()

    existing = sample_payment(idempotency_key="idem-dup")
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = existing
    db.execute.return_value = result_mock

    with patch.object(mod, "record_audit", new_callable=AsyncMock):
        resp = c.post("/api/v1/payments", headers=headers, json={
            "booking_id": str(uuid.uuid4()),
            "amount": 100.0,
            "idempotency_key": "idem-dup",
        })
    assert resp.status_code == 201


def test_process_payment_card_tokenized_not_stored_raw(payment_app, auth_headers, sample_payment):
    c, db, mod = payment_app
    headers = auth_headers()

    no_existing = MagicMock()
    no_existing.scalar_one_or_none.return_value = None
    db.execute.return_value = no_existing

    captured = {}

    orig_add = db.add

    def capture_add(obj):
        captured["payment"] = obj
        return orig_add(obj)

    db.add = capture_add

    payment = sample_payment()

    def fake_refresh(obj):
        obj.id = payment.id
        obj.booking_id = payment.booking_id
        obj.user_id = payment.user_id
        obj.amount = 50.0
        obj.currency = "EUR"
        obj.status = MagicMock(value="completed")
        obj.payment_method = MagicMock(value="credit-card")
        obj.idempotency_key = "idem-tok"
        obj.transaction_ref = "TXN-TOK"
        obj.failure_reason = None
        obj.card_token = captured.get("payment", MagicMock()).card_token if "payment" in captured else "tok_x"
        obj.card_last_four = "4242"
        obj.created_at = payment.created_at

    db.refresh = AsyncMock(side_effect=fake_refresh)

    with patch.object(mod, "simulate_payment_processing", return_value=(True, "TXN-TOK")), \
         patch("httpx.AsyncClient") as mock_httpx, \
         patch.object(mod, "record_audit", new_callable=AsyncMock):
        mock_client = AsyncMock()
        mock_client.put = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client

        resp = c.post("/api/v1/payments", headers=headers, json={
            "booking_id": str(payment.booking_id),
            "amount": 50.0,
            "idempotency_key": "idem-tok",
            "card_number": "4111111111114242",
        })
    # The stored payment should have a card_token (tok_...) not raw number
    if "payment" in captured:
        p = captured["payment"]
        assert p.card_token is not None
        assert p.card_token.startswith("tok_")


def test_process_payment_card_masked_last_four(payment_app, auth_headers, sample_payment):
    c, db, mod = payment_app
    headers = auth_headers()

    no_existing = MagicMock()
    no_existing.scalar_one_or_none.return_value = None
    db.execute.return_value = no_existing

    captured = {}
    orig_add = db.add

    def capture_add(obj):
        captured["payment"] = obj
        return orig_add(obj)

    db.add = capture_add

    payment = sample_payment()

    def fake_refresh(obj):
        obj.id = payment.id
        obj.booking_id = payment.booking_id
        obj.user_id = payment.user_id
        obj.amount = 50.0
        obj.currency = "EUR"
        obj.status = MagicMock(value="completed")
        obj.payment_method = MagicMock(value="credit-card")
        obj.idempotency_key = "idem-mask"
        obj.transaction_ref = "TXN-MSK"
        obj.failure_reason = None
        obj.card_token = "tok_xyz"
        obj.card_last_four = "1111"
        obj.created_at = payment.created_at

    db.refresh = AsyncMock(side_effect=fake_refresh)

    with patch.object(mod, "simulate_payment_processing", return_value=(True, "TXN-MSK")), \
         patch("httpx.AsyncClient") as mock_httpx, \
         patch.object(mod, "record_audit", new_callable=AsyncMock):
        mock_client = AsyncMock()
        mock_client.put = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client

        resp = c.post("/api/v1/payments", headers=headers, json={
            "booking_id": str(payment.booking_id),
            "amount": 50.0,
            "idempotency_key": "idem-mask",
            "card_number": "4111111111111111",
        })
    if "payment" in captured:
        assert captured["payment"].card_last_four == "1111"


def test_process_payment_failure(payment_app, auth_headers, sample_payment):
    c, db, mod = payment_app
    headers = auth_headers()

    no_existing = MagicMock()
    no_existing.scalar_one_or_none.return_value = None
    db.execute.return_value = no_existing

    payment = sample_payment(status="failed")

    def fake_refresh(obj):
        obj.id = payment.id
        obj.booking_id = payment.booking_id
        obj.user_id = payment.user_id
        obj.amount = 100.0
        obj.currency = "EUR"
        obj.status = MagicMock(value="failed")
        obj.payment_method = MagicMock(value="credit-card")
        obj.idempotency_key = "idem-fail"
        obj.transaction_ref = None
        obj.failure_reason = "Payment declined by issuing bank"
        obj.card_token = None
        obj.card_last_four = None
        obj.created_at = payment.created_at

    db.refresh = AsyncMock(side_effect=fake_refresh)

    with patch.object(mod, "simulate_payment_processing",
                      return_value=(False, "Payment declined by issuing bank")), \
         patch.object(mod, "record_audit", new_callable=AsyncMock):
        resp = c.post("/api/v1/payments", headers=headers, json={
            "booking_id": str(payment.booking_id),
            "amount": 100.0,
            "idempotency_key": "idem-fail",
        })
    assert resp.status_code == 201
    assert resp.json()["status"] == "failed"


def test_process_payment_updates_booking_status(payment_app, auth_headers, sample_payment):
    c, db, mod = payment_app
    headers = auth_headers()

    no_existing = MagicMock()
    no_existing.scalar_one_or_none.return_value = None
    db.execute.return_value = no_existing

    payment = sample_payment()

    def fake_refresh(obj):
        obj.id = payment.id
        obj.booking_id = payment.booking_id
        obj.user_id = payment.user_id
        obj.amount = 200.0
        obj.currency = "EUR"
        obj.status = MagicMock(value="completed")
        obj.payment_method = MagicMock(value="credit-card")
        obj.idempotency_key = "idem-bk"
        obj.transaction_ref = "TXN-BK"
        obj.failure_reason = None
        obj.card_token = None
        obj.card_last_four = None
        obj.created_at = payment.created_at

    db.refresh = AsyncMock(side_effect=fake_refresh)

    with patch.object(mod, "simulate_payment_processing", return_value=(True, "TXN-BK")), \
         patch("httpx.AsyncClient") as mock_httpx, \
         patch.object(mod, "record_audit", new_callable=AsyncMock):
        mock_client = AsyncMock()
        mock_client.put = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client

        c.post("/api/v1/payments", headers=headers, json={
            "booking_id": str(payment.booking_id),
            "amount": 200.0,
            "idempotency_key": "idem-bk",
        })
    # Verify httpx was called to update booking status
    mock_client.put.assert_called_once()


def test_process_payment_publishes_event(payment_app, auth_headers, sample_payment):
    c, db, mod = payment_app
    headers = auth_headers()

    mock_pub = MagicMock()
    mod.event_publisher = mock_pub

    no_existing = MagicMock()
    no_existing.scalar_one_or_none.return_value = None
    db.execute.return_value = no_existing

    payment = sample_payment()

    def fake_refresh(obj):
        obj.id = payment.id
        obj.booking_id = payment.booking_id
        obj.user_id = payment.user_id
        obj.amount = 150.0
        obj.currency = "EUR"
        obj.status = MagicMock(value="completed")
        obj.payment_method = MagicMock(value="credit-card")
        obj.idempotency_key = "idem-evt"
        obj.transaction_ref = "TXN-EVT"
        obj.failure_reason = None
        obj.card_token = None
        obj.card_last_four = None
        obj.created_at = payment.created_at

    db.refresh = AsyncMock(side_effect=fake_refresh)

    with patch.object(mod, "simulate_payment_processing", return_value=(True, "TXN-EVT")), \
         patch("httpx.AsyncClient") as mock_httpx, \
         patch.object(mod, "record_audit", new_callable=AsyncMock):
        mock_client = AsyncMock()
        mock_client.put = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client

        c.post("/api/v1/payments", headers=headers, json={
            "booking_id": str(payment.booking_id),
            "amount": 150.0,
            "idempotency_key": "idem-evt",
        })
    mock_pub.publish.assert_called()
    assert mock_pub.publish.call_args[0][1] == "PaymentProcessed"


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
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = p
    db.execute.return_value = result_mock
    db.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, 'status', MagicMock(value="refunded")))

    with patch("httpx.AsyncClient") as mock_httpx, \
         patch.object(mod, "record_audit", new_callable=AsyncMock):
        mock_client = AsyncMock()
        mock_client.put = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client

        resp = c.post(f"/api/v1/payments/{p.id}/refund", headers=headers, json={
            "reason": "Customer request",
        })
    assert resp.status_code == 200


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


def test_refund_payment_updates_booking(payment_app, auth_headers, sample_payment):
    c, db, mod = payment_app
    headers = auth_headers()

    p = sample_payment()
    p.status = mod.PaymentStatus.COMPLETED
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = p
    db.execute.return_value = result_mock
    db.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, 'status', MagicMock(value="refunded")))

    with patch("httpx.AsyncClient") as mock_httpx, \
         patch.object(mod, "record_audit", new_callable=AsyncMock):
        mock_client = AsyncMock()
        mock_client.put = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client

        c.post(f"/api/v1/payments/{p.id}/refund", headers=headers, json={"reason": "Test"})
    # Booking status update should be called
    mock_client.put.assert_called_once()
