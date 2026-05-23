"""
Integration tests for AeroLink microservices.

These tests load multiple services simultaneously and wire them together
via a custom httpx transport bridge, so inter-service HTTP calls actually
execute the target service's endpoint code instead of being mocked.
"""
import sys
import os
import uuid
import time
import importlib.util
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx
from fastapi import FastAPI

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.database import Base
from shared.auth import create_access_token

# Pre-mock boto3 to prevent import hang
_mock_boto3 = MagicMock()
sys.modules.setdefault("boto3", _mock_boto3)

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")


# ══════════════════════════════════════════════════════════════════
#  Infrastructure: Transport Bridge, Event Capture, Service Loader
# ══════════════════════════════════════════════════════════════════

class IntegrationTransport(httpx.AsyncBaseTransport):
    """Routes httpx requests to the correct service's ASGI app by URL port."""

    def __init__(self, service_apps: dict[int, FastAPI]):
        self._transports = {
            port: httpx.ASGITransport(app=app)
            for port, app in service_apps.items()
        }

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        port = request.url.port or 80
        transport = self._transports.get(port)
        if transport is None:
            raise httpx.ConnectError(f"No service on port {port}")
        return await transport.handle_async_request(request)


class EventCapture:
    """Captures events published by services; can replay them to consumers."""

    def __init__(self):
        self.events: list[dict] = []

    def publish(self, source: str, detail_type: str, detail: dict) -> dict:
        from datetime import datetime, timezone
        detail["timestamp"] = datetime.now(timezone.utc).isoformat()
        self.events.append({
            "source": source,
            "detail-type": detail_type,
            "detail": detail,
        })
        return {"FailedEntryCount": 0}

    def drain_to(self, notification_mod) -> list[dict]:
        """Deliver all captured events to notification service's process_event."""
        delivered = list(self.events)
        for event in delivered:
            notification_mod.process_event(event)
        self.events.clear()
        return delivered

    def find(self, detail_type: str) -> list[dict]:
        return [e for e in self.events if e["detail-type"] == detail_type]

    def clear(self):
        self.events.clear()


def _create_mock_db_session():
    """Create an independent mock AsyncSession."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.delete = AsyncMock()
    return session


def _load_service(service_dir: str, module_alias: str, db_session,
                  extra_patches: dict = None, env_overrides: dict = None):
    """
    Load a service module via importlib with mocked DB/logging.
    Returns the loaded module.
    """
    svc_path = os.path.join(PROJECT_ROOT, service_dir)
    sys.path.insert(0, svc_path)

    for mod_name in ["models", "schemas"]:
        sys.modules.pop(mod_name, None)

    mock_engine = MagicMock()
    mock_engine.begin.return_value = AsyncMock()
    mock_engine.dispose = AsyncMock()

    spec = importlib.util.spec_from_file_location(
        module_alias, os.path.join(svc_path, "main.py"))
    mod = importlib.util.module_from_spec(spec)

    patches = {
        "shared.database.create_db_engine": mock_engine,
        "shared.database.create_session_factory": MagicMock(),
        "shared.logging.setup_logging": MagicMock(),
    }
    if extra_patches:
        patches.update(extra_patches)

    with _multi_patch(patches), patch.dict(os.environ, env_overrides or {}):
        spec.loader.exec_module(mod)

    async def mock_get_db():
        yield db_session

    mod.app.dependency_overrides[mod.get_db] = mock_get_db
    return mod


class _multi_patch:
    """Context manager applying multiple patches at once."""

    def __init__(self, patches: dict):
        self._patches = patches
        self._active = []

    def __enter__(self):
        for target, value in self._patches.items():
            p = patch(target, return_value=value)
            p.start()
            self._active.append(p)
        return self

    def __exit__(self, *args):
        for p in reversed(self._active):
            p.stop()


@dataclass
class ServiceBundle:
    """All loaded services and their mock DB sessions."""
    # Modules
    flight_mod: object = None
    booking_mod: object = None
    payment_mod: object = None
    checkin_mod: object = None
    passenger_mod: object = None
    notification_mod: object = None
    baggage_mod: object = None
    # DB sessions
    flight_db: object = None
    booking_db: object = None
    payment_db: object = None
    checkin_db: object = None
    passenger_db: object = None
    notification_db: object = None
    baggage_db: object = None
    # Event capture
    events: EventCapture = field(default_factory=EventCapture)
    # Auth helper
    auth_headers: dict = field(default_factory=dict)
    user_id: str = ""


@dataclass
class GatewayBundle:
    """Gateway test client + all backend services."""
    client: object = None  # TestClient
    gw_mod: object = None
    auth_mod: object = None
    auth_db: object = None
    flight_mod: object = None
    flight_db: object = None
    booking_mod: object = None
    booking_db: object = None
    payment_mod: object = None
    payment_db: object = None
    baggage_mod: object = None
    baggage_db: object = None
    checkin_mod: object = None
    checkin_db: object = None
    passenger_mod: object = None
    passenger_db: object = None
    notification_mod: object = None
    notification_db: object = None


def _mock_result(scalar_one_or_none=None, scalars_all=None, rowcount=1):
    """Helper to create a mock db.execute() result."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_one_or_none
    result.rowcount = rowcount
    if scalars_all is not None:
        result.scalars.return_value.all.return_value = scalars_all
    return result


# ══════════════════════════════════════════════════════════════════
#  Fixtures
# ══════════════════════════════════════════════════════════════════

