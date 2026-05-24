"""Tests for services/baggage-service/main.py."""
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
def baggage_app(mock_db_session, auth_headers):
    svc_path = os.path.join(os.path.dirname(__file__), "..", "services", "baggage-service")
    sys.path.insert(0, svc_path)
    Base.metadata.clear()
    for mod_name in ["models", "schemas"]:
        sys.modules.pop(mod_name, None)

    mock_engine = MagicMock()
    mock_engine.begin.return_value = AsyncMock()
    mock_engine.dispose = AsyncMock()

    spec = importlib.util.spec_from_file_location(
        "baggage_main", os.path.join(svc_path, "main.py"))
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


def _make_baggage(**overrides):
    b = MagicMock()
    b.id = overrides.get("id", uuid.uuid4())
    b.tag_number = overrides.get("tag_number", "BAG-0001234567")
    b.booking_id = overrides.get("booking_id", uuid.uuid4())
    b.passenger_name = overrides.get("passenger_name", "John Doe")
    b.flight_id = overrides.get("flight_id", uuid.uuid4())
    b.weight_kg = overrides.get("weight_kg", 23.5)
    b.status = MagicMock(value=overrides.get("status", "registered"))
    b.last_location = overrides.get("last_location", "Check-in Counter")
    b.description = overrides.get("description", "Black suitcase")
    b.created_at = overrides.get("created_at", MagicMock())
    return b


# ── generate_tag ─────────────────────────────────────────────────

def test_generate_tag_format(baggage_app):
    c, db, mod = baggage_app
    tag = mod.generate_tag()
    assert tag.startswith("BAG-")
    assert len(tag) == 14  # BAG- + 10 digits
    assert tag[4:].isdigit()


# ── Register Baggage ─────────────────────────────────────────────

def test_register_baggage_success(baggage_app, auth_headers):
    c, db, mod = baggage_app
    headers = auth_headers()

    def fake_refresh(obj):
        obj.id = uuid.uuid4()
        obj.tag_number = "BAG-1234567890"
        obj.booking_id = uuid.uuid4()
        obj.passenger_name = "John Doe"
        obj.flight_id = uuid.uuid4()
        obj.weight_kg = 23.5
        obj.status = MagicMock(value="registered")
        obj.last_location = None
        obj.description = "Blue bag"
        obj.created_at = MagicMock()

    db.refresh = AsyncMock(side_effect=fake_refresh)

    resp = c.post("/api/v1/baggage", headers=headers, json={
        "booking_id": str(uuid.uuid4()),
        "passenger_name": "John Doe",
        "flight_id": str(uuid.uuid4()),
        "weight_kg": 23.5,
        "description": "Blue bag",
    })
    assert resp.status_code == 201
    assert resp.json()["tag_number"].startswith("BAG-")


# ── Track Baggage ────────────────────────────────────────────────

def test_track_baggage_found(baggage_app):
    c, db, mod = baggage_app
    bag = _make_baggage()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = bag
    db.execute.return_value = result_mock

    resp = c.get(f"/api/v1/baggage/{bag.tag_number}")
    assert resp.status_code == 200
    assert resp.json()["tag_number"] == bag.tag_number


def test_track_baggage_not_found(baggage_app):
    c, db, mod = baggage_app
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    resp = c.get("/api/v1/baggage/BAG-9999999999")
    assert resp.status_code == 404


# ── Get Baggage by Booking ───────────────────────────────────────

def test_get_baggage_by_booking(baggage_app, auth_headers):
    c, db, mod = baggage_app
    headers = auth_headers()
    bag = _make_baggage()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [bag]
    db.execute.return_value = result_mock

    resp = c.get(f"/api/v1/baggage/booking/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── Update Baggage Status ────────────────────────────────────────

def test_update_baggage_status_success(baggage_app, auth_headers):
    c, db, mod = baggage_app
    headers = auth_headers(role="admin")
    bag = _make_baggage()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = bag
    db.execute.return_value = result_mock
    db.refresh = AsyncMock(side_effect=lambda obj: None)

    resp = c.put(f"/api/v1/baggage/{bag.tag_number}/status", headers=headers, json={
        "status": "loaded",
        "location": "Aircraft Hold",
    })
    assert resp.status_code == 200


def test_update_baggage_status_publishes_event(baggage_app, auth_headers):
    c, db, mod = baggage_app
    headers = auth_headers(role="admin")
    mock_pub = MagicMock()
    mod.event_publisher = mock_pub

    bag = _make_baggage()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = bag
    db.execute.return_value = result_mock
    db.refresh = AsyncMock(side_effect=lambda obj: None)

    c.put(f"/api/v1/baggage/{bag.tag_number}/status", headers=headers, json={
        "status": "in-transit",
        "location": "In Flight",
    })
    mock_pub.publish.assert_called_once()
    assert mock_pub.publish.call_args[0][1] == "BaggageStatusChanged"


# ── Health ───────────────────────────────────────────────────────

def test_health_endpoint(baggage_app):
    c, db, mod = baggage_app
    resp = c.get("/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "baggage-service"


# ── 404 paths ────────────────────────────────────────────────────

def test_update_baggage_status_not_found(baggage_app, auth_headers):
    c, db, mod = baggage_app
    headers = auth_headers(role="admin")
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    resp = c.put("/api/v1/baggage/BAG-0000000000/status", headers=headers, json={"status": "loaded"})
    assert resp.status_code == 404


# ── Exception silencing ──────────────────────────────────────────

def test_update_baggage_publisher_exception_silenced(baggage_app, auth_headers):
    c, db, mod = baggage_app
    headers = auth_headers(role="admin")

    mock_pub = MagicMock()
    mock_pub.publish.side_effect = Exception("eventbridge down")
    mod.event_publisher = mock_pub

    bag = _make_baggage()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = bag
    db.execute.return_value = result_mock
    db.refresh = AsyncMock(side_effect=lambda obj: None)

    resp = c.put(f"/api/v1/baggage/{bag.tag_number}/status", headers=headers, json={
        "status": "loaded",
        "location": "Baggage Hall",
    })
    assert resp.status_code == 200


# ── Validation (422) ─────────────────────────────────────────────

def test_register_baggage_missing_required_field_422(baggage_app, auth_headers):
    c, db, mod = baggage_app
    headers = auth_headers()
    resp = c.post("/api/v1/baggage", headers=headers, json={
        "booking_id": str(uuid.uuid4()),
        # passenger_name and flight_id omitted
    })
    assert resp.status_code == 422


def test_update_baggage_status_missing_status_422(baggage_app, auth_headers):
    c, db, mod = baggage_app
    headers = auth_headers(role="admin")
    resp = c.put("/api/v1/baggage/BAG-1234567890/status", headers=headers, json={
        "location": "Gate B3"
        # status required but omitted
    })
    assert resp.status_code == 422
