"""Tests for services/checkin-service/main.py."""
import sys
import os
import uuid
import json
import importlib.util
from unittest.mock import AsyncMock, MagicMock, patch

import pybreaker
from sqlalchemy.exc import IntegrityError

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.database import Base

# Pre-mock boto3 to prevent hang when shared.events is imported
_mock_boto3 = MagicMock()
sys.modules.setdefault("boto3", _mock_boto3)


@pytest.fixture
def checkin_app(mock_db_session, auth_headers):
    svc_path = os.path.join(os.path.dirname(__file__), "..", "..", "services", "checkin-service")
    sys.path.insert(0, svc_path)
    Base.metadata.clear()
    for mod_name in ["models", "schemas"]:
        sys.modules.pop(mod_name, None)

    mock_engine = MagicMock()
    mock_engine.begin.return_value = AsyncMock()
    mock_engine.dispose = AsyncMock()

    spec = importlib.util.spec_from_file_location(
        "checkin_main", os.path.join(svc_path, "main.py"))
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


# ── assign_seat ──────────────────────────────────────────────────

def test_assign_seat_format(checkin_app):
    c, db, mod = checkin_app
    seat, group = mod.resolve_seat(None)
    assert seat[:-1].isdigit()  # row is numeric
    assert seat[-1] in "ABCDEF"
    assert group in ("A", "B", "C")


def test_assign_seat_group_a_rows_1_10(checkin_app):
    c, db, mod = checkin_app
    with patch("random.randint", return_value=5), patch("random.choice", return_value="B"):
        seat, group = mod.resolve_seat(None)
    assert seat == "5B"
    assert group == "A"


def test_assign_seat_group_b_rows_11_20(checkin_app):
    c, db, mod = checkin_app
    with patch("random.randint", return_value=15), patch("random.choice", return_value="C"):
        seat, group = mod.resolve_seat(None)
    assert seat == "15C"
    assert group == "B"


def test_assign_seat_group_c_rows_21_35(checkin_app):
    c, db, mod = checkin_app
    with patch("random.randint", return_value=25), patch("random.choice", return_value="D"):
        seat, group = mod.resolve_seat(None)
    assert seat == "25D"
    assert group == "C"


# ── Check-in ─────────────────────────────────────────────────────

def test_checkin_success(checkin_app, auth_headers):
    c, db, mod = checkin_app
    headers = auth_headers()
    booking_id = str(uuid.uuid4())
    flight_id = str(uuid.uuid4())

    # No existing check-in
    no_existing = MagicMock()
    no_existing.scalar_one_or_none.return_value = None
    db.execute.return_value = no_existing

    def fake_refresh(obj):
        obj.id = uuid.uuid4()
        obj.booking_id = booking_id
        obj.flight_id = flight_id
        obj.passenger_name = "John Doe"
        obj.seat_number = "10A"
        obj.boarding_group = "A"
        obj.gate = None
        obj.status = MagicMock(value="boarding-pass-issued")
        obj.boarding_pass_url = f"/api/v1/checkin/{booking_id}/boarding-pass"
        obj.has_baggage = False
        obj.created_at = MagicMock()

    db.refresh = AsyncMock(side_effect=fake_refresh)

    with patch("httpx.AsyncClient") as mock_httpx:
        mock_client = AsyncMock()
        mock_client.put = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client

        resp = c.post("/api/v1/checkin", headers=headers, json={
            "booking_id": booking_id,
            "flight_id": flight_id,
            "passenger_name": "John Doe",
        })
    assert resp.status_code == 201


def test_checkin_duplicate_409(checkin_app, auth_headers):
    c, db, mod = checkin_app
    headers = auth_headers()

    existing = MagicMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = existing
    db.execute.return_value = result_mock

    resp = c.post("/api/v1/checkin", headers=headers, json={
        "booking_id": str(uuid.uuid4()),
        "flight_id": str(uuid.uuid4()),
        "passenger_name": "Dup Person",
    })
    assert resp.status_code == 409