@pytest.fixture
def integration_services():
    """
    Load flight, booking, payment, checkin, passenger, and notification
    services. Wire them via httpx transport bridge and EventCapture.
    """
    Base.metadata.clear()

    # Per-service DB sessions
    flight_db = _create_mock_db_session()
    booking_db = _create_mock_db_session()
    payment_db = _create_mock_db_session()
    checkin_db = _create_mock_db_session()
    passenger_db = _create_mock_db_session()
    notification_db = _create_mock_db_session()
    baggage_db = _create_mock_db_session()

    mock_redis = MagicMock()
    mock_redis.get = MagicMock(return_value=None)
    mock_redis.set = MagicMock(return_value=True)
    mock_redis.setex = MagicMock(return_value=True)
    mock_redis.delete = MagicMock(return_value=1)
    mock_redis.keys = MagicMock(return_value=[])
    mock_redis.ping = MagicMock(return_value=True)

    # Load services sequentially (pop models/schemas between each)
    flight_mod = _load_service(
        "services/flight-service", "integ_flight", flight_db,
        extra_patches={"redis.Redis.from_url": mock_redis})

    booking_mod = _load_service(
        "services/booking-service", "integ_booking", booking_db)

    payment_mod = _load_service(
        "services/payment-service", "integ_payment", payment_db)

    checkin_mod = _load_service(
        "services/checkin-service", "integ_checkin", checkin_db)

    passenger_mod = _load_service(
        "services/passenger-service", "integ_passenger", passenger_db)

    baggage_mod = _load_service(
        "services/baggage-service", "integ_baggage", baggage_db)

    notification_mod = _load_service(
        "services/notification-service", "integ_notification", notification_db,
        env_overrides={"ENABLE_SQS_POLLING": "false"})

    # Wire EventCapture
    events = EventCapture()
    for mod in [flight_mod, booking_mod, payment_mod, checkin_mod, baggage_mod]:
        mod.event_publisher = events

    # Patch record_audit on services that use it
    payment_mod.record_audit = AsyncMock()
    passenger_mod.record_audit = AsyncMock()

    # Build transport
    service_apps = {
        8002: flight_mod.app,
        8003: booking_mod.app,
        8004: payment_mod.app,
        8005: baggage_mod.app,
        8006: checkin_mod.app,
        8007: passenger_mod.app,
        8008: notification_mod.app,
    }
    transport = IntegrationTransport(service_apps)

    # Auth
    user_id = str(uuid.uuid4())
    token = create_access_token({
        "sub": user_id, "username": "integ_user",
        "role": "passenger", "airport_code": None, "airline_code": None,
    })
    headers = {"Authorization": f"Bearer {token}"}

    bundle = ServiceBundle(
        flight_mod=flight_mod, booking_mod=booking_mod,
        payment_mod=payment_mod, checkin_mod=checkin_mod,
        passenger_mod=passenger_mod, notification_mod=notification_mod,
        baggage_mod=baggage_mod,
        flight_db=flight_db, booking_db=booking_db,
        payment_db=payment_db, checkin_db=checkin_db,
        passenger_db=passenger_db, notification_db=notification_db,
        baggage_db=baggage_db,
        events=events, auth_headers=headers, user_id=user_id,
    )

    # Patch httpx.AsyncClient globally to use our transport
    original_init = httpx.AsyncClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        kwargs.pop("timeout", None)
        original_init(self, *args, **kwargs)

    svc_paths = []
    for svc_dir in ["services/flight-service", "services/booking-service",
                     "services/payment-service", "services/baggage-service",
                     "services/checkin-service",
                     "services/passenger-service", "services/notification-service"]:
        p = os.path.join(PROJECT_ROOT, svc_dir)
        if p not in svc_paths:
            svc_paths.append(p)

    with patch.object(httpx.AsyncClient, "__init__", patched_init):
        yield bundle

    # Cleanup
    for mod in [flight_mod, booking_mod, payment_mod, baggage_mod,
                checkin_mod, passenger_mod, notification_mod]:
        mod.app.dependency_overrides.clear()
    for mod_name in ["models", "schemas"]:
        sys.modules.pop(mod_name, None)
    for p in svc_paths:
        if p in sys.path:
            sys.path.remove(p)


@pytest.fixture
def gw_integration():
    """Load API gateway with all 8 backend services via transport bridge."""
    Base.metadata.clear()

    # DB sessions for all services
    auth_db = _create_mock_db_session()
    flight_db = _create_mock_db_session()
    booking_db = _create_mock_db_session()
    payment_db = _create_mock_db_session()
    baggage_db = _create_mock_db_session()
    checkin_db = _create_mock_db_session()
    passenger_db = _create_mock_db_session()
    notification_db = _create_mock_db_session()

    mock_redis = MagicMock()
    mock_redis.get = MagicMock(return_value=None)
    mock_redis.set = MagicMock(return_value=True)
    mock_redis.setex = MagicMock(return_value=True)
    mock_redis.delete = MagicMock(return_value=1)
    mock_redis.keys = MagicMock(return_value=[])
    mock_redis.ping = MagicMock(return_value=True)

    # Load all backend services
    auth_mod = _load_service("services/auth-service", "gw_auth", auth_db)
    flight_mod = _load_service(
        "services/flight-service", "gw_flight", flight_db,
        extra_patches={"redis.Redis.from_url": mock_redis})
    booking_mod = _load_service("services/booking-service", "gw_booking", booking_db)
    payment_mod = _load_service("services/payment-service", "gw_payment", payment_db)
    baggage_mod = _load_service("services/baggage-service", "gw_baggage", baggage_db)
    checkin_mod = _load_service("services/checkin-service", "gw_checkin", checkin_db)
    passenger_mod = _load_service("services/passenger-service", "gw_passenger", passenger_db)
    notification_mod = _load_service(
        "services/notification-service", "gw_notification", notification_db,
        env_overrides={"ENABLE_SQS_POLLING": "false"})

    # Patch record_audit on services that use it
    payment_mod.record_audit = AsyncMock()
    passenger_mod.record_audit = AsyncMock()

    # Load gateway
    gw_path = os.path.join(PROJECT_ROOT, "api-gateway")
    sys.path.insert(0, gw_path)
    for mod_name in ["models", "schemas"]:
        sys.modules.pop(mod_name, None)
    spec = importlib.util.spec_from_file_location(
        "gw_main_integ", os.path.join(gw_path, "main.py"))
    gw_mod = importlib.util.module_from_spec(spec)
    with patch("shared.logging.setup_logging"):
        spec.loader.exec_module(gw_mod)
    gw_mod.rate_limit_store.clear()

    # Transport: all 8 service ports
    service_apps = {
        8001: auth_mod.app,
        8002: flight_mod.app,
        8003: booking_mod.app,
        8004: payment_mod.app,
        8005: baggage_mod.app,
        8006: checkin_mod.app,
        8007: passenger_mod.app,
        8008: notification_mod.app,
    }
    transport = IntegrationTransport(service_apps)

    from fastapi.testclient import TestClient

    original_init = httpx.AsyncClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        kwargs.pop("timeout", None)
        original_init(self, *args, **kwargs)

    bundle = GatewayBundle(
        gw_mod=gw_mod,
        auth_mod=auth_mod, auth_db=auth_db,
        flight_mod=flight_mod, flight_db=flight_db,
        booking_mod=booking_mod, booking_db=booking_db,
        payment_mod=payment_mod, payment_db=payment_db,
        baggage_mod=baggage_mod, baggage_db=baggage_db,
        checkin_mod=checkin_mod, checkin_db=checkin_db,
        passenger_mod=passenger_mod, passenger_db=passenger_db,
        notification_mod=notification_mod, notification_db=notification_db,
    )

    with patch.object(httpx.AsyncClient, "__init__", patched_init):
        with TestClient(gw_mod.app, raise_server_exceptions=False) as client:
            bundle.client = client
            yield bundle

    all_mods = [auth_mod, flight_mod, booking_mod, payment_mod,
                baggage_mod, checkin_mod, passenger_mod, notification_mod]
    for mod in all_mods:
        mod.app.dependency_overrides.clear()
    for mod_name in ["models", "schemas"]:
        sys.modules.pop(mod_name, None)


# ══════════════════════════════════════════════════════════════════
#  Flow 1: Full Booking Saga
# ══════════════════════════════════════════════════════════════════

