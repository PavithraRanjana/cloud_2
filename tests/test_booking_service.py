"""Tests for services/booking-service/main.py."""
import sys
import os
import uuid
import importlib.util
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.database import Base

# Pre-mock boto3 to prevent hang when shared.events is imported
_mock_boto3 = MagicMock()
sys.modules.setdefault("boto3", _mock_boto3)


@pytest.fixture
def booking_app(mock_db_session, auth_headers):
    svc_path = os.path.join(os.path.dirname(__file__), "..", "services", "booking-service")
    sys.path.insert(0, svc_path)
    Base.metadata.clear()
    for mod_name in ["models", "schemas"]:
        sys.modules.pop(mod_name, None)

    mock_engine = MagicMock()
    mock_engine.begin.return_value = AsyncMock()
    mock_engine.dispose = AsyncMock()

    spec = importlib.util.spec_from_file_location(
        "booking_main", os.path.join(svc_path, "main.py"))
    mod = importlib.util.module_from_spec(spec)
    with patch("shared.database.create_db_engine", return_value=mock_engine), \
         patch("shared.database.create_session_factory"), \
         patch("shared.logging.setup_logging"), \
         patch("shared.resilience.create_circuit_breaker", return_value=MagicMock()):
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


# ── generate_booking_ref ─────────────────────────────────────────

def test_generate_booking_ref_format(booking_app):
    c, db, mod = booking_app
    ref = mod.generate_booking_ref()
    assert ref.startswith("AL")
    assert len(ref) == 8


def test_generate_booking_ref_uniqueness(booking_app):
    c, db, mod = booking_app
    refs = {mod.generate_booking_ref() for _ in range(100)}
    assert len(refs) > 90  # Should be mostly unique


# ── Create Booking ───────────────────────────────────────────────

