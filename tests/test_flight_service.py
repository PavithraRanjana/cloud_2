"""Tests for services/flight-service/main.py."""
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
def flight_app(mock_db_session, mock_redis, auth_headers):
    """Load flight service with mocked dependencies."""
    svc_path = os.path.join(os.path.dirname(__file__), "..", "services", "flight-service")
    sys.path.insert(0, svc_path)
    Base.metadata.clear()
    for mod_name in ["models", "schemas"]:
        sys.modules.pop(mod_name, None)

    mock_engine = MagicMock()
    mock_engine.begin.return_value = AsyncMock()
    mock_engine.dispose = AsyncMock()

    spec = importlib.util.spec_from_file_location(
        "flight_main", os.path.join(svc_path, "main.py"))
    mod = importlib.util.module_from_spec(spec)
    with patch("shared.database.create_db_engine", return_value=mock_engine), \
         patch("shared.database.create_session_factory"), \
         patch("shared.logging.setup_logging"), \
         patch("redis.Redis.from_url", return_value=mock_redis):
        spec.loader.exec_module(mod)

    mod.redis_client = mock_redis

    async def mock_get_db():
        yield mock_db_session

    mod.app.dependency_overrides[mod.get_db] = mock_get_db
    with TestClient(mod.app, raise_server_exceptions=False) as c:
        yield c, mock_db_session, mod, mock_redis
    mod.app.dependency_overrides.clear()
    for mod_name in ["models", "schemas"]:
        sys.modules.pop(mod_name, None)
    if svc_path in sys.path:
        sys.path.remove(svc_path)


# ── Create Flight ────────────────────────────────────────────────

def test_create_flight_success(flight_app, auth_headers, sample_flight):
    c, db, mod, redis = flight_app
    headers = auth_headers(role="admin")

    flight = sample_flight()

    def fake_refresh(obj):
        obj.id = flight.id
        obj.flight_number = "AL200"
        obj.airline = "AeroLink"
        obj.origin = "DUB"
        obj.destination = "LHR"
        obj.departure_date = flight.departure_date
        obj.departure_time = flight.departure_time
        obj.arrival_date = flight.arrival_date
        obj.arrival_time = flight.arrival_time
        obj.status = flight.status
        obj.aircraft_type = "A320"
        obj.available_seats_economy = 150
        obj.available_seats_business = 30
        obj.available_seats_first = 10
        obj.price_economy = 199.99
        obj.price_business = 599.99
        obj.price_first = 1299.99
        obj.gate = "A1"
        obj.terminal = "T1"
        obj.created_at = flight.created_at

    db.refresh = AsyncMock(side_effect=fake_refresh)
    mod.event_publisher = None

    resp = c.post("/api/v1/flights", headers=headers, json={
        "flight_number": "AL200",
        "airline": "AeroLink",
        "origin": "dub",
        "destination": "lhr",
        "departure_date": "2025-06-01",
        "departure_time": "10:00:00",
        "arrival_date": "2025-06-01",
        "arrival_time": "11:30:00",
        "aircraft_type": "A320",
        "total_seats_economy": 150,
        "total_seats_business": 30,
        "total_seats_first": 10,
        "price_economy": 199.99,
        "price_business": 599.99,
        "price_first": 1299.99,
    })
    assert resp.status_code == 201