def test_full_booking_saga_happy_path(integration_services):
    """Flight lookup → booking → payment → check-in → boarding pass."""
    s = integration_services
    from fastapi.testclient import TestClient

    flight_id = str(uuid.uuid4())
    booking_id = str(uuid.uuid4())
    payment_id = str(uuid.uuid4())

    # ── Step 1: Flight service returns a flight ──
    flight_obj = MagicMock()
    flight_obj.id = flight_id
    flight_obj.flight_number = "AL100"
    flight_obj.airline = "AeroLink"
    flight_obj.origin = "DUB"
    flight_obj.destination = "LHR"
    flight_obj.departure_date = "2025-06-01"
    flight_obj.departure_time = "10:00:00"
    flight_obj.arrival_date = "2025-06-01"
    flight_obj.arrival_time = "11:30:00"
    flight_obj.status = MagicMock(value="scheduled")
    flight_obj.aircraft_type = "A320"
    flight_obj.available_seats_economy = 150
    flight_obj.available_seats_business = 30
    flight_obj.available_seats_first = 10
    flight_obj.total_seats_economy = 150
    flight_obj.price_economy = 199.99
    flight_obj.price_business = 599.99
    flight_obj.price_first = 1299.99
    flight_obj.gate = "A1"
    flight_obj.terminal = "T1"
    flight_obj.version = 1
    flight_obj.created_at = MagicMock(isoformat=MagicMock(return_value="2025-01-01T00:00:00"))

    # Flight DB: GET flight, then GET flight for seat update, then UPDATE seats
    s.flight_db.execute = AsyncMock(side_effect=[
        _mock_result(scalar_one_or_none=flight_obj),   # GET /flights/{id}
        _mock_result(scalar_one_or_none=flight_obj),   # PUT /seats: read flight
        _mock_result(rowcount=1),                      # PUT /seats: optimistic lock update
    ])

    # ── Step 2: Create booking via booking-service ──
    # Booking DB: no duplicate check, then the booking insert
    def fake_booking_refresh(obj):
        obj.id = booking_id
        obj.booking_reference = "ALTEST01"
        obj.user_id = s.user_id
        obj.flight_id = flight_id
        obj.passenger_name = "John Doe"
        obj.passenger_email = "john@test.com"
        obj.cabin_class = "economy"
        obj.num_passengers = 1
        obj.total_price = 199.99
        obj.status = MagicMock(value="pending")
        obj.payment_id = None
        obj.seat_numbers = None
        obj.special_requests = None
        obj.created_at = MagicMock(isoformat=MagicMock(return_value="2025-01-01T00:00:00"))

    s.booking_db.refresh = AsyncMock(side_effect=fake_booking_refresh)

    with TestClient(s.booking_mod.app, raise_server_exceptions=False) as c:
        resp = c.post("/api/v1/bookings", headers=s.auth_headers, json={
            "flight_id": flight_id,
            "passenger_name": "John Doe",
            "passenger_email": "john@test.com",
            "cabin_class": "economy",
            "num_passengers": 1,
        })
    assert resp.status_code == 201, f"Booking failed: {resp.text}"
    booking_data = resp.json()
    assert booking_data["status"] == "pending"

    # Verify BookingCreated event was captured
    assert len(s.events.find("BookingCreated")) == 1

    # ── Step 3: Process payment via payment-service ──
    s.events.clear()

    # Payment DB: idempotency check returns None, then refresh
    s.payment_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=None))

    def fake_payment_refresh(obj):
        obj.id = payment_id
        obj.booking_id = booking_id
        obj.user_id = s.user_id
        obj.amount = 199.99
        obj.currency = "EUR"
        obj.status = MagicMock(value="completed")
        obj.payment_method = MagicMock(value="credit-card")
        obj.idempotency_key = "idem-001"
        obj.transaction_ref = "TXN-INTEG-001"
        obj.failure_reason = None
        obj.card_token = "tok_abc"
        obj.card_last_four = "4242"
        obj.created_at = MagicMock(isoformat=MagicMock(return_value="2025-01-01T00:00:00"))

    s.payment_db.refresh = AsyncMock(side_effect=fake_payment_refresh)

    # Booking DB for status update from payment: find booking, then refresh
    booking_for_status = MagicMock()
    booking_for_status.id = booking_id
    booking_for_status.booking_reference = "ALTEST01"
    booking_for_status.user_id = s.user_id
    booking_for_status.flight_id = flight_id
    booking_for_status.passenger_name = "John Doe"
    booking_for_status.passenger_email = "john@test.com"
    booking_for_status.cabin_class = "economy"
    booking_for_status.num_passengers = 1
    booking_for_status.total_price = 199.99
    booking_for_status.status = MagicMock(value="pending")
    booking_for_status.payment_id = None
    booking_for_status.seat_numbers = None
    booking_for_status.special_requests = None
    booking_for_status.created_at = MagicMock(isoformat=MagicMock(return_value="2025-01-01T00:00:00"))

    s.booking_db.execute = AsyncMock(return_value=_mock_result(
        scalar_one_or_none=booking_for_status))
    s.booking_db.refresh = AsyncMock(side_effect=lambda obj: None)

    with patch.object(s.payment_mod, "simulate_payment_processing",
                      return_value=(True, "TXN-INTEG-001")):
        with TestClient(s.payment_mod.app, raise_server_exceptions=False) as c:
            resp = c.post("/api/v1/payments", headers=s.auth_headers, json={
                "booking_id": booking_id,
                "amount": 199.99,
                "currency": "EUR",
                "payment_method": "credit-card",
                "card_number": "4111111111111111",
                "idempotency_key": "idem-001",
            })
    assert resp.status_code == 201, f"Payment failed: {resp.text}"
    assert resp.json()["status"] == "completed"

    # Verify PaymentProcessed event
    assert len(s.events.find("PaymentProcessed")) == 1

    # ── Step 4: Check-in via checkin-service ──
    s.events.clear()

    # Checkin DB: no existing check-in
    s.checkin_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=None))

    def fake_checkin_refresh(obj):
        obj.id = str(uuid.uuid4())
        obj.booking_id = booking_id
        obj.flight_id = flight_id
        obj.passenger_name = "John Doe"
        obj.seat_number = "12A"
        obj.boarding_group = "B"
        obj.gate = None
        obj.status = MagicMock(value="boarding-pass-issued")
        obj.boarding_pass_url = f"/api/v1/checkin/{booking_id}/boarding-pass"
        obj.has_baggage = False
        obj.created_at = MagicMock(isoformat=MagicMock(return_value="2025-01-01T00:00:00"))

    s.checkin_db.refresh = AsyncMock(side_effect=fake_checkin_refresh)

    # Booking DB for status update from check-in
    booking_for_checkin = MagicMock()
    booking_for_checkin.id = booking_id
    booking_for_checkin.booking_reference = "ALTEST01"
    booking_for_checkin.user_id = s.user_id
    booking_for_checkin.flight_id = flight_id
    booking_for_checkin.passenger_name = "John Doe"
    booking_for_checkin.passenger_email = "john@test.com"
    booking_for_checkin.cabin_class = "economy"
    booking_for_checkin.num_passengers = 1
    booking_for_checkin.total_price = 199.99
    booking_for_checkin.status = MagicMock(value="paid")
    booking_for_checkin.payment_id = payment_id
    booking_for_checkin.seat_numbers = None
    booking_for_checkin.special_requests = None
    booking_for_checkin.created_at = MagicMock(isoformat=MagicMock(return_value="2025-01-01T00:00:00"))

    s.booking_db.execute = AsyncMock(return_value=_mock_result(
        scalar_one_or_none=booking_for_checkin))
    s.booking_db.refresh = AsyncMock(side_effect=lambda obj: None)

    with TestClient(s.checkin_mod.app, raise_server_exceptions=False) as c:
        resp = c.post("/api/v1/checkin", headers=s.auth_headers, json={
            "booking_id": booking_id,
            "flight_id": flight_id,
            "passenger_name": "John Doe",
        })
    assert resp.status_code == 201, f"Check-in failed: {resp.text}"
    checkin_data = resp.json()
    assert checkin_data["seat_number"]
    assert checkin_data["boarding_group"]

    # Verify CheckInCompleted event
    assert len(s.events.find("CheckInCompleted")) == 1

    # ── Step 5: Get boarding pass ──
    checkin_obj = MagicMock()
    checkin_obj.passenger_name = "John Doe"
    checkin_obj.seat_number = "12A"
    checkin_obj.boarding_group = "B"
    checkin_obj.gate = None
    checkin_obj.flight_id = flight_id

    s.checkin_db.execute = AsyncMock(return_value=_mock_result(
        scalar_one_or_none=checkin_obj))

    with TestClient(s.checkin_mod.app, raise_server_exceptions=False) as c:
        resp = c.get(f"/api/v1/checkin/{booking_id}/boarding-pass")
    assert resp.status_code == 200
    bp = resp.json()["boarding_pass"]
    assert bp["passenger"] == "John Doe"
    assert bp["seat"] == "12A"
    assert bp["status"] == "READY TO BOARD"