def test_checkin_publishes_event_with_boarding_group_gate(checkin_app, auth_headers):
    c, db, mod = checkin_app
    headers = auth_headers()

    mock_pub = MagicMock()
    mod.event_publisher = mock_pub

    no_existing = MagicMock()
    no_existing.scalar_one_or_none.return_value = None
    db.execute.return_value = no_existing

    def fake_refresh(obj):
        obj.id = uuid.uuid4()
        obj.booking_id = str(uuid.uuid4())
        obj.flight_id = str(uuid.uuid4())
        obj.passenger_name = "Test"
        obj.seat_number = "5A"
        obj.boarding_group = "A"
        obj.gate = None
        obj.status = MagicMock(value="boarding-pass-issued")
        obj.boarding_pass_url = "/api/v1/checkin/x/boarding-pass"
        obj.has_baggage = False
        obj.created_at = MagicMock()

    db.refresh = AsyncMock(side_effect=fake_refresh)

    with patch("httpx.AsyncClient") as mock_httpx:
        mock_client = AsyncMock()
        mock_client.put = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client

        c.post("/api/v1/checkin", headers=headers, json={
            "booking_id": str(uuid.uuid4()),
            "flight_id": str(uuid.uuid4()),
            "passenger_name": "Test",
        })
    mock_pub.publish.assert_called_once()
    call_args = mock_pub.publish.call_args
    assert call_args[0][1] == "CheckInCompleted"
    detail = call_args[0][2]
    assert "boarding_group" in detail
    assert "gate" in detail


# ── Get Check-in / Boarding Pass ─────────────────────────────────