def test_create_flight_sets_available_from_total(flight_app, auth_headers):
    """available_seats should be set from total_seats on creation."""
    c, db, mod, redis = flight_app
    headers = auth_headers(role="admin")

    captured_flight = {}

    original_add = db.add

    def capture_add(obj):
        captured_flight["obj"] = obj
        return original_add(obj)

    db.add = capture_add

    def fake_refresh(obj):
        obj.id = uuid.uuid4()
        obj.flight_number = "AL201"
        obj.airline = "AeroLink"
        obj.origin = "DUB"
        obj.destination = "LHR"
        obj.departure_date = "2025-06-01"
        obj.departure_time = "10:00:00"
        obj.arrival_date = "2025-06-01"
        obj.arrival_time = "11:30:00"
        obj.status = MagicMock(value="scheduled")
        obj.aircraft_type = "A320"
        obj.available_seats_economy = 100
        obj.available_seats_business = 20
        obj.available_seats_first = 5
        obj.price_economy = 99.0
        obj.price_business = 299.0
        obj.price_first = 799.0
        obj.gate = None
        obj.terminal = None
        obj.created_at = MagicMock(isoformat=MagicMock(return_value="2025-01-01"))

    db.refresh = AsyncMock(side_effect=fake_refresh)
    mod.event_publisher = None

    resp = c.post("/api/v1/flights", headers=headers, json={
        "flight_number": "AL201",
        "airline": "AeroLink",
        "origin": "DUB",
        "destination": "LHR",
        "departure_date": "2025-06-01",
        "departure_time": "10:00:00",
        "arrival_date": "2025-06-01",
        "arrival_time": "11:30:00",
        "total_seats_economy": 100,
        "total_seats_business": 20,
        "total_seats_first": 5,
        "price_economy": 99.0,
        "price_business": 299.0,
        "price_first": 799.0,
    })
    assert resp.status_code == 201
    # The created flight object should have available = total
    if "obj" in captured_flight:
        obj = captured_flight["obj"]
        assert obj.available_seats_economy == obj.total_seats_economy


def test_create_flight_uppercases_origin_destination(flight_app, auth_headers):
    c, db, mod, redis = flight_app
    headers = auth_headers(role="admin")

    captured = {}

    orig_add = db.add

    def capture(obj):
        captured["obj"] = obj
        return orig_add(obj)

    db.add = capture

    def fake_refresh(obj):
        obj.id = uuid.uuid4()
        obj.flight_number = "AL202"
        obj.airline = "AeroLink"
        obj.origin = "DUB"
        obj.destination = "CDG"
        obj.departure_date = "2025-06-01"
        obj.departure_time = "10:00:00"
        obj.arrival_date = "2025-06-01"
        obj.arrival_time = "12:00:00"
        obj.status = MagicMock(value="scheduled")
        obj.aircraft_type = "B737"
        obj.available_seats_economy = 150
        obj.available_seats_business = 30
        obj.available_seats_first = 10
        obj.price_economy = 199.99
        obj.price_business = 599.99
        obj.price_first = 1299.99
        obj.gate = None
        obj.terminal = None
        obj.created_at = MagicMock(isoformat=MagicMock(return_value="2025-01-01"))

    db.refresh = AsyncMock(side_effect=fake_refresh)
    mod.event_publisher = None

    c.post("/api/v1/flights", headers=headers, json={
        "flight_number": "AL202",
        "airline": "AeroLink",
        "origin": "dub",
        "destination": "cdg",
        "departure_date": "2025-06-01",
        "departure_time": "10:00:00",
        "arrival_date": "2025-06-01",
        "arrival_time": "12:00:00",
        "total_seats_economy": 150,
        "total_seats_business": 30,
        "total_seats_first": 10,
        "price_economy": 199.99,
        "price_business": 599.99,
        "price_first": 1299.99,
    })
    if "obj" in captured:
        assert captured["obj"].origin == "DUB"
        assert captured["obj"].destination == "CDG"


# ── Get Flight ───────────────────────────────────────────────────

def test_get_flight_cache_hit(flight_app):
    c, db, mod, redis = flight_app
    cached_data = json.dumps({
        "id": str(uuid.uuid4()), "flight_number": "AL100",
        "airline": "AeroLink", "origin": "DUB", "destination": "LHR",
        "departure_date": "2025-06-01", "departure_time": "10:00:00",
        "arrival_date": "2025-06-01", "arrival_time": "11:30:00",
        "status": "scheduled", "aircraft_type": "A320",
        "available_seats_economy": 150, "available_seats_business": 30,
        "available_seats_first": 10, "price_economy": 199.99,
        "price_business": 599.99, "price_first": 1299.99,
        "gate": "A1", "terminal": "T1", "created_at": "2025-01-01T00:00:00",
    })
    redis.get = MagicMock(return_value=cached_data)
    resp = c.get(f"/api/v1/flights/{uuid.uuid4()}")
    assert resp.status_code == 200
    assert resp.json()["flight_number"] == "AL100"