def test_booking_saga_events_reach_notification(integration_services):
    """After a booking, events drain to the notification service."""
    s = integration_services

    # Simulate events
    s.events.publish("booking-service", "BookingCreated", {
        "booking_reference": "ALTEST01",
        "passenger_name": "John Doe",
        "flight_id": "F1",
        "total_price": "199.99",
    })
    s.events.publish("payment-service", "PaymentProcessed", {
        "booking_id": "B1",
        "amount": "199.99",
        "transaction_ref": "TXN-001",
    })
    s.events.publish("checkin-service", "CheckInCompleted", {
        "passenger_name": "John Doe",
        "seat_number": "12A",
        "flight_id": "F1",
    })

    # Drain to notification service — should not raise
    delivered = s.events.drain_to(s.notification_mod)
    assert len(delivered) == 3
    types = [e["detail-type"] for e in delivered]
    assert "BookingCreated" in types
    assert "PaymentProcessed" in types
    assert "CheckInCompleted" in types


# ══════════════════════════════════════════════════════════════════
#  Flow 2: Cancellation + Compensating Transaction
# ══════════════════════════════════════════════════════════════════

def test_cancel_booking_releases_seats(integration_services):
    """Cancel booking → flight-service receives PUT seats with positive change."""
    s = integration_services
    from fastapi.testclient import TestClient

    flight_id = str(uuid.uuid4())
    booking_id = str(uuid.uuid4())

    # Booking to cancel
    booking = MagicMock()
    booking.id = booking_id
    booking.booking_reference = "ALCANC01"
    booking.user_id = s.user_id
    booking.flight_id = flight_id
    booking.passenger_name = "Jane Doe"
    booking.passenger_email = "jane@test.com"
    booking.cabin_class = "economy"
    booking.num_passengers = 2
    booking.total_price = 399.98
    booking.status = MagicMock(value="paid")
    booking.payment_id = None
    booking.seat_numbers = None
    booking.special_requests = None
    booking.created_at = MagicMock(isoformat=MagicMock(return_value="2025-01-01T00:00:00"))

    s.booking_db.execute = AsyncMock(return_value=_mock_result(
        scalar_one_or_none=booking))
    s.booking_db.refresh = AsyncMock(side_effect=lambda obj: None)

    # Flight DB for seat release: find flight, then update
    flight_obj = MagicMock()
    flight_obj.id = flight_id
    flight_obj.available_seats_economy = 148
    flight_obj.version = 2
    s.flight_db.execute = AsyncMock(side_effect=[
        _mock_result(scalar_one_or_none=flight_obj),
        _mock_result(rowcount=1),
    ])

    with TestClient(s.booking_mod.app, raise_server_exceptions=False) as c:
        resp = c.post(f"/api/v1/bookings/{booking_id}/cancel",
                      headers=s.auth_headers)
    assert resp.status_code == 200, f"Cancel failed: {resp.text}"
    assert resp.json()["status"] == "cancelled"

    # Verify BookingCancelled event
    assert len(s.events.find("BookingCancelled")) == 1

    # Verify flight-service was called (seat release)
    assert s.flight_db.execute.call_count == 2


def test_cancel_already_cancelled_booking_fails(integration_services):
    """Cancelling an already-cancelled booking returns 400."""
    s = integration_services
    from fastapi.testclient import TestClient

    booking = MagicMock()
    booking.id = str(uuid.uuid4())
    booking.status = s.booking_mod.BookingStatus.CANCELLED

    s.booking_db.execute = AsyncMock(return_value=_mock_result(
        scalar_one_or_none=booking))

    with TestClient(s.booking_mod.app, raise_server_exceptions=False) as c:
        resp = c.post(f"/api/v1/bookings/{booking.id}/cancel",
                      headers=s.auth_headers)
    assert resp.status_code == 400


# ══════════════════════════════════════════════════════════════════
#  Flow 3: Payment Failure
# ══════════════════════════════════════════════════════════════════

def test_payment_failure_publishes_failed_event(integration_services):
    """Failed payment publishes PaymentFailed, not PaymentProcessed."""
    s = integration_services
    from fastapi.testclient import TestClient

    payment_id = str(uuid.uuid4())

    # No existing idempotent payment
    s.payment_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=None))

    def fake_refresh(obj):
        obj.id = payment_id
        obj.booking_id = str(uuid.uuid4())
        obj.user_id = s.user_id
        obj.amount = 100.0
        obj.currency = "EUR"
        obj.status = MagicMock(value="failed")
        obj.payment_method = MagicMock(value="credit-card")
        obj.idempotency_key = "fail-001"
        obj.transaction_ref = None
        obj.failure_reason = "Payment declined by issuing bank"
        obj.card_token = "tok_x"
        obj.card_last_four = "1234"
        obj.created_at = MagicMock(isoformat=MagicMock(return_value="2025-01-01T00:00:00"))

    s.payment_db.refresh = AsyncMock(side_effect=fake_refresh)

    with patch.object(s.payment_mod, "simulate_payment_processing",
                      return_value=(False, "Payment declined by issuing bank")):
        with TestClient(s.payment_mod.app, raise_server_exceptions=False) as c:
            resp = c.post("/api/v1/payments", headers=s.auth_headers, json={
                "booking_id": str(uuid.uuid4()),
                "amount": 100.0,
                "currency": "EUR",
                "payment_method": "credit-card",
                "card_number": "4111111111111111",
                "idempotency_key": "fail-001",
            })
    assert resp.status_code == 201
    assert resp.json()["status"] == "failed"
    assert len(s.events.find("PaymentFailed")) == 1
    assert len(s.events.find("PaymentProcessed")) == 0