def test_create_booking_success(booking_app, auth_headers, sample_booking):
    c, db, mod = booking_app
    headers = auth_headers(role="passenger")
    flight_id = str(uuid.uuid4())

    # Mock httpx calls (flight lookup + seat reserve)
    flight_resp = MagicMock()
    flight_resp.status_code = 200
    flight_resp.json.return_value = {
        "available_seats_economy": 100,
        "price_economy": 199.99,
    }
    flight_resp.raise_for_status = MagicMock()

    seat_resp = MagicMock()
    seat_resp.status_code = 200
    seat_resp.raise_for_status = MagicMock()

    booking = sample_booking(flight_id=flight_id)

    def fake_refresh(obj):
        obj.id = booking.id
        obj.booking_reference = "AL1TEST1"
        obj.user_id = booking.user_id
        obj.flight_id = flight_id
        obj.passenger_name = "John Doe"
        obj.passenger_email = "john@example.com"
        obj.cabin_class = "economy"
        obj.num_passengers = 1
        obj.total_price = 199.99
        obj.status = MagicMock(value="pending")
        obj.payment_id = None
        obj.seat_numbers = None
        obj.special_requests = None
        obj.created_at = booking.created_at

    db.refresh = AsyncMock(side_effect=fake_refresh)

    with patch("httpx.AsyncClient") as mock_httpx:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=flight_resp)
        mock_client.put = AsyncMock(return_value=seat_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client

        resp = c.post("/api/v1/bookings", headers=headers, json={
            "flight_id": flight_id,
            "passenger_name": "John Doe",
            "passenger_email": "john@example.com",
            "cabin_class": "economy",
            "num_passengers": 1,
        })
    assert resp.status_code == 201


def test_create_booking_insufficient_seats(booking_app, auth_headers):
    c, db, mod = booking_app
    headers = auth_headers()
    flight_id = str(uuid.uuid4())

    flight_resp = MagicMock()
    flight_resp.status_code = 200
    flight_resp.json.return_value = {"available_seats_economy": 0, "price_economy": 199.99}
    flight_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_httpx:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=flight_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client

        resp = c.post("/api/v1/bookings", headers=headers, json={
            "flight_id": flight_id,
            "passenger_name": "Jane Doe",
            "passenger_email": "jane@example.com",
            "cabin_class": "economy",
            "num_passengers": 5,
        })
    assert resp.status_code == 409


def test_create_booking_flight_not_found(booking_app, auth_headers):
    c, db, mod = booking_app
    headers = auth_headers()

    flight_resp = MagicMock()
    flight_resp.status_code = 404
    flight_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404 Not Found", request=MagicMock(), response=flight_resp)

    with patch("httpx.AsyncClient") as mock_httpx:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=flight_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client

        resp = c.post("/api/v1/bookings", headers=headers, json={
            "flight_id": str(uuid.uuid4()),
            "passenger_name": "Test",
            "passenger_email": "test@test.com",
            "cabin_class": "economy",
            "num_passengers": 1,
        })
    assert resp.status_code == 404


def test_create_booking_publishes_event(booking_app, auth_headers, sample_booking):
    c, db, mod = booking_app
    headers = auth_headers()
    flight_id = str(uuid.uuid4())

    mock_pub = MagicMock()
    mod.event_publisher = mock_pub

    flight_resp = MagicMock()
    flight_resp.status_code = 200
    flight_resp.json.return_value = {"available_seats_economy": 50, "price_economy": 100.0}
    flight_resp.raise_for_status = MagicMock()

    seat_resp = MagicMock()
    seat_resp.status_code = 200
    seat_resp.raise_for_status = MagicMock()

    booking = sample_booking()

    def fake_refresh(obj):
        obj.id = booking.id
        obj.booking_reference = "ALTEST11"
        obj.user_id = booking.user_id
        obj.flight_id = flight_id
        obj.passenger_name = "Test"
        obj.passenger_email = "t@t.com"
        obj.cabin_class = "economy"
        obj.num_passengers = 1
        obj.total_price = 100.0
        obj.status = MagicMock(value="pending")
        obj.payment_id = None
        obj.seat_numbers = None
        obj.special_requests = None
        obj.created_at = booking.created_at

    db.refresh = AsyncMock(side_effect=fake_refresh)

    with patch("httpx.AsyncClient") as mock_httpx:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=flight_resp)
        mock_client.put = AsyncMock(return_value=seat_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client

        c.post("/api/v1/bookings", headers=headers, json={
            "flight_id": flight_id,
            "passenger_name": "Test",
            "passenger_email": "t@t.com",
            "cabin_class": "economy",
            "num_passengers": 1,
        })
    mock_pub.publish.assert_called_once()
    assert mock_pub.publish.call_args[0][1] == "BookingCreated"


def test_create_booking_conflict_retry(booking_app, auth_headers):
    c, db, mod = booking_app
    headers = auth_headers()

    flight_resp = MagicMock()
    flight_resp.status_code = 200
    flight_resp.json.return_value = {"available_seats_economy": 10, "price_economy": 100.0}
    flight_resp.raise_for_status = MagicMock()

    seat_resp = MagicMock()
    seat_resp.status_code = 409

    with patch("httpx.AsyncClient") as mock_httpx:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=flight_resp)
        mock_client.put = AsyncMock(return_value=seat_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client

        resp = c.post("/api/v1/bookings", headers=headers, json={
            "flight_id": str(uuid.uuid4()),
            "passenger_name": "Test",
            "passenger_email": "t@t.com",
            "cabin_class": "economy",
            "num_passengers": 1,
        })
    assert resp.status_code == 409


# ── List / Get Bookings ──────────────────────────────────────────

def test_list_bookings_returns_user_bookings(booking_app, auth_headers, sample_booking):
    c, db, mod = booking_app
    headers = auth_headers()
    b = sample_booking()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [b]
    db.execute.return_value = result_mock

    resp = c.get("/api/v1/bookings", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_booking_success(booking_app, auth_headers, sample_booking):
    c, db, mod = booking_app
    headers = auth_headers()
    b = sample_booking()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = b
    db.execute.return_value = result_mock

    resp = c.get(f"/api/v1/bookings/{b.id}", headers=headers)
    assert resp.status_code == 200


def test_get_booking_not_found(booking_app, auth_headers):
    c, db, mod = booking_app
    headers = auth_headers()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    resp = c.get(f"/api/v1/bookings/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404


# ── Cancel Booking ───────────────────────────────────────────────

def test_cancel_booking_success_releases_seats(booking_app, auth_headers, sample_booking):
    c, db, mod = booking_app
    headers = auth_headers()
    b = sample_booking(status="pending")
    # Make status comparison work properly
    from unittest.mock import PropertyMock
    b.status.__eq__ = lambda s, o: False  # not CANCELLED or REFUNDED
    b.status.__ne__ = lambda s, o: True
    # Ensure `in` check works: booking.status in (CANCELLED, REFUNDED) should be False
    b.status.__hash__ = lambda s: hash("pending")

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = b
    db.execute.return_value = result_mock
    db.refresh = AsyncMock(side_effect=lambda obj: None)

    seat_resp = MagicMock()
    seat_resp.status_code = 200

    with patch("httpx.AsyncClient") as mock_httpx:
        mock_client = AsyncMock()
        mock_client.put = AsyncMock(return_value=seat_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client

        resp = c.post(f"/api/v1/bookings/{b.id}/cancel", headers=headers)
    assert resp.status_code == 200


def test_cancel_booking_already_cancelled(booking_app, auth_headers, sample_booking):
    c, db, mod = booking_app
    headers = auth_headers()

    b = sample_booking(status="cancelled")
    b.status = mod.BookingStatus.CANCELLED

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = b
    db.execute.return_value = result_mock

    resp = c.post(f"/api/v1/bookings/{b.id}/cancel", headers=headers)
    assert resp.status_code == 400


# ── Health ───────────────────────────────────────────────────────

def test_health_endpoint(booking_app):
    c, db, mod = booking_app
    resp = c.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "booking-service"


# ── Update Status 404 ────────────────────────────────────────────

def test_update_booking_status_not_found(booking_app):
    c, db, mod = booking_app
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    resp = c.put(f"/api/v1/bookings/{uuid.uuid4()}/status", json={"status": "paid"})
    assert resp.status_code == 404


# ── Cancel 404 ───────────────────────────────────────────────────

def test_cancel_booking_not_found(booking_app, auth_headers):
    c, db, mod = booking_app
    headers = auth_headers()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    resp = c.post(f"/api/v1/bookings/{uuid.uuid4()}/cancel", headers=headers)
    assert resp.status_code == 404


# ── Exception silencing ──────────────────────────────────────────

def test_create_booking_publisher_exception_silenced(booking_app, auth_headers, sample_booking):
    """Event publisher failure should not abort the booking creation."""
    c, db, mod = booking_app
    headers = auth_headers()
    flight_id = str(uuid.uuid4())

    mock_pub = MagicMock()
    mock_pub.publish.side_effect = Exception("eventbridge down")
    mod.event_publisher = mock_pub

    flight_resp = MagicMock()
    flight_resp.status_code = 200
    flight_resp.json.return_value = {"available_seats_economy": 50, "price_economy": 100.0}
    flight_resp.raise_for_status = MagicMock()

    seat_resp = MagicMock()
    seat_resp.status_code = 200
    seat_resp.raise_for_status = MagicMock()

    booking = sample_booking()

    def fake_refresh(obj):
        obj.id = booking.id
        obj.booking_reference = "ALSILENT1"
        obj.user_id = booking.user_id
        obj.flight_id = flight_id
        obj.passenger_name = "Test"
        obj.passenger_email = "t@t.com"
        obj.cabin_class = "economy"
        obj.num_passengers = 1
        obj.total_price = 100.0
        obj.status = MagicMock(value="pending")
        obj.payment_id = None
        obj.seat_numbers = None
        obj.special_requests = None
        obj.created_at = booking.created_at

    db.refresh = AsyncMock(side_effect=fake_refresh)

    with patch("httpx.AsyncClient") as mock_httpx:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=flight_resp)
        mock_client.put = AsyncMock(return_value=seat_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client

        resp = c.post("/api/v1/bookings", headers=headers, json={
            "flight_id": flight_id,
            "passenger_name": "Test",
            "passenger_email": "t@t.com",
            "cabin_class": "economy",
            "num_passengers": 1,
        })
    assert resp.status_code == 201


def test_cancel_booking_httpx_error_silenced(booking_app, auth_headers, sample_booking):
    """Seat release httpx failure should not abort the cancel."""
    c, db, mod = booking_app
    headers = auth_headers()

    b = sample_booking()
    b.status = mod.BookingStatus.PENDING
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = b
    db.execute.return_value = result_mock
    db.refresh = AsyncMock(side_effect=lambda obj: None)
    mod.event_publisher = None

    with patch("httpx.AsyncClient") as mock_httpx:
        mock_client = AsyncMock()
        mock_client.put = AsyncMock(side_effect=Exception("connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client

        resp = c.post(f"/api/v1/bookings/{b.id}/cancel", headers=headers)
    assert resp.status_code == 200


def test_cancel_booking_publisher_exception_silenced(booking_app, auth_headers, sample_booking):
    """Event publisher failure during cancel should not abort the response."""
    c, db, mod = booking_app
    headers = auth_headers()

    b = sample_booking()
    b.status = mod.BookingStatus.PENDING
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = b
    db.execute.return_value = result_mock
    db.refresh = AsyncMock(side_effect=lambda obj: None)

    mock_pub = MagicMock()
    mock_pub.publish.side_effect = Exception("eventbridge down")
    mod.event_publisher = mock_pub

    seat_resp = MagicMock()
    seat_resp.status_code = 200

    with patch("httpx.AsyncClient") as mock_httpx:
        mock_client = AsyncMock()
        mock_client.put = AsyncMock(return_value=seat_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client

        resp = c.post(f"/api/v1/bookings/{b.id}/cancel", headers=headers)
    assert resp.status_code == 200