def test_get_flight_cache_miss_fetches_db(flight_app, sample_flight):
    c, db, mod, redis = flight_app
    redis.get = MagicMock(return_value=None)

    flight = sample_flight()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = flight
    db.execute.return_value = result_mock

    resp = c.get(f"/api/v1/flights/{flight.id}")
    assert resp.status_code == 200


def test_get_flight_not_found(flight_app):
    c, db, mod, redis = flight_app
    redis.get = MagicMock(return_value=None)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    resp = c.get(f"/api/v1/flights/{uuid.uuid4()}")
    assert resp.status_code == 404


# ── Search Flights ───────────────────────────────────────────────

def test_search_flights_no_filters(flight_app, sample_flight):
    c, db, mod, redis = flight_app
    redis.get = MagicMock(return_value=None)

    f = sample_flight()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [f]
    db.execute.return_value = result_mock

    resp = c.get("/api/v1/flights")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body


def test_search_flights_with_origin_destination(flight_app, sample_flight):
    c, db, mod, redis = flight_app
    redis.get = MagicMock(return_value=None)

    f = sample_flight(origin="DUB", destination="LHR")
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [f]
    db.execute.return_value = result_mock

    resp = c.get("/api/v1/flights?origin=DUB&destination=LHR")
    assert resp.status_code == 200


def test_search_flights_price_range_filter(flight_app, sample_flight):
    c, db, mod, redis = flight_app
    redis.get = MagicMock(return_value=None)

    f = sample_flight(price_economy=250.0)
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [f]
    db.execute.return_value = result_mock

    resp = c.get("/api/v1/flights?min_price=100&max_price=300&cabin_class=economy")
    assert resp.status_code == 200


def test_search_flights_pagination_cursor(flight_app, sample_flight):
    c, db, mod, redis = flight_app
    f = sample_flight()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [f]
    db.execute.return_value = result_mock

    resp = c.get(f"/api/v1/flights?cursor={uuid.uuid4()}")
    assert resp.status_code == 200


def test_search_flights_cache_hit(flight_app):
    c, db, mod, redis = flight_app
    cached = json.dumps([{"id": str(uuid.uuid4()), "flight_number": "AL100"}])
    redis.get = MagicMock(return_value=cached)

    resp = c.get("/api/v1/flights?origin=DUB&destination=LHR")
    assert resp.status_code == 200
    assert resp.json()["source"] == "cache"


# ── Update Flight ────────────────────────────────────────────────

def test_update_flight_partial_fields(flight_app, auth_headers, sample_flight):
    c, db, mod, redis = flight_app
    headers = auth_headers(role="admin")
    flight = sample_flight()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = flight
    db.execute.return_value = result_mock

    db.refresh = AsyncMock(side_effect=lambda obj: None)
    mod.event_publisher = None

    resp = c.put(f"/api/v1/flights/{flight.id}", headers=headers, json={
        "gate": "B5",
    })
    assert resp.status_code == 200


def test_update_flight_invalidates_cache(flight_app, auth_headers, sample_flight):
    c, db, mod, redis = flight_app
    headers = auth_headers(role="admin")
    flight = sample_flight()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = flight
    db.execute.return_value = result_mock
    db.refresh = AsyncMock(side_effect=lambda obj: None)
    mod.event_publisher = None

    c.put(f"/api/v1/flights/{flight.id}", headers=headers, json={"gate": "C1"})
    # Redis keys/delete should have been called for cache invalidation
    assert redis.keys.called or redis.delete.called


# ── Update Seats ─────────────────────────────────────────────────

def test_update_seats_success_increments_version(flight_app, sample_flight):
    c, db, mod, redis = flight_app
    flight = sample_flight(available_seats_economy=100, version=1)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = flight
    update_result = MagicMock()
    update_result.rowcount = 1
    db.execute.side_effect = [result_mock, update_result]
    mod.event_publisher = None

    resp = c.put(f"/api/v1/flights/{flight.id}/seats", json={
        "cabin_class": "economy", "change": -2,
    })
    assert resp.status_code == 200
    assert resp.json()["version"] == 2


def test_update_seats_prevents_negative(flight_app, sample_flight):
    c, db, mod, redis = flight_app
    flight = sample_flight(available_seats_economy=1, version=1)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = flight
    db.execute.return_value = result_mock

    resp = c.put(f"/api/v1/flights/{flight.id}/seats", json={
        "cabin_class": "economy", "change": -5,
    })
    assert resp.status_code == 409