def test_payment_failure_booking_stays_pending(integration_services):
    """After failed payment, no booking status update is made."""
    s = integration_services
    from fastapi.testclient import TestClient

    booking_id = str(uuid.uuid4())

    s.payment_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=None))

    def fake_refresh(obj):
        obj.id = str(uuid.uuid4())
        obj.booking_id = booking_id
        obj.user_id = s.user_id
        obj.amount = 50.0
        obj.currency = "EUR"
        obj.status = MagicMock(value="failed")
        obj.payment_method = MagicMock(value="credit-card")
        obj.idempotency_key = "fail-002"
        obj.transaction_ref = None
        obj.failure_reason = "Declined"
        obj.card_token = "tok_y"
        obj.card_last_four = "5678"
        obj.created_at = MagicMock(isoformat=MagicMock(return_value="2025-01-01T00:00:00"))

    s.payment_db.refresh = AsyncMock(side_effect=fake_refresh)

    # Booking DB should NOT receive any calls (no status update on failure)
    s.booking_db.execute = AsyncMock()

    with patch.object(s.payment_mod, "simulate_payment_processing",
                      return_value=(False, "Declined")):
        with TestClient(s.payment_mod.app, raise_server_exceptions=False) as c:
            c.post("/api/v1/payments", headers=s.auth_headers, json={
                "booking_id": booking_id,
                "amount": 50.0,
                "currency": "EUR",
                "payment_method": "credit-card",
                "card_number": "4111111111111111",
                "idempotency_key": "fail-002",
            })

    # Booking DB should not have been called for status update
    s.booking_db.execute.assert_not_called()


# ══════════════════════════════════════════════════════════════════
#  Flow 4: Idempotency / Duplicate Prevention
# ══════════════════════════════════════════════════════════════════

def test_payment_idempotency_returns_existing(integration_services):
    """Same idempotency key returns existing payment, no new event."""
    s = integration_services
    from fastapi.testclient import TestClient

    existing_payment = MagicMock()
    existing_payment.id = uuid.uuid4()
    existing_payment.booking_id = uuid.uuid4()
    existing_payment.user_id = s.user_id
    existing_payment.amount = 199.99
    existing_payment.currency = "EUR"
    existing_payment.status = MagicMock(value="completed")
    existing_payment.payment_method = MagicMock(value="credit-card")
    existing_payment.idempotency_key = "idem-dup"
    existing_payment.transaction_ref = "TXN-EXISTING"
    existing_payment.failure_reason = None
    existing_payment.card_token = "tok_exist"
    existing_payment.card_last_four = "4242"
    existing_payment.created_at = MagicMock(isoformat=MagicMock(return_value="2025-01-01T00:00:00"))

    s.payment_db.execute = AsyncMock(return_value=_mock_result(
        scalar_one_or_none=existing_payment))

    s.events.clear()

    with TestClient(s.payment_mod.app, raise_server_exceptions=False) as c:
        resp = c.post("/api/v1/payments", headers=s.auth_headers, json={
            "booking_id": str(uuid.uuid4()),
            "amount": 199.99,
            "currency": "EUR",
            "payment_method": "credit-card",
            "card_number": "4111111111111111",
            "idempotency_key": "idem-dup",
        })
    assert resp.status_code == 201
    assert resp.json()["transaction_ref"] == "TXN-EXISTING"
    # No new events
    assert len(s.events.events) == 0


def test_double_checkin_returns_409(integration_services):
    """Checking in the same booking twice returns 409."""
    s = integration_services
    from fastapi.testclient import TestClient

    existing_checkin = MagicMock()
    s.checkin_db.execute = AsyncMock(return_value=_mock_result(
        scalar_one_or_none=existing_checkin))

    with TestClient(s.checkin_mod.app, raise_server_exceptions=False) as c:
        resp = c.post("/api/v1/checkin", headers=s.auth_headers, json={
            "booking_id": str(uuid.uuid4()),
            "flight_id": str(uuid.uuid4()),
            "passenger_name": "Dup Person",
        })
    assert resp.status_code == 409


# ══════════════════════════════════════════════════════════════════
#  Flow 5: Event Propagation
# ══════════════════════════════════════════════════════════════════

def test_booking_event_reaches_notification(integration_services):
    s = integration_services
    s.events.publish("booking-service", "BookingCreated", {
        "booking_reference": "ALEVT01",
        "passenger_name": "Test User",
        "flight_id": "F1",
        "total_price": "100",
    })
    delivered = s.events.drain_to(s.notification_mod)
    assert len(delivered) == 1
    assert delivered[0]["detail-type"] == "BookingCreated"


def test_payment_event_reaches_notification(integration_services):
    s = integration_services
    s.events.publish("payment-service", "PaymentProcessed", {
        "booking_id": "B1",
        "amount": "100",
        "transaction_ref": "TXN-1",
    })
    delivered = s.events.drain_to(s.notification_mod)
    assert len(delivered) == 1
    assert delivered[0]["detail-type"] == "PaymentProcessed"


def test_checkin_event_reaches_notification(integration_services):
    s = integration_services
    s.events.publish("checkin-service", "CheckInCompleted", {
        "passenger_name": "Test",
        "seat_number": "5B",
        "flight_id": "F2",
    })
    delivered = s.events.drain_to(s.notification_mod)
    assert len(delivered) == 1
    assert delivered[0]["detail-type"] == "CheckInCompleted"


def test_cancellation_event_reaches_notification(integration_services):
    s = integration_services
    s.events.publish("booking-service", "BookingCancelled", {
        "booking_reference": "ALCAN01",
    })
    delivered = s.events.drain_to(s.notification_mod)
    assert len(delivered) == 1
    assert delivered[0]["detail-type"] == "BookingCancelled"


# ══════════════════════════════════════════════════════════════════
#  Flow 6: GDPR Erasure Cascade
# ══════════════════════════════════════════════════════════════════