def test_get_checkin_success(checkin_app, auth_headers):
    c, db, mod = checkin_app
    headers = auth_headers()
    checkin = MagicMock()
    checkin.id = uuid.uuid4()
    checkin.booking_id = uuid.uuid4()
    checkin.flight_id = uuid.uuid4()
    checkin.passenger_name = "Test"
    checkin.seat_number = "12B"
    checkin.boarding_group = "B"
    checkin.gate = "A5"
    checkin.status = MagicMock(value="boarding-pass-issued")
    checkin.boarding_pass_url = "/api/v1/checkin/x/boarding-pass"
    checkin.has_baggage = False
    checkin.created_at = MagicMock()

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = checkin
    db.execute.return_value = result_mock

    resp = c.get(f"/api/v1/checkin/{checkin.booking_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["seat_number"] == "12B"


def test_get_boarding_pass(checkin_app, auth_headers):
    c, db, mod = checkin_app
    headers = auth_headers()
    checkin = MagicMock()
    checkin.passenger_name = "Jane Doe"
    checkin.seat_number = "1A"
    checkin.boarding_group = "A"
    checkin.gate = "B3"
    checkin.flight_id = uuid.uuid4()

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = checkin
    db.execute.return_value = result_mock

    with patch("httpx.AsyncClient") as mock_httpx:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("no service"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client

        resp = c.get(f"/api/v1/checkin/{uuid.uuid4()}/boarding-pass", headers=headers)
    assert resp.status_code == 200
    assert "JANE DOE" in resp.text
    assert "1A" in resp.text


# ── Health ───────────────────────────────────────────────────────

def test_health_endpoint(checkin_app):
    c, db, mod = checkin_app
    resp = c.get("/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "checkin-service"


# ── 404 paths ────────────────────────────────────────────────────

def test_get_checkin_not_found(checkin_app, auth_headers):
    c, db, mod = checkin_app
    headers = auth_headers()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    resp = c.get(f"/api/v1/checkin/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404


def test_get_checkin_from_cache(checkin_app, auth_headers):
    """Cache hit on GET /checkin/{id} should bypass DB and return cached value."""
    c, db, mod = checkin_app
    headers = auth_headers()
    booking_id = str(uuid.uuid4())

    cached = {
        "id": str(uuid.uuid4()),
        "booking_id": booking_id,
        "flight_id": str(uuid.uuid4()),
        "passenger_name": "Cached Pax",
        "seat_number": "5C",
        "boarding_group": "A",
        "gate": "C1",
        "status": "boarding-pass-issued",
        "boarding_pass_url": f"/api/v1/checkin/{booking_id}/boarding-pass",
        "has_baggage": False,
        "seat_selected_by_user": True,
        "created_at": "2026-05-24T10:00:00+00:00",
    }
    mod.redis_client = MagicMock()
    mod.redis_client.get.return_value = json.dumps(cached)

    resp = c.get(f"/api/v1/checkin/{booking_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["passenger_name"] == "Cached Pax"
    db.execute.assert_not_called()


def test_checkin_flush_integrity_error_returns_409(checkin_app, auth_headers):
    """Race-condition IntegrityError on flush should return 409."""
    c, db, mod = checkin_app
    headers = auth_headers()

    no_existing = MagicMock()
    no_existing.scalar_one_or_none.return_value = None
    db.execute.return_value = no_existing
    db.flush = AsyncMock(side_effect=IntegrityError("unique constraint", None, Exception()))

    resp = c.post("/api/v1/checkin", headers=headers, json={
        "booking_id": str(uuid.uuid4()),
        "flight_id": str(uuid.uuid4()),
        "passenger_name": "Race Person",
    })
    assert resp.status_code == 409


def test_checkin_circuit_breaker_open_silenced(checkin_app, auth_headers):
    """Open circuit breaker on booking status update should not abort the check-in."""
    c, db, mod = checkin_app
    headers = auth_headers()

    no_existing = MagicMock()
    no_existing.scalar_one_or_none.return_value = None
    db.execute.return_value = no_existing

    def fake_refresh(obj):
        obj.id = uuid.uuid4()
        obj.booking_id = str(uuid.uuid4())
        obj.flight_id = str(uuid.uuid4())
        obj.passenger_name = "CB Test"
        obj.seat_number = "9D"
        obj.boarding_group = "B"
        obj.gate = None
        obj.status = MagicMock(value="boarding-pass-issued")
        obj.boarding_pass_url = "/bp"
        obj.has_baggage = False
        obj.created_at = MagicMock()

    db.refresh = AsyncMock(side_effect=fake_refresh)
    mod.event_publisher = None

    with patch.object(mod, "breaker_call_async",
                      new=AsyncMock(side_effect=pybreaker.CircuitBreakerError(mod.booking_breaker))):
        resp = c.post("/api/v1/checkin", headers=headers, json={
            "booking_id": str(uuid.uuid4()),
            "flight_id": str(uuid.uuid4()),
            "passenger_name": "CB Test",
        })
    assert resp.status_code == 201


def test_get_boarding_pass_pdf(checkin_app, auth_headers):
    """PDF boarding pass endpoint should generate and return PDF bytes."""
    c, db, mod = checkin_app
    headers = auth_headers()

    checkin = MagicMock()
    checkin.passenger_name = "JOHN DOE"
    checkin.seat_number = "12A"
    checkin.boarding_group = "B"
    checkin.gate = "A5"
    checkin.flight_id = uuid.uuid4()

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = checkin
    db.execute.return_value = result_mock

    flight_resp = MagicMock()
    flight_resp.status_code = 200
    flight_resp.json.return_value = {
        "flight_number": "AL100", "airline": "AeroLink",
        "origin": "DUB", "destination": "LHR",
        "departure_time": "10:30", "arrival_time": "12:30",
        "departure_date": "2026-06-01", "gate": "A5",
    }
    booking_resp = MagicMock()
    booking_resp.status_code = 200
    booking_resp.json.return_value = {
        "cabin_class": "economy", "booking_reference": "ALTEST01",
    }

    with patch("httpx.AsyncClient") as mock_httpx:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[flight_resp, booking_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client

        resp = c.get(f"/api/v1/checkin/{uuid.uuid4()}/boarding-pass/pdf", headers=headers)

    assert resp.status_code == 200
    assert "pdf" in resp.headers["content-type"]
    assert len(resp.content) > 0


def test_get_boarding_pass_pdf_not_found(checkin_app, auth_headers):
    c, db, mod = checkin_app
    headers = auth_headers()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    resp = c.get(f"/api/v1/checkin/{uuid.uuid4()}/boarding-pass/pdf", headers=headers)
    assert resp.status_code == 404


def test_get_boarding_pass_not_found(checkin_app, auth_headers):
    c, db, mod = checkin_app
    headers = auth_headers()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    resp = c.get(f"/api/v1/checkin/{uuid.uuid4()}/boarding-pass", headers=headers)
    assert resp.status_code == 404


# ── Exception silencing ──────────────────────────────────────────

def test_checkin_httpx_error_silenced(checkin_app, auth_headers):
    """Booking status update httpx failure should not abort check-in."""
    c, db, mod = checkin_app
    headers = auth_headers()
    booking_id = str(uuid.uuid4())
    flight_id = str(uuid.uuid4())

    no_existing = MagicMock()
    no_existing.scalar_one_or_none.return_value = None
    db.execute.return_value = no_existing

    def fake_refresh(obj):
        obj.id = uuid.uuid4()
        obj.booking_id = booking_id
        obj.flight_id = flight_id
        obj.passenger_name = "Test"
        obj.seat_number = "7B"
        obj.boarding_group = "A"
        obj.gate = None
        obj.status = MagicMock(value="boarding-pass-issued")
        obj.boarding_pass_url = f"/api/v1/checkin/{booking_id}/boarding-pass"
        obj.has_baggage = False
        obj.created_at = MagicMock()

    db.refresh = AsyncMock(side_effect=fake_refresh)
    mod.event_publisher = None

    with patch("httpx.AsyncClient") as mock_httpx:
        mock_client = AsyncMock()
        mock_client.put = AsyncMock(side_effect=Exception("booking service down"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client

        resp = c.post("/api/v1/checkin", headers=headers, json={
            "booking_id": booking_id,
            "flight_id": flight_id,
            "passenger_name": "Test",
        })
    assert resp.status_code == 201


def test_checkin_publisher_exception_silenced(checkin_app, auth_headers):
    """Event publisher failure should not abort check-in."""
    c, db, mod = checkin_app
    headers = auth_headers()
    booking_id = str(uuid.uuid4())
    flight_id = str(uuid.uuid4())

    no_existing = MagicMock()
    no_existing.scalar_one_or_none.return_value = None
    db.execute.return_value = no_existing

    def fake_refresh(obj):
        obj.id = uuid.uuid4()
        obj.booking_id = booking_id
        obj.flight_id = flight_id
        obj.passenger_name = "Test"
        obj.seat_number = "8C"
        obj.boarding_group = "B"
        obj.gate = None
        obj.status = MagicMock(value="boarding-pass-issued")
        obj.boarding_pass_url = f"/api/v1/checkin/{booking_id}/boarding-pass"
        obj.has_baggage = False
        obj.created_at = MagicMock()

    db.refresh = AsyncMock(side_effect=fake_refresh)

    mock_pub = MagicMock()
    mock_pub.publish.side_effect = Exception("eventbridge down")
    mod.event_publisher = mock_pub

    with patch("httpx.AsyncClient") as mock_httpx:
        mock_client = AsyncMock()
        mock_client.put = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client

        resp = c.post("/api/v1/checkin", headers=headers, json={
            "booking_id": booking_id,
            "flight_id": flight_id,
            "passenger_name": "Test",
        })
    assert resp.status_code == 201