def test_update_seats_optimistic_lock_conflict(flight_app, sample_flight):
    c, db, mod, redis = flight_app
    flight = sample_flight(available_seats_economy=50, version=1)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = flight
    update_result = MagicMock()
    update_result.rowcount = 0  # conflict
    db.execute.side_effect = [result_mock, update_result]
    mod.event_publisher = None

    resp = c.put(f"/api/v1/flights/{flight.id}/seats", json={
        "cabin_class": "economy", "change": -1,
    })
    assert resp.status_code == 409
    assert "Concurrent" in resp.json()["detail"]


# ── Health ───────────────────────────────────────────────────────

def test_health_endpoint_with_redis(flight_app):
    c, db, mod, redis = flight_app
    resp = c.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "flight-service"
    assert body["dependencies"]["redis_cache"] == "healthy"


# ── Search – departure_date filter ───────────────────────────────

def test_search_flights_with_departure_date(flight_app, sample_flight):
    c, db, mod, redis = flight_app
    redis.get = MagicMock(return_value=None)

    f = sample_flight()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [f]
    db.execute.return_value = result_mock

    resp = c.get("/api/v1/flights?departure_date=2026-06-15")
    assert resp.status_code == 200
    assert "items" in resp.json()


# ── Search – cache populate after DB miss ────────────────────────

def test_search_flights_cache_populate_after_db(flight_app, sample_flight):
    c, db, mod, redis = flight_app
    redis.get = MagicMock(return_value=None)

    f = sample_flight()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [f]
    db.execute.return_value = result_mock

    c.get("/api/v1/flights?origin=DUB&destination=LHR")
    redis.setex.assert_called()


# ── Search – redis.get raises, falls back to DB ──────────────────

def test_search_flights_redis_exception_falls_back(flight_app, sample_flight):
    c, db, mod, redis = flight_app
    redis.get = MagicMock(side_effect=Exception("redis down"))

    f = sample_flight()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [f]
    db.execute.return_value = result_mock

    resp = c.get("/api/v1/flights?origin=DUB")
    assert resp.status_code == 200
    assert resp.json()["source"] == "database"


# ── Get flight – redis.get raises, falls back to DB ──────────────

def test_get_flight_redis_exception_falls_back(flight_app, sample_flight):
    c, db, mod, redis = flight_app
    redis.get = MagicMock(side_effect=Exception("redis down"))

    flight = sample_flight()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = flight
    db.execute.return_value = result_mock

    resp = c.get(f"/api/v1/flights/{flight.id}")
    assert resp.status_code == 200


# ── Get flight – redis.setex raises after DB fetch ───────────────

def test_get_flight_cache_set_exception_silenced(flight_app, sample_flight):
    c, db, mod, redis = flight_app
    redis.get = MagicMock(return_value=None)
    redis.setex = MagicMock(side_effect=Exception("redis write failed"))

    flight = sample_flight()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = flight
    db.execute.return_value = result_mock

    resp = c.get(f"/api/v1/flights/{flight.id}")
    assert resp.status_code == 200


# ── Update flight – 404 ──────────────────────────────────────────

def test_update_flight_not_found(flight_app, auth_headers):
    c, db, mod, redis = flight_app
    headers = auth_headers(role="admin")

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    resp = c.put(f"/api/v1/flights/{uuid.uuid4()}", headers=headers, json={"gate": "X1"})
    assert resp.status_code == 404


# ── Update flight – status field triggers FlightStatus() ─────────

def test_update_flight_with_status_field(flight_app, auth_headers, sample_flight):
    c, db, mod, redis = flight_app
    headers = auth_headers(role="admin")

    flight = sample_flight()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = flight
    db.execute.return_value = result_mock
    db.refresh = AsyncMock(side_effect=lambda obj: None)
    mod.event_publisher = None

    resp = c.put(f"/api/v1/flights/{flight.id}", headers=headers, json={
        "status": "boarding",
    })
    assert resp.status_code == 200


# ── Create flight – event publisher ──────────────────────────────