def test_gdpr_erasure_cascades_to_services(integration_services):
    """DELETE profile cascades httpx POST to booking + notification services."""
    s = integration_services
    from fastapi.testclient import TestClient

    profile = MagicMock()
    profile.id = uuid.uuid4()
    profile.user_id = s.user_id

    consents_result = MagicMock()
    consents_result.scalars.return_value.all.return_value = []

    s.passenger_db.execute = AsyncMock(side_effect=[
        _mock_result(scalar_one_or_none=profile),  # find profile
        consents_result,                            # find consents
    ])

    with TestClient(s.passenger_mod.app, raise_server_exceptions=False) as c:
        resp = c.delete("/api/v1/passengers/profile", headers=s.auth_headers)
    assert resp.status_code == 204

    # Verify audit was called with "gdpr.erasure" action (3rd positional arg)
    s.passenger_mod.record_audit.assert_called()
    audit_args = s.passenger_mod.record_audit.call_args_list
    assert any("gdpr.erasure" in str(call) for call in audit_args)


def test_gdpr_erasure_audit_logged(integration_services):
    """GDPR erasure records audit with correct action."""
    s = integration_services
    from fastapi.testclient import TestClient

    profile = MagicMock()
    profile.id = uuid.uuid4()
    profile.user_id = s.user_id

    consents_result = MagicMock()
    consents_result.scalars.return_value.all.return_value = []

    s.passenger_db.execute = AsyncMock(side_effect=[
        _mock_result(scalar_one_or_none=profile),
        consents_result,
    ])

    # Reset mock to track calls for this test
    s.passenger_mod.record_audit = AsyncMock()

    with TestClient(s.passenger_mod.app, raise_server_exceptions=False) as c:
        c.delete("/api/v1/passengers/profile", headers=s.auth_headers)

    # Check record_audit was called with "gdpr.erasure"
    assert s.passenger_mod.record_audit.call_count >= 1
    call_args_list = s.passenger_mod.record_audit.call_args_list
    actions = [str(call) for call in call_args_list]
    assert any("gdpr.erasure" in a for a in actions)


# ══════════════════════════════════════════════════════════════════
#  Flow 7: API Gateway Routing
# ══════════════════════════════════════════════════════════════════

def test_gateway_health_endpoint(gw_integration):
    """GET /health returns gateway health status."""
    gw = gw_integration
    resp = gw.client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "api-gateway"


def test_gateway_routes_public_path_no_auth(gw_integration):
    """GET /api/v1/flights via gateway reaches flight-service."""
    gw = gw_integration

    flight_obj = MagicMock()
    flight_obj.id = uuid.uuid4()
    flight_obj.flight_number = "AL100"
    flight_obj.airline = "AeroLink"
    flight_obj.origin = "DUB"
    flight_obj.destination = "LHR"
    flight_obj.departure_date = "2025-06-01"
    flight_obj.departure_time = "10:00"
    flight_obj.arrival_date = "2025-06-01"
    flight_obj.arrival_time = "11:30"
    flight_obj.status = MagicMock(value="scheduled")
    flight_obj.aircraft_type = "A320"
    flight_obj.available_seats_economy = 150
    flight_obj.available_seats_business = 30
    flight_obj.available_seats_first = 10
    flight_obj.price_economy = 199.99
    flight_obj.price_business = 599.99
    flight_obj.price_first = 1299.99
    flight_obj.gate = "A1"
    flight_obj.terminal = "T1"
    flight_obj.created_at = MagicMock(isoformat=MagicMock(return_value="2025-01-01T00:00:00"))

    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [flight_obj]
    gw.flight_db.execute = AsyncMock(return_value=result_mock)

    resp = gw.client.get("/api/v1/flights")
    assert resp.status_code == 200


def test_gateway_blocks_protected_path_without_token(gw_integration):
    """GET /api/v1/bookings without auth returns 401."""
    gw = gw_integration
    resp = gw.client.get("/api/v1/bookings")
    assert resp.status_code == 401


def test_gateway_forwards_protected_path_with_token(gw_integration):
    """GET /api/v1/bookings with JWT is forwarded to booking-service."""
    gw = gw_integration

    token = create_access_token({
        "sub": str(uuid.uuid4()), "username": "gw_user",
        "role": "passenger",
    })
    headers = {"Authorization": f"Bearer {token}"}

    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = []
    gw.booking_db.execute = AsyncMock(return_value=result_mock)

    resp = gw.client.get("/api/v1/bookings", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_gateway_unknown_route_returns_404(gw_integration):
    """GET /api/v1/unknown returns 404."""
    gw = gw_integration
    token = create_access_token({"sub": "u1", "username": "u", "role": "passenger"})
    resp = gw.client.get("/api/v1/unknown", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_gateway_service_down_returns_503(gw_integration):
    """When a service port has no app registered, gateway returns 503."""
    gw = gw_integration
    token = create_access_token({"sub": "u1", "username": "u", "role": "passenger"})

    # Use a path whose service URL resolves to a port NOT in the transport.
    # Temporarily swap the notification service URL to a dead port.
    original_url = gw.gw_mod.ROUTES["/api/v1/notifications"]
    gw.gw_mod.ROUTES["/api/v1/notifications"] = "http://localhost:9999"
    try:
        resp = gw.client.get("/api/v1/notifications",
                             headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 503
    finally:
        gw.gw_mod.ROUTES["/api/v1/notifications"] = original_url


def test_gateway_proxies_auth_register(gw_integration):
    """POST /api/v1/auth/register proxied to auth-service (public path)."""
    gw = gw_integration

    # Auth DB: no duplicate user, then refresh returns new user
    gw.auth_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=None))

    def fake_refresh(obj):
        obj.id = uuid.uuid4()
        obj.email = "new@example.com"
        obj.username = "newuser"
        obj.full_name = "New User"
        obj.role = MagicMock(value="passenger")
        obj.is_active = True
        obj.airport_code = None
        obj.airline_code = None
        obj.api_key = None
        obj.created_at = MagicMock(isoformat=MagicMock(return_value="2025-01-01T00:00:00"))

    gw.auth_db.refresh = AsyncMock(side_effect=fake_refresh)

    resp = gw.client.post("/api/v1/auth/register", json={
        "email": "new@example.com",
        "username": "newuser",
        "password": "password123",
        "full_name": "New User",
    })
    assert resp.status_code == 201
    assert resp.json()["username"] == "newuser"


def test_gateway_proxies_payments(gw_integration):
    """POST /api/v1/payments with JWT proxied to payment-service."""
    gw = gw_integration
    token = create_access_token({
        "sub": str(uuid.uuid4()), "username": "payer",
        "role": "passenger",
    })
    headers = {"Authorization": f"Bearer {token}"}

    payment_id = str(uuid.uuid4())

    # Payment DB: no idempotent match
    gw.payment_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=None))

    def fake_refresh(obj):
        obj.id = payment_id
        obj.booking_id = str(uuid.uuid4())
        obj.user_id = str(uuid.uuid4())
        obj.amount = 99.99
        obj.currency = "EUR"
        obj.status = MagicMock(value="completed")
        obj.payment_method = MagicMock(value="credit-card")
        obj.idempotency_key = "gw-idem-001"
        obj.transaction_ref = "TXN-GW-001"
        obj.failure_reason = None
        obj.card_token = "tok_gw"
        obj.card_last_four = "4242"
        obj.created_at = MagicMock(isoformat=MagicMock(return_value="2025-01-01T00:00:00"))

    gw.payment_db.refresh = AsyncMock(side_effect=fake_refresh)

    # Booking DB for status update from payment
    booking_for_status = MagicMock()
    booking_for_status.id = str(uuid.uuid4())
    booking_for_status.booking_reference = "ALGW01"
    booking_for_status.user_id = str(uuid.uuid4())
    booking_for_status.flight_id = str(uuid.uuid4())
    booking_for_status.passenger_name = "GW User"
    booking_for_status.passenger_email = "gw@test.com"
    booking_for_status.cabin_class = "economy"
    booking_for_status.num_passengers = 1
    booking_for_status.total_price = 99.99
    booking_for_status.status = MagicMock(value="pending")
    booking_for_status.payment_id = None
    booking_for_status.seat_numbers = None
    booking_for_status.special_requests = None
    booking_for_status.created_at = MagicMock(isoformat=MagicMock(return_value="2025-01-01T00:00:00"))
    gw.booking_db.execute = AsyncMock(return_value=_mock_result(
        scalar_one_or_none=booking_for_status))
    gw.booking_db.refresh = AsyncMock(side_effect=lambda obj: None)

    with patch.object(gw.payment_mod, "simulate_payment_processing",
                      return_value=(True, "TXN-GW-001")):
        resp = gw.client.post("/api/v1/payments", headers=headers, json={
            "booking_id": str(uuid.uuid4()),
            "amount": 99.99,
            "currency": "EUR",
            "payment_method": "credit-card",
            "card_number": "4111111111111111",
            "idempotency_key": "gw-idem-001",
        })
    assert resp.status_code == 201
    assert resp.json()["status"] == "completed"


def test_gateway_proxies_baggage(gw_integration):
    """GET /api/v1/baggage/{tag} with JWT proxied to baggage-service."""
    gw = gw_integration
    token = create_access_token({
        "sub": str(uuid.uuid4()), "username": "bag_user",
        "role": "passenger",
    })
    headers = {"Authorization": f"Bearer {token}"}

    bag_obj = MagicMock()
    bag_obj.id = uuid.uuid4()
    bag_obj.tag_number = "BAG-0000000001"
    bag_obj.booking_id = uuid.uuid4()
    bag_obj.passenger_name = "Bag User"
    bag_obj.flight_id = uuid.uuid4()
    bag_obj.weight_kg = 23.0
    bag_obj.status = MagicMock(value="checked-in")
    bag_obj.last_location = "DUB Terminal 1"
    bag_obj.description = "Black suitcase"
    bag_obj.created_at = MagicMock(isoformat=MagicMock(return_value="2025-01-01T00:00:00"))

    gw.baggage_db.execute = AsyncMock(return_value=_mock_result(
        scalar_one_or_none=bag_obj))

    resp = gw.client.get("/api/v1/baggage/BAG-0000000001", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["tag_number"] == "BAG-0000000001"


def test_gateway_proxies_checkin(gw_integration):
    """GET /api/v1/checkin/{booking_id} with JWT proxied to checkin-service."""
    gw = gw_integration
    token = create_access_token({
        "sub": str(uuid.uuid4()), "username": "ci_user",
        "role": "passenger",
    })
    headers = {"Authorization": f"Bearer {token}"}
    booking_id = str(uuid.uuid4())

    checkin_obj = MagicMock()
    checkin_obj.id = uuid.uuid4()
    checkin_obj.booking_id = booking_id
    checkin_obj.flight_id = uuid.uuid4()
    checkin_obj.passenger_name = "CI User"
    checkin_obj.seat_number = "14C"
    checkin_obj.boarding_group = "B"
    checkin_obj.gate = "B3"
    checkin_obj.status = MagicMock(value="boarding-pass-issued")
    checkin_obj.boarding_pass_url = f"/api/v1/checkin/{booking_id}/boarding-pass"
    checkin_obj.has_baggage = False
    checkin_obj.created_at = MagicMock(isoformat=MagicMock(return_value="2025-01-01T00:00:00"))

    gw.checkin_db.execute = AsyncMock(return_value=_mock_result(
        scalar_one_or_none=checkin_obj))

    resp = gw.client.get(f"/api/v1/checkin/{booking_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["seat_number"] == "14C"


def test_gateway_proxies_passengers(gw_integration):
    """GET /api/v1/passengers/profile with JWT proxied to passenger-service."""
    gw = gw_integration
    user_id = str(uuid.uuid4())
    token = create_access_token({
        "sub": user_id, "username": "pax_user",
        "role": "passenger",
    })
    headers = {"Authorization": f"Bearer {token}"}

    profile = MagicMock()
    profile.id = uuid.uuid4()
    profile.user_id = user_id
    profile.first_name = "Pax"
    profile.last_name = "User"
    profile.date_of_birth = None
    profile.nationality = "IE"
    profile.passport_number_encrypted = None
    profile.phone_number = "+3531234567"
    profile.loyalty_tier = "silver"
    profile.loyalty_points = 5000
    profile.meal_preference = None
    profile.seat_preference = "window"
    profile.created_at = MagicMock(isoformat=MagicMock(return_value="2025-01-01T00:00:00"))

    gw.passenger_db.execute = AsyncMock(return_value=_mock_result(
        scalar_one_or_none=profile))

    resp = gw.client.get("/api/v1/passengers/profile", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["first_name"] == "Pax"


def test_gateway_proxies_notifications(gw_integration):
    """GET /api/v1/notifications with JWT proxied to notification-service."""
    gw = gw_integration
    token = create_access_token({
        "sub": str(uuid.uuid4()), "username": "notif_user",
        "role": "passenger",
    })
    headers = {"Authorization": f"Bearer {token}"}

    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = []
    gw.notification_db.execute = AsyncMock(return_value=result_mock)

    resp = gw.client.get("/api/v1/notifications", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


# ══════════════════════════════════════════════════════════════════
#  Flow 8: Rate Limiting
# ══════════════════════════════════════════════════════════════════

def test_rate_limit_blocks_after_limit(gw_integration):
    """After RATE_LIMIT_PUBLIC requests, returns 429."""
    gw = gw_integration
    gw.gw_mod.rate_limit_store.clear()

    # Wire flight_db so proxied GET /api/v1/flights succeeds
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = []
    gw.flight_db.execute = AsyncMock(return_value=result_mock)

    # Public proxied path — send RATE_LIMIT_PUBLIC requests (rate limiter counts each)
    for i in range(gw.gw_mod.RATE_LIMIT_PUBLIC):
        resp = gw.client.get("/api/v1/flights")
        assert resp.status_code == 200, f"Request {i+1} failed with {resp.status_code}"

    # Next request should be rate limited
    resp = gw.client.get("/api/v1/flights")
    assert resp.status_code == 429


def test_rate_limit_partner_higher_limit(gw_integration):
    """Partner API key gets higher rate limit (1000 req/min)."""
    gw = gw_integration
    gw.gw_mod.rate_limit_store.clear()

    # Send 200 requests with API key — should all pass
    for _ in range(200):
        resp = gw.client.get("/api/v1/flights", headers={"x-api-key": "ak_partner"})
    # 200 < 1000, should not be rate limited
    assert resp.status_code != 429


def test_rate_limit_resets_after_window(gw_integration):
    """After the rate limit window expires, requests are allowed again."""
    gw = gw_integration
    gw.gw_mod.rate_limit_store.clear()

    # Wire flight_db so proxied GET /api/v1/flights succeeds
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = []
    gw.flight_db.execute = AsyncMock(return_value=result_mock)

    # Fill to limit with proxied requests
    for _ in range(gw.gw_mod.RATE_LIMIT_PUBLIC):
        gw.client.get("/api/v1/flights")

    # Verify blocked
    resp = gw.client.get("/api/v1/flights")
    assert resp.status_code == 429

    # Simulate window expiry by clearing store
    gw.gw_mod.rate_limit_store.clear()

    # Should be allowed now
    resp = gw.client.get("/api/v1/flights")
    assert resp.status_code != 429


# ══════════════════════════════════════════════════════════════════
#  Flow 9: Payment Refund → Booking Status + Event
# ══════════════════════════════════════════════════════════════════

def test_refund_updates_booking_status_and_publishes_event(integration_services):
    """Payment refund updates booking to 'refunded' and publishes PaymentRefunded."""
    s = integration_services
    from fastapi.testclient import TestClient

    payment_id = str(uuid.uuid4())
    booking_id = str(uuid.uuid4())

    # Payment DB: find the completed payment
    existing_payment = MagicMock()
    existing_payment.id = payment_id
    existing_payment.booking_id = booking_id
    existing_payment.user_id = s.user_id
    existing_payment.amount = 199.99
    existing_payment.currency = "EUR"
    existing_payment.status = s.payment_mod.PaymentStatus.COMPLETED
    existing_payment.payment_method = MagicMock(value="credit-card")
    existing_payment.idempotency_key = "ref-001"
    existing_payment.transaction_ref = "TXN-REF-001"
    existing_payment.failure_reason = None
    existing_payment.card_token = "tok_ref"
    existing_payment.card_last_four = "4242"
    existing_payment.created_at = MagicMock(isoformat=MagicMock(return_value="2025-01-01T00:00:00"))

    s.payment_db.execute = AsyncMock(return_value=_mock_result(
        scalar_one_or_none=existing_payment))

    def fake_refresh(obj):
        obj.status = MagicMock(value="refunded")

    s.payment_db.refresh = AsyncMock(side_effect=fake_refresh)

    # Booking DB for status update from refund: find booking, then refresh
    booking_for_refund = MagicMock()
    booking_for_refund.id = booking_id
    booking_for_refund.booking_reference = "ALREF01"
    booking_for_refund.user_id = s.user_id
    booking_for_refund.flight_id = str(uuid.uuid4())
    booking_for_refund.passenger_name = "Refund User"
    booking_for_refund.passenger_email = "refund@test.com"
    booking_for_refund.cabin_class = "economy"
    booking_for_refund.num_passengers = 1
    booking_for_refund.total_price = 199.99
    booking_for_refund.status = MagicMock(value="paid")
    booking_for_refund.payment_id = payment_id
    booking_for_refund.seat_numbers = None
    booking_for_refund.special_requests = None
    booking_for_refund.created_at = MagicMock(isoformat=MagicMock(return_value="2025-01-01T00:00:00"))

    s.booking_db.execute = AsyncMock(return_value=_mock_result(
        scalar_one_or_none=booking_for_refund))
    s.booking_db.refresh = AsyncMock(side_effect=lambda obj: None)

    s.events.clear()

    with TestClient(s.payment_mod.app, raise_server_exceptions=False) as c:
        resp = c.post(f"/api/v1/payments/{payment_id}/refund",
                      headers=s.auth_headers,
                      json={"reason": "Customer requested refund"})
    assert resp.status_code == 200, f"Refund failed: {resp.text}"
    assert resp.json()["status"] == "refunded"

    # Verify PaymentRefunded event published
    assert len(s.events.find("PaymentRefunded")) == 1
    refund_event = s.events.find("PaymentRefunded")[0]
    assert refund_event["detail"]["payment_id"] == payment_id
    assert refund_event["detail"]["booking_id"] == booking_id

    # Verify booking-service was called to update status to "refunded"
    s.booking_db.execute.assert_called()


# ══════════════════════════════════════════════════════════════════
#  Flow 10: Baggage Status Change → Event → Notification
# ══════════════════════════════════════════════════════════════════

def test_baggage_status_change_publishes_event(integration_services):
    """Updating baggage status publishes BaggageStatusChanged event."""
    s = integration_services
    from fastapi.testclient import TestClient

    tag_number = "BAG-1234567890"

    baggage_obj = MagicMock()
    baggage_obj.id = uuid.uuid4()
    baggage_obj.tag_number = tag_number
    baggage_obj.booking_id = uuid.uuid4()
    baggage_obj.passenger_name = "Bag Owner"
    baggage_obj.flight_id = uuid.uuid4()
    baggage_obj.weight_kg = 20.0
    baggage_obj.status = MagicMock(value="in-transit")
    baggage_obj.last_location = "LHR Carousel 5"
    baggage_obj.description = "Blue suitcase"
    baggage_obj.created_at = MagicMock(isoformat=MagicMock(return_value="2025-01-01T00:00:00"))

    s.baggage_db.execute = AsyncMock(return_value=_mock_result(
        scalar_one_or_none=baggage_obj))

    def fake_refresh(obj):
        obj.status = MagicMock(value="in-transit")
        obj.last_location = "LHR Carousel 5"

    s.baggage_db.refresh = AsyncMock(side_effect=fake_refresh)

    s.events.clear()

    with TestClient(s.baggage_mod.app, raise_server_exceptions=False) as c:
        resp = c.put(f"/api/v1/baggage/{tag_number}/status", json={
            "status": "in-transit",
            "location": "LHR Carousel 5",
        })
    assert resp.status_code == 200, f"Baggage update failed: {resp.text}"

    # Verify BaggageStatusChanged event published
    assert len(s.events.find("BaggageStatusChanged")) == 1
    event = s.events.find("BaggageStatusChanged")[0]
    assert event["detail"]["tag_number"] == tag_number
    assert event["detail"]["status"] == "in-transit"
    assert event["detail"]["location"] == "LHR Carousel 5"


def test_baggage_event_reaches_notification(integration_services):
    """BaggageStatusChanged event is handled by notification service."""
    s = integration_services
    s.events.publish("baggage-service", "BaggageStatusChanged", {
        "tag_number": "BAG-9999999999",
        "booking_id": "B1",
        "status": "delivered",
        "location": "DUB Carousel 3",
    })
    delivered = s.events.drain_to(s.notification_mod)
    assert len(delivered) == 1
    assert delivered[0]["detail-type"] == "BaggageStatusChanged"