def test_create_flight_with_event_publisher(flight_app, auth_headers, sample_flight):
    c, db, mod, redis = flight_app
    headers = auth_headers(role="admin")

    mock_pub = MagicMock()
    mod.event_publisher = mock_pub

    flight = sample_flight()

    def fake_refresh(obj):
        obj.id = flight.id
        obj.flight_number = "AL300"
        obj.airline = "AeroLink"
        obj.origin = "DUB"
        obj.destination = "JFK"
        obj.departure_date = flight.departure_date
        obj.departure_time = flight.departure_time
        obj.arrival_date = flight.arrival_date
        obj.arrival_time = flight.arrival_time
        obj.status = flight.status
        obj.aircraft_type = "B777"
        obj.available_seats_economy = 200
        obj.available_seats_business = 40
        obj.available_seats_first = 16
        obj.price_economy = 399.99
        obj.price_business = 1199.99
        obj.price_first = 2499.99
        obj.gate = None
        obj.terminal = None
        obj.created_at = flight.created_at

    db.refresh = AsyncMock(side_effect=fake_refresh)

    resp = c.post("/api/v1/flights", headers=headers, json={
        "flight_number": "AL300",
        "airline": "AeroLink",
        "origin": "DUB",
        "destination": "JFK",
        "departure_date": "2026-07-01",
        "departure_time": "09:00:00",
        "arrival_date": "2026-07-01",
        "arrival_time": "11:30:00",
    })
    assert resp.status_code == 201
    mock_pub.publish.assert_called_once()
    assert mock_pub.publish.call_args[0][1] == "FlightScheduleUpdated"


# ── Update flight – event publisher ──────────────────────────────

def test_update_flight_with_event_publisher(flight_app, auth_headers, sample_flight):
    c, db, mod, redis = flight_app
    headers = auth_headers(role="admin")

    mock_pub = MagicMock()
    mod.event_publisher = mock_pub

    flight = sample_flight()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = flight
    db.execute.return_value = result_mock
    db.refresh = AsyncMock(side_effect=lambda obj: None)

    resp = c.put(f"/api/v1/flights/{flight.id}", headers=headers, json={"gate": "Z9"})
    assert resp.status_code == 200
    mock_pub.publish.assert_called_once()
    assert mock_pub.publish.call_args[0][1] == "FlightScheduleUpdated"


# ── Update seats – 404 ──────────────────────────────────────────

def test_update_seats_not_found(flight_app):
    c, db, mod, redis = flight_app
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    resp = c.put(f"/api/v1/flights/{uuid.uuid4()}/seats", json={
        "cabin_class": "economy", "change": -1,
    })
    assert resp.status_code == 404


# ── Update seats – event publisher ───────────────────────────────

def test_update_seats_with_event_publisher(flight_app, sample_flight):
    c, db, mod, redis = flight_app

    mock_pub = MagicMock()
    mod.event_publisher = mock_pub

    flight = sample_flight(available_seats_economy=50, version=2)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = flight
    update_result = MagicMock()
    update_result.rowcount = 1
    db.execute.side_effect = [result_mock, update_result]

    resp = c.put(f"/api/v1/flights/{flight.id}/seats", json={
        "cabin_class": "economy", "change": -1,
    })
    assert resp.status_code == 200
    mock_pub.publish.assert_called_once()
    assert mock_pub.publish.call_args[0][1] == "SeatAvailabilityChanged"


# ── _invalidate_cache_for_flight – direct unit tests ─────────────

def test_invalidate_cache_deletes_matching_keys(flight_app, sample_flight):
    """Cache keys returned by redis.keys() should be deleted."""
    c, db, mod, redis = flight_app
    redis.keys = MagicMock(return_value=["flights:DUB:*", "flights:*:LHR:*"])

    flight = sample_flight(origin="DUB", destination="LHR")
    mod._invalidate_cache_for_flight(flight)

    redis.delete.assert_called()


def test_invalidate_cache_exception_silenced(flight_app, sample_flight):
    """Redis error during cache invalidation should not propagate."""
    c, db, mod, redis = flight_app
    redis.keys = MagicMock(side_effect=Exception("redis down"))

    flight = sample_flight()
    mod._invalidate_cache_for_flight(flight)  # should not raise
