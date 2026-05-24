"""
Extended integration tests: auth, flight CRUD, baggage, passenger,
check-in boarding passes, payment webhooks, and notifications.
Each area is tested end-to-end with the multi-service transport bridge.
"""
import sys
import os
import uuid
import json
import importlib.util
from dataclasses import dataclass, field
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.database import Base
from shared.auth import create_access_token, create_refresh_token, hash_password

# Pre-mock boto3 and stripe before any service import
_mock_boto3 = MagicMock()
sys.modules.setdefault("boto3", _mock_boto3)
if "stripe" not in sys.modules:
    sys.modules["stripe"] = MagicMock()
_mock_stripe = sys.modules["stripe"]

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


# ══════════════════════════════════════════════════════════════════
#  Infrastructure (mirrors test_integration.py)
# ══════════════════════════════════════════════════════════════════

class IntegrationTransport(httpx.AsyncBaseTransport):
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
    def __init__(self):
        self.events: list[dict] = []

    def publish(self, source: str, detail_type: str, detail: dict) -> dict:
        detail["timestamp"] = datetime.now(timezone.utc).isoformat()
        self.events.append({"source": source, "detail-type": detail_type, "detail": detail})
        return {"FailedEntryCount": 0}

    def find(self, detail_type: str) -> list[dict]:
        return [e for e in self.events if e["detail-type"] == detail_type]

    def clear(self):
        self.events.clear()


def _create_mock_db():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.delete = AsyncMock()
    return session


class _multi_patch:
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


def _load_svc(service_dir, alias, db, extra_patches=None, env_overrides=None):
    svc_path = os.path.join(PROJECT_ROOT, service_dir)
    sys.path.insert(0, svc_path)
    for mod_name in ["models", "schemas"]:
        sys.modules.pop(mod_name, None)

    mock_engine = MagicMock()
    mock_engine.begin.return_value = AsyncMock()
    mock_engine.dispose = AsyncMock()

    patches = {
        "shared.database.create_db_engine": mock_engine,
        "shared.database.create_session_factory": MagicMock(),
        "shared.logging.setup_logging": MagicMock(),
    }
    if extra_patches:
        patches.update(extra_patches)

    spec = importlib.util.spec_from_file_location(alias, os.path.join(svc_path, "main.py"))
    mod = importlib.util.module_from_spec(spec)
    with _multi_patch(patches), patch.dict(os.environ, env_overrides or {}):
        spec.loader.exec_module(mod)

    async def mock_get_db():
        yield db

    mod.app.dependency_overrides[mod.get_db] = mock_get_db
    return mod


def _mock_result(scalar_one_or_none=None, scalars_all=None, rowcount=1):
    r = MagicMock()
    r.scalar_one_or_none.return_value = scalar_one_or_none
    r.rowcount = rowcount
    if scalars_all is not None:
        r.scalars.return_value.all.return_value = scalars_all
    return r


# ── Object mock helpers ──────────────────────────────────────────

def _flight_mock(flight_id=None):
    f = MagicMock()
    f.id = flight_id or str(uuid.uuid4())
    f.flight_number = "AL200"
    f.airline = "AeroLink"
    f.origin = "DUB"
    f.destination = "LHR"
    f.departure_date = "2026-07-01"
    f.departure_time = "09:00:00"
    f.arrival_date = "2026-07-01"
    f.arrival_time = "10:30:00"
    f.status = MagicMock(value="scheduled")
    f.aircraft_type = "A320"
    f.available_seats_economy = 140
    f.available_seats_business = 20
    f.available_seats_first = 8
    f.total_seats_economy = 150
    f.price_economy = 199.99
    f.price_business = 599.99
    f.price_first = 1299.99
    f.gate = "B3"
    f.terminal = "T2"
    f.version = 1
    f.created_at = MagicMock(isoformat=MagicMock(return_value="2026-01-01T00:00:00"))
    return f


def _booking_mock(booking_id=None, flight_id=None, user_id=None):
    b = MagicMock()
    b.id = booking_id or str(uuid.uuid4())
    b.booking_reference = "ALEXTEST1"
    b.user_id = user_id or str(uuid.uuid4())
    b.flight_id = flight_id or str(uuid.uuid4())
    b.passenger_name = "Test User"
    b.passenger_email = "test@test.com"
    b.cabin_class = "economy"
    b.num_passengers = 1
    b.total_price = 199.99
    b.status = MagicMock(value="paid")
    b.payment_id = None
    b.seat_numbers = None
    b.special_requests = None
    b.trip_type = "one_way"
    b.group_booking_id = None
    b.title = None
    b.gender = None
    b.first_name = None
    b.middle_name = None
    b.last_name = None
    b.date_of_birth = None
    b.nationality = None
    b.passport_number = None
    b.passport_expiry = None
    b.country_code = None
    b.phone_number = None
    b.created_at = MagicMock(isoformat=MagicMock(return_value="2026-01-01T00:00:00"))
    return b


def _baggage_mock(tag="BAG-0001234567"):
    b = MagicMock()
    b.id = str(uuid.uuid4())
    b.tag_number = tag
    b.booking_id = str(uuid.uuid4())
    b.passenger_name = "Test User"
    b.passenger_email = "test@test.com"
    b.flight_id = str(uuid.uuid4())
    b.weight_kg = 23.0
    b.status = MagicMock(value="checked_in")
    b.last_location = "DUB"
    b.description = "Black suitcase"
    b.created_at = MagicMock()
    return b


def _passenger_mock(user_id=None):
    p = MagicMock()
    p.id = str(uuid.uuid4())
    p.user_id = user_id or str(uuid.uuid4())
    p.title = "Mr"
    p.gender = "male"
    p.first_name = "Test"
    p.middle_name = None
    p.last_name = "User"
    p.date_of_birth = "1990-01-01"
    p.nationality = "Irish"
    p.passport_number_encrypted = None
    p.passport_expiry = None
    p.phone_number = "+353871234567"
    p.loyalty_tier = "bronze"
    p.loyalty_points = 0
    p.meal_preference = None
    p.seat_preference = None
    p.created_at = MagicMock()
    return p


def _notification_mock():
    n = MagicMock()
    n.id = uuid.uuid4()
    n.recipient_email = "test@test.com"
    n.recipient_name = "Test User"
    n.notification_type = MagicMock(value="email")
    n.subject = "Test Subject"
    n.body = "Test Body"
    n.event_type = "BookingCreated"
    n.status = MagicMock(value="sent")
    n.is_read = False
    n.created_at = MagicMock()
    return n


def _payment_mock(payment_id=None):
    p = MagicMock()
    p.id = payment_id or str(uuid.uuid4())
    p.booking_id = str(uuid.uuid4())
    p.user_id = str(uuid.uuid4())
    p.amount = 199.99
    p.currency = "EUR"
    p.status = MagicMock(value="completed")
    p.stripe_payment_intent_id = "pi_test_ext"
    p.idempotency_key = "idem-ext-001"
    p.transaction_ref = "TXN-EXT-001"
    p.failure_reason = None
    p.provider = "stripe"
    p.payment_method_type = None
    p.wallet_brand = None
    p.last_four = None
    p.created_at = MagicMock(isoformat=MagicMock(return_value="2026-01-01T00:00:00"))
    return p


def _user_mock(user_id=None, password="TestPass123!"):
    u = MagicMock()
    u.id = user_id or uuid.uuid4()
    u.email = "user@test.com"
    u.username = "testuser"
    u.hashed_password = hash_password(password)
    u.full_name = "Test User"
    u.role = MagicMock(value="passenger")
    u.is_active = True
    u.created_at = MagicMock()
    return u


# ══════════════════════════════════════════════════════════════════
#  Fixtures
# ══════════════════════════════════════════════════════════════════

@dataclass
class ExtBundle:
    flight_mod: object = None
    booking_mod: object = None
    payment_mod: object = None
    checkin_mod: object = None
    passenger_mod: object = None
    notification_mod: object = None
    baggage_mod: object = None
    flight_db: object = None
    booking_db: object = None
    payment_db: object = None
    checkin_db: object = None
    passenger_db: object = None
    notification_db: object = None
    baggage_db: object = None
    events: EventCapture = field(default_factory=EventCapture)
    auth_headers: dict = field(default_factory=dict)
    admin_headers: dict = field(default_factory=dict)
    user_id: str = ""


@dataclass
class ExtGwBundle:
    client: object = None
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
    user_id: str = ""
    auth_headers: dict = field(default_factory=dict)
    admin_headers: dict = field(default_factory=dict)


@pytest.fixture
def ext_services():
    Base.metadata.clear()

    dbs = {svc: _create_mock_db() for svc in
           ["flight", "booking", "payment", "checkin", "passenger", "notification", "baggage"]}

    mock_redis = MagicMock()
    mock_redis.get = MagicMock(return_value=None)
    mock_redis.set = MagicMock(return_value=True)
    mock_redis.setex = MagicMock(return_value=True)
    mock_redis.delete = MagicMock(return_value=1)
    mock_redis.keys = MagicMock(return_value=[])
    mock_redis.ping = MagicMock(return_value=True)

    flight_mod   = _load_svc("services/flight-service",       "ext_flight",   dbs["flight"],
                             extra_patches={"redis.Redis.from_url": mock_redis})
    booking_mod  = _load_svc("services/booking-service",      "ext_booking",  dbs["booking"])
    payment_mod  = _load_svc("services/payment-service",      "ext_payment",  dbs["payment"],
                             env_overrides={"STRIPE_SECRET_KEY": "sk_test_fake",
                                            "STRIPE_WEBHOOK_SECRET": "whsec_test"})
    checkin_mod  = _load_svc("services/checkin-service",      "ext_checkin",  dbs["checkin"])
    passenger_mod = _load_svc("services/passenger-service",   "ext_passenger", dbs["passenger"])
    baggage_mod  = _load_svc("services/baggage-service",      "ext_baggage",  dbs["baggage"])
    notification_mod = _load_svc("services/notification-service", "ext_notif",
                                 dbs["notification"],
                                 env_overrides={"ENABLE_SQS_POLLING": "false"})

    events = EventCapture()
    for mod in [flight_mod, booking_mod, payment_mod, checkin_mod, baggage_mod]:
        mod.event_publisher = events

    payment_mod.record_audit = AsyncMock()
    passenger_mod.record_audit = AsyncMock()

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

    user_id = str(uuid.uuid4())
    token = create_access_token({"sub": user_id, "username": "ext_user", "role": "passenger"})
    admin_token = create_access_token({"sub": str(uuid.uuid4()), "username": "admin_user",
                                       "role": "admin"})

    bundle = ExtBundle(
        flight_mod=flight_mod, booking_mod=booking_mod,
        payment_mod=payment_mod, checkin_mod=checkin_mod,
        passenger_mod=passenger_mod, notification_mod=notification_mod,
        baggage_mod=baggage_mod,
        flight_db=dbs["flight"], booking_db=dbs["booking"],
        payment_db=dbs["payment"], checkin_db=dbs["checkin"],
        passenger_db=dbs["passenger"], notification_db=dbs["notification"],
        baggage_db=dbs["baggage"],
        events=events, user_id=user_id,
        auth_headers={"Authorization": f"Bearer {token}"},
        admin_headers={"Authorization": f"Bearer {admin_token}"},
    )

    original_init = httpx.AsyncClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        kwargs.pop("timeout", None)
        original_init(self, *args, **kwargs)

    svc_paths = []
    for svc_dir in ["services/flight-service", "services/booking-service",
                    "services/payment-service", "services/baggage-service",
                    "services/checkin-service", "services/passenger-service",
                    "services/notification-service"]:
        p = os.path.join(PROJECT_ROOT, svc_dir)
        if p not in svc_paths:
            svc_paths.append(p)

    with patch.object(httpx.AsyncClient, "__init__", patched_init):
        yield bundle

    for mod in [flight_mod, booking_mod, payment_mod, baggage_mod,
                checkin_mod, passenger_mod, notification_mod]:
        mod.app.dependency_overrides.clear()
    for mod_name in ["models", "schemas"]:
        sys.modules.pop(mod_name, None)
    for p in svc_paths:
        if p in sys.path:
            sys.path.remove(p)


@pytest.fixture
def ext_gw():
    """Gateway + all services for auth and gateway edge-case tests."""
    Base.metadata.clear()

    dbs = {svc: _create_mock_db() for svc in
           ["auth", "flight", "booking", "payment", "baggage",
            "checkin", "passenger", "notification"]}

    mock_redis = MagicMock()
    mock_redis.get = MagicMock(return_value=None)
    mock_redis.set = MagicMock(return_value=True)
    mock_redis.setex = MagicMock(return_value=True)
    mock_redis.delete = MagicMock(return_value=1)
    mock_redis.keys = MagicMock(return_value=[])
    mock_redis.ping = MagicMock(return_value=True)

    auth_mod     = _load_svc("services/auth-service",         "ext_gw_auth",    dbs["auth"])
    flight_mod   = _load_svc("services/flight-service",       "ext_gw_flight",  dbs["flight"],
                             extra_patches={"redis.Redis.from_url": mock_redis})
    booking_mod  = _load_svc("services/booking-service",      "ext_gw_booking", dbs["booking"])
    payment_mod  = _load_svc("services/payment-service",      "ext_gw_payment", dbs["payment"],
                             env_overrides={"STRIPE_SECRET_KEY": "sk_test_fake",
                                            "STRIPE_WEBHOOK_SECRET": "whsec_test"})
    baggage_mod  = _load_svc("services/baggage-service",      "ext_gw_baggage", dbs["baggage"])
    checkin_mod  = _load_svc("services/checkin-service",      "ext_gw_checkin", dbs["checkin"])
    passenger_mod = _load_svc("services/passenger-service",   "ext_gw_pax",     dbs["passenger"])
    notification_mod = _load_svc("services/notification-service", "ext_gw_notif",
                                 dbs["notification"],
                                 env_overrides={"ENABLE_SQS_POLLING": "false"})

    payment_mod.record_audit = AsyncMock()
    passenger_mod.record_audit = AsyncMock()

    gw_path = os.path.join(PROJECT_ROOT, "api-gateway")
    sys.path.insert(0, gw_path)
    for mod_name in ["models", "schemas"]:
        sys.modules.pop(mod_name, None)
    spec = importlib.util.spec_from_file_location(
        "ext_gw_main", os.path.join(gw_path, "main.py"))
    gw_mod = importlib.util.module_from_spec(spec)
    with patch("shared.logging.setup_logging"):
        spec.loader.exec_module(gw_mod)

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

    original_init = httpx.AsyncClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        kwargs.pop("timeout", None)
        original_init(self, *args, **kwargs)

    user_id = str(uuid.uuid4())
    token = create_access_token({"sub": user_id, "username": "gw_user", "role": "passenger"})
    admin_token = create_access_token({"sub": str(uuid.uuid4()), "username": "gw_admin",
                                       "role": "admin"})

    bundle = ExtGwBundle(
        auth_mod=auth_mod, auth_db=dbs["auth"],
        flight_mod=flight_mod, flight_db=dbs["flight"],
        booking_mod=booking_mod, booking_db=dbs["booking"],
        payment_mod=payment_mod, payment_db=dbs["payment"],
        baggage_mod=baggage_mod, baggage_db=dbs["baggage"],
        checkin_mod=checkin_mod, checkin_db=dbs["checkin"],
        passenger_mod=passenger_mod, passenger_db=dbs["passenger"],
        notification_mod=notification_mod, notification_db=dbs["notification"],
        user_id=user_id,
        auth_headers={"Authorization": f"Bearer {token}"},
        admin_headers={"Authorization": f"Bearer {admin_token}"},
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
#  Auth service
# ══════════════════════════════════════════════════════════════════

def test_auth_register_success(ext_gw):
    g = ext_gw

    def fake_refresh(obj):
        obj.id = uuid.uuid4()
        obj.email = "newuser@test.com"
        obj.username = "newuser"
        obj.full_name = "New User"
        obj.role = MagicMock(value="passenger")
        obj.is_active = True
        obj.created_at = MagicMock()

    g.auth_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=None))
    g.auth_db.refresh = AsyncMock(side_effect=fake_refresh)

    with TestClient(g.auth_mod.app, raise_server_exceptions=False) as c:
        resp = c.post("/api/v1/auth/register", json={
            "email": "newuser@test.com",
            "username": "newuser",
            "password": "SecurePass123!",
            "full_name": "New User",
        })
    assert resp.status_code == 201
    assert resp.json()["email"] == "newuser@test.com"
    assert resp.json()["username"] == "newuser"


def test_auth_duplicate_registration(ext_gw):
    g = ext_gw
    existing_user = _user_mock()
    g.auth_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=existing_user))

    with TestClient(g.auth_mod.app, raise_server_exceptions=False) as c:
        resp = c.post("/api/v1/auth/register", json={
            "email": "existing@test.com",
            "username": "existinguser",
            "password": "SecurePass123!",
            "full_name": "Existing User",
        })
    assert resp.status_code == 409


def test_auth_login_success(ext_gw):
    g = ext_gw
    password = "TestPass123!"
    user = _user_mock(password=password)
    g.auth_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=user))

    with TestClient(g.auth_mod.app, raise_server_exceptions=False) as c:
        resp = c.post("/api/v1/auth/login", json={
            "username": "testuser",
            "password": password,
        })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["expires_in"] > 0


def test_auth_invalid_credentials(ext_gw):
    g = ext_gw
    user = _user_mock(password="CorrectPassword!")
    g.auth_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=user))

    with TestClient(g.auth_mod.app, raise_server_exceptions=False) as c:
        resp = c.post("/api/v1/auth/login", json={
            "username": "testuser",
            "password": "WrongPassword!",
        })
    assert resp.status_code == 401


def test_auth_token_refresh(ext_gw):
    g = ext_gw
    user_id = str(uuid.uuid4())
    refresh_tok = create_refresh_token({
        "sub": user_id, "email": "r@test.com",
        "username": "ruser", "role": "passenger",
    })

    with TestClient(g.auth_mod.app, raise_server_exceptions=False) as c:
        resp = c.post("/api/v1/auth/refresh", json={"refresh_token": refresh_tok})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_auth_get_me(ext_gw):
    g = ext_gw
    user = _user_mock(user_id=uuid.UUID(g.user_id))
    g.auth_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=user))

    with TestClient(g.auth_mod.app, raise_server_exceptions=False) as c:
        resp = c.get("/api/v1/auth/me", headers=g.auth_headers)
    assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════
#  Flight service
# ══════════════════════════════════════════════════════════════════

def test_flight_search_returns_flights(ext_services):
    s = ext_services
    flight = _flight_mock()
    s.flight_db.execute = AsyncMock(return_value=_mock_result(scalars_all=[flight]))

    with TestClient(s.flight_mod.app, raise_server_exceptions=False) as c:
        resp = c.get("/api/v1/flights?origin=DUB&destination=LHR")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert len(data["items"]) == 1
    assert data["items"][0]["origin"] == "DUB"
    assert data["items"][0]["destination"] == "LHR"


def test_flight_search_no_results(ext_services):
    s = ext_services
    s.flight_db.execute = AsyncMock(return_value=_mock_result(scalars_all=[]))

    with TestClient(s.flight_mod.app, raise_server_exceptions=False) as c:
        resp = c.get("/api/v1/flights?origin=XYZ&destination=ABC")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_flight_get_by_id(ext_services):
    s = ext_services
    flight_id = str(uuid.uuid4())
    flight = _flight_mock(flight_id=flight_id)
    s.flight_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=flight))

    with TestClient(s.flight_mod.app, raise_server_exceptions=False) as c:
        resp = c.get(f"/api/v1/flights/{flight_id}")
    assert resp.status_code == 200
    assert resp.json()["flight_number"] == "AL200"


def test_flight_not_found(ext_services):
    s = ext_services
    s.flight_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=None))

    with TestClient(s.flight_mod.app, raise_server_exceptions=False) as c:
        resp = c.get(f"/api/v1/flights/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_admin_creates_flight(ext_services):
    s = ext_services
    flight_id = str(uuid.uuid4())
    flight = _flight_mock(flight_id=flight_id)
    s.flight_db.refresh = AsyncMock(side_effect=lambda obj: None)
    # Patch refresh to fill in flight attributes
    def fake_flight_refresh(obj):
        for attr in vars(flight):
            try:
                setattr(obj, attr, getattr(flight, attr))
            except Exception:
                pass
        obj.id = flight_id
        obj.flight_number = "AL300"
        obj.airline = "AeroLink"
        obj.origin = "DUB"
        obj.destination = "CDG"
        obj.status = MagicMock(value="scheduled")
        obj.aircraft_type = "B737"
        obj.available_seats_economy = 100
        obj.available_seats_business = 20
        obj.available_seats_first = 5
        obj.price_economy = 250.0
        obj.price_business = 700.0
        obj.price_first = 1500.0
        obj.gate = "C1"
        obj.terminal = "T3"
        obj.departure_date = "2026-08-01"
        obj.departure_time = "08:00:00"
        obj.arrival_date = "2026-08-01"
        obj.arrival_time = "10:00:00"
        obj.created_at = MagicMock(isoformat=MagicMock(return_value="2026-01-01T00:00:00"))

    s.flight_db.refresh = AsyncMock(side_effect=fake_flight_refresh)

    with TestClient(s.flight_mod.app, raise_server_exceptions=False) as c:
        resp = c.post("/api/v1/flights", headers=s.admin_headers, json={
            "flight_number": "AL300",
            "airline": "AeroLink",
            "origin": "DUB",
            "destination": "CDG",
            "departure_date": "2026-08-01",
            "departure_time": "08:00:00",
            "arrival_date": "2026-08-01",
            "arrival_time": "10:00:00",
            "aircraft_type": "B737",
            "total_seats_economy": 100,
            "total_seats_business": 20,
            "total_seats_first": 5,
            "price_economy": 250.0,
            "price_business": 700.0,
            "price_first": 1500.0,
        })
    assert resp.status_code == 201
    assert resp.json()["flight_number"] == "AL300"
    # Verify FlightScheduleUpdated event
    assert len(s.events.find("FlightScheduleUpdated")) == 1


def test_passenger_role_cannot_create_flight(ext_services):
    s = ext_services
    with TestClient(s.flight_mod.app, raise_server_exceptions=False) as c:
        resp = c.post("/api/v1/flights", headers=s.auth_headers, json={
            "flight_number": "AL999",
            "airline": "AeroLink",
            "origin": "DUB",
            "destination": "LHR",
            "departure_date": "2026-09-01",
            "departure_time": "10:00:00",
            "arrival_date": "2026-09-01",
            "arrival_time": "11:30:00",
            "aircraft_type": "A320",
            "total_seats_economy": 150,
            "total_seats_business": 30,
            "total_seats_first": 10,
            "price_economy": 199.0,
            "price_business": 599.0,
            "price_first": 1299.0,
        })
    assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════
#  Booking service
# ══════════════════════════════════════════════════════════════════

def test_list_bookings_for_user(ext_services):
    s = ext_services
    booking = _booking_mock(user_id=s.user_id)
    s.booking_db.execute = AsyncMock(return_value=_mock_result(scalars_all=[booking]))

    with TestClient(s.booking_mod.app, raise_server_exceptions=False) as c:
        resp = c.get("/api/v1/bookings", headers=s.auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) == 1


def test_get_booking_by_id(ext_services):
    s = ext_services
    booking_id = str(uuid.uuid4())
    booking = _booking_mock(booking_id=booking_id, user_id=s.user_id)
    s.booking_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=booking))

    with TestClient(s.booking_mod.app, raise_server_exceptions=False) as c:
        resp = c.get(f"/api/v1/bookings/{booking_id}", headers=s.auth_headers)
    assert resp.status_code == 200
    assert resp.json()["booking_reference"] == "ALEXTEST1"


def test_booking_not_found(ext_services):
    s = ext_services
    s.booking_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=None))

    with TestClient(s.booking_mod.app, raise_server_exceptions=False) as c:
        resp = c.get(f"/api/v1/bookings/{uuid.uuid4()}", headers=s.auth_headers)
    assert resp.status_code == 404


def test_seat_availability_endpoint(ext_services):
    s = ext_services
    flight_id = str(uuid.uuid4())
    # Seat availability queries economy bookings count
    s.booking_db.execute = AsyncMock(return_value=_mock_result(scalars_all=[]))

    with TestClient(s.booking_mod.app, raise_server_exceptions=False) as c:
        resp = c.get(f"/api/v1/bookings/seat-availability?flight_id={flight_id}",
                     headers=s.auth_headers)
    assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════
#  Baggage service
# ══════════════════════════════════════════════════════════════════

def test_register_baggage_publishes_event(ext_services):
    s = ext_services
    booking_id = str(uuid.uuid4())
    flight_id = str(uuid.uuid4())
    bag = _baggage_mock()
    bag.booking_id = booking_id
    bag.flight_id = flight_id
    s.baggage_db.refresh = AsyncMock(side_effect=lambda obj: None)

    def fake_bag_refresh(obj):
        obj.id = str(uuid.uuid4())
        obj.tag_number = bag.tag_number
        obj.booking_id = booking_id
        obj.passenger_name = "Test User"
        obj.passenger_email = "test@test.com"
        obj.flight_id = flight_id
        obj.weight_kg = 23.0
        obj.status = MagicMock(value="checked_in")
        obj.last_location = None
        obj.description = "Black suitcase"
        obj.created_at = MagicMock()

    s.baggage_db.refresh = AsyncMock(side_effect=fake_bag_refresh)
    s.events.clear()

    with TestClient(s.baggage_mod.app, raise_server_exceptions=False) as c:
        resp = c.post("/api/v1/baggage", headers=s.auth_headers, json={
            "booking_id": booking_id,
            "passenger_name": "Test User",
            "passenger_email": "test@test.com",
            "flight_id": flight_id,
            "weight_kg": 23.0,
            "description": "Black suitcase",
        })
    assert resp.status_code == 201
    assert resp.json()["weight_kg"] == 23.0
    assert len(s.events.find("BaggageRegistered")) == 1


def test_baggage_by_booking_id(ext_services):
    s = ext_services
    booking_id = str(uuid.uuid4())
    bag = _baggage_mock()
    bag.booking_id = booking_id
    s.baggage_db.execute = AsyncMock(return_value=_mock_result(scalars_all=[bag]))

    with TestClient(s.baggage_mod.app, raise_server_exceptions=False) as c:
        resp = c.get(f"/api/v1/baggage/booking/{booking_id}", headers=s.auth_headers)
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)
    assert len(items) == 1


def test_baggage_tag_not_found(ext_services):
    s = ext_services
    s.baggage_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=None))

    with TestClient(s.baggage_mod.app, raise_server_exceptions=False) as c:
        resp = c.get("/api/v1/baggage/BAG-0000000000")
    assert resp.status_code == 404


def test_admin_updates_baggage_status(ext_services):
    s = ext_services
    bag = _baggage_mock()
    s.baggage_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=bag))
    s.baggage_db.refresh = AsyncMock(side_effect=lambda obj: None)

    def fake_bag_refresh(obj):
        obj.id = bag.id
        obj.tag_number = bag.tag_number
        obj.booking_id = bag.booking_id
        obj.passenger_name = bag.passenger_name
        obj.flight_id = bag.flight_id
        obj.weight_kg = bag.weight_kg
        obj.status = MagicMock(value="loaded")
        obj.last_location = "DUB-Cargo"
        obj.description = bag.description
        obj.created_at = MagicMock()

    s.baggage_db.refresh = AsyncMock(side_effect=fake_bag_refresh)

    with TestClient(s.baggage_mod.app, raise_server_exceptions=False) as c:
        resp = c.put(
            f"/api/v1/baggage/{bag.tag_number}/status",
            headers=s.admin_headers,
            json={"status": "loaded", "location": "DUB-Cargo"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "loaded"
    assert len(s.events.find("BaggageStatusChanged")) == 1


def test_non_admin_cannot_update_baggage_status(ext_services):
    s = ext_services
    with TestClient(s.baggage_mod.app, raise_server_exceptions=False) as c:
        resp = c.put(
            "/api/v1/baggage/BAG-0000000001/status",
            headers=s.auth_headers,
            json={"status": "loaded", "location": "DUB-Cargo"},
        )
    assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════
#  Passenger service
# ══════════════════════════════════════════════════════════════════

def test_passenger_create_profile(ext_services):
    s = ext_services
    profile = _passenger_mock(user_id=s.user_id)

    # No existing profile
    s.passenger_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=None))

    def fake_profile_refresh(obj):
        obj.id = str(uuid.uuid4())
        obj.user_id = s.user_id
        obj.title = "Mr"
        obj.gender = "male"
        obj.first_name = "Test"
        obj.middle_name = None
        obj.last_name = "User"
        obj.date_of_birth = "1990-01-01"
        obj.nationality = "Irish"
        obj.passport_number_encrypted = None
        obj.passport_expiry = None
        obj.phone_number = "+353871234567"
        obj.loyalty_tier = "bronze"
        obj.loyalty_points = 0
        obj.meal_preference = None
        obj.seat_preference = None
        obj.created_at = MagicMock()

    s.passenger_db.refresh = AsyncMock(side_effect=fake_profile_refresh)

    with TestClient(s.passenger_mod.app, raise_server_exceptions=False) as c:
        resp = c.post("/api/v1/passengers/profile", headers=s.auth_headers, json={
            "first_name": "Test",
            "last_name": "User",
            "date_of_birth": "1990-01-01",
            "nationality": "Irish",
            "phone_number": "+353871234567",
            "title": "Mr",
            "gender": "male",
        })
    assert resp.status_code == 201
    assert resp.json()["first_name"] == "Test"
    assert resp.json()["last_name"] == "User"


def test_passenger_duplicate_profile_returns_409(ext_services):
    s = ext_services
    existing = _passenger_mock(user_id=s.user_id)
    s.passenger_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=existing))

    with TestClient(s.passenger_mod.app, raise_server_exceptions=False) as c:
        resp = c.post("/api/v1/passengers/profile", headers=s.auth_headers, json={
            "first_name": "Test", "last_name": "User",
            "date_of_birth": "1990-01-01", "nationality": "Irish",
        })
    assert resp.status_code == 409


def test_passenger_get_profile_success(ext_services):
    s = ext_services
    profile = _passenger_mock(user_id=s.user_id)
    s.passenger_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=profile))

    with TestClient(s.passenger_mod.app, raise_server_exceptions=False) as c:
        resp = c.get("/api/v1/passengers/profile", headers=s.auth_headers)
    assert resp.status_code == 200
    assert resp.json()["first_name"] == "Test"


def test_passenger_get_profile_not_found(ext_services):
    s = ext_services
    s.passenger_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=None))

    with TestClient(s.passenger_mod.app, raise_server_exceptions=False) as c:
        resp = c.get("/api/v1/passengers/profile", headers=s.auth_headers)
    assert resp.status_code == 404


def test_passenger_update_profile(ext_services):
    s = ext_services
    profile = _passenger_mock(user_id=s.user_id)
    s.passenger_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=profile))

    def fake_update_refresh(obj):
        obj.id = profile.id
        obj.user_id = s.user_id
        obj.title = "Ms"
        obj.gender = "female"
        obj.first_name = "Updated"
        obj.middle_name = None
        obj.last_name = "Name"
        obj.date_of_birth = "1992-05-15"
        obj.nationality = "Irish"
        obj.passport_number_encrypted = None
        obj.passport_expiry = None
        obj.phone_number = "+353871234567"
        obj.loyalty_tier = "bronze"
        obj.loyalty_points = 0
        obj.meal_preference = "vegetarian"
        obj.seat_preference = "window"
        obj.created_at = MagicMock()

    s.passenger_db.refresh = AsyncMock(side_effect=fake_update_refresh)

    with TestClient(s.passenger_mod.app, raise_server_exceptions=False) as c:
        resp = c.put("/api/v1/passengers/profile", headers=s.auth_headers, json={
            "first_name": "Updated",
            "last_name": "Name",
            "meal_preference": "vegetarian",
            "seat_preference": "window",
        })
    assert resp.status_code == 200
    assert resp.json()["first_name"] == "Updated"
    assert resp.json()["meal_preference"] == "vegetarian"


# ══════════════════════════════════════════════════════════════════
#  Check-in service
# ══════════════════════════════════════════════════════════════════

def test_checkin_not_found_by_booking(ext_services):
    s = ext_services
    s.checkin_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=None))

    with TestClient(s.checkin_mod.app, raise_server_exceptions=False) as c:
        resp = c.get(f"/api/v1/checkin/{uuid.uuid4()}", headers=s.auth_headers)
    assert resp.status_code == 404


def test_get_boarding_pass_html(ext_services):
    """HTML boarding pass fetches flight/booking via transport bridge."""
    s = ext_services
    booking_id = str(uuid.uuid4())
    flight_id = str(uuid.uuid4())

    checkin = MagicMock()
    checkin.passenger_name = "ALICE SMITH"
    checkin.seat_number = "14C"
    checkin.boarding_group = "A"
    checkin.gate = "D7"
    checkin.flight_id = flight_id
    checkin.booking_id = booking_id
    s.checkin_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=checkin))

    # Flight and booking serve data via transport bridge
    flight = _flight_mock(flight_id=flight_id)
    s.flight_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=flight))

    booking = _booking_mock(booking_id=booking_id, user_id=s.user_id)
    s.booking_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=booking))

    with TestClient(s.checkin_mod.app, raise_server_exceptions=False) as c:
        resp = c.get(f"/api/v1/checkin/{booking_id}/boarding-pass", headers=s.auth_headers)
    assert resp.status_code == 200
    assert "ALICE SMITH" in resp.text
    assert "14C" in resp.text


def test_get_boarding_pass_pdf_integration(ext_services):
    """PDF boarding pass fetches flight/booking data via transport bridge."""
    s = ext_services
    booking_id = str(uuid.uuid4())
    flight_id = str(uuid.uuid4())

    checkin = MagicMock()
    checkin.passenger_name = "BOB JONES"
    checkin.seat_number = "5A"
    checkin.boarding_group = "B"
    checkin.gate = "E2"
    checkin.flight_id = flight_id
    checkin.booking_id = booking_id
    s.checkin_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=checkin))

    # Flight data (ASCII only — no em-dashes in PDF rendering)
    flight = _flight_mock(flight_id=flight_id)
    s.flight_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=flight))

    booking = _booking_mock(booking_id=booking_id, user_id=s.user_id)
    s.booking_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=booking))

    with TestClient(s.checkin_mod.app, raise_server_exceptions=False) as c:
        resp = c.get(f"/api/v1/checkin/{booking_id}/boarding-pass/pdf", headers=s.auth_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert len(resp.content) > 100


def test_boarding_pass_not_found(ext_services):
    s = ext_services
    s.checkin_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=None))

    with TestClient(s.checkin_mod.app, raise_server_exceptions=False) as c:
        resp = c.get(f"/api/v1/checkin/{uuid.uuid4()}/boarding-pass", headers=s.auth_headers)
    assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════
#  Payment service
# ══════════════════════════════════════════════════════════════════

def test_payment_webhook_invalid_payload(ext_services):
    """ValueError from construct_event → 400 Invalid payload."""
    s = ext_services
    _mock_stripe.Webhook.construct_event.side_effect = ValueError("invalid json payload")

    with TestClient(s.payment_mod.app, raise_server_exceptions=False) as c:
        resp = c.post(
            "/api/v1/payments/stripe/webhook",
            content=b"not valid json",
            headers={"stripe-signature": "t=bad,v1=invalid"},
        )
    assert resp.status_code == 400
    _mock_stripe.Webhook.construct_event.side_effect = None  # reset for other tests


def test_get_payment_by_id(ext_services):
    s = ext_services
    payment = _payment_mock()
    s.payment_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=payment))

    with TestClient(s.payment_mod.app, raise_server_exceptions=False) as c:
        resp = c.get(f"/api/v1/payments/{payment.id}", headers=s.auth_headers)
    assert resp.status_code == 200
    assert resp.json()["currency"] == "EUR"


def test_payment_not_found(ext_services):
    s = ext_services
    s.payment_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=None))

    with TestClient(s.payment_mod.app, raise_server_exceptions=False) as c:
        resp = c.get(f"/api/v1/payments/{uuid.uuid4()}", headers=s.auth_headers)
    assert resp.status_code == 404


def test_payments_by_booking_id(ext_services):
    s = ext_services
    payment = _payment_mock()
    s.payment_db.execute = AsyncMock(return_value=_mock_result(scalars_all=[payment]))

    with TestClient(s.payment_mod.app, raise_server_exceptions=False) as c:
        resp = c.get(f"/api/v1/payments/booking/{uuid.uuid4()}")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) == 1


def test_payment_config_endpoint(ext_services):
    s = ext_services
    with TestClient(s.payment_mod.app, raise_server_exceptions=False) as c:
        resp = c.get("/api/v1/payments/config")
    assert resp.status_code == 200
    assert "publishable_key" in resp.json()


# ══════════════════════════════════════════════════════════════════
#  Notification service
# ══════════════════════════════════════════════════════════════════

def test_list_notifications(ext_services):
    s = ext_services
    notif = _notification_mock()
    s.notification_db.execute = AsyncMock(return_value=_mock_result(scalars_all=[notif]))

    with TestClient(s.notification_mod.app, raise_server_exceptions=False) as c:
        resp = c.get("/api/v1/notifications", headers=s.auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) == 1


def test_mark_notification_read_success(ext_services):
    s = ext_services
    notif = _notification_mock()
    s.notification_db.execute = AsyncMock(
        return_value=_mock_result(scalar_one_or_none=notif))
    s.notification_db.refresh = AsyncMock(return_value=None)

    with TestClient(s.notification_mod.app, raise_server_exceptions=False) as c:
        resp = c.patch(f"/api/v1/notifications/{notif.id}/read", headers=s.auth_headers)
    assert resp.status_code == 200
    assert notif.is_read is True


def test_mark_notification_read_not_found(ext_services):
    s = ext_services
    s.notification_db.execute = AsyncMock(
        return_value=_mock_result(scalar_one_or_none=None))

    with TestClient(s.notification_mod.app, raise_server_exceptions=False) as c:
        resp = c.patch(f"/api/v1/notifications/{uuid.uuid4()}/read", headers=s.auth_headers)
    assert resp.status_code == 404


def test_notification_service_health(ext_services):
    s = ext_services
    with TestClient(s.notification_mod.app, raise_server_exceptions=False) as c:
        resp = c.get("/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "notification-service"


# ══════════════════════════════════════════════════════════════════
#  Gateway auth edge cases
# ══════════════════════════════════════════════════════════════════

def test_gateway_expired_token_returns_401(ext_gw):
    g = ext_gw
    expired_token = create_access_token({"sub": "u1", "role": "passenger"}, expires_minutes=-1)
    resp = g.client.get("/api/v1/bookings",
                        headers={"Authorization": f"Bearer {expired_token}"})
    assert resp.status_code == 401


def test_gateway_no_auth_header_on_protected_route(ext_gw):
    g = ext_gw
    resp = g.client.get("/api/v1/bookings")
    assert resp.status_code == 401


def test_gateway_malformed_token_returns_401(ext_gw):
    g = ext_gw
    resp = g.client.get("/api/v1/bookings",
                        headers={"Authorization": "Bearer not.a.valid.token"})
    assert resp.status_code == 401


def test_gateway_routes_flight_search_with_valid_token(ext_gw):
    g = ext_gw
    g.flight_db.execute = AsyncMock(return_value=_mock_result(scalars_all=[]))
    resp = g.client.get("/api/v1/flights?origin=DUB", headers=g.auth_headers)
    assert resp.status_code == 200


def test_gateway_routes_to_auth_register(ext_gw):
    g = ext_gw

    def fake_refresh(obj):
        obj.id = uuid.uuid4()
        obj.email = "gw@test.com"
        obj.username = "gwuser"
        obj.full_name = "GW User"
        obj.role = MagicMock(value="passenger")
        obj.is_active = True
        obj.created_at = MagicMock()

    g.auth_db.execute = AsyncMock(return_value=_mock_result(scalar_one_or_none=None))
    g.auth_db.refresh = AsyncMock(side_effect=fake_refresh)

    resp = g.client.post("/api/v1/auth/register", json={
        "email": "gw@test.com",
        "username": "gwuser",
        "password": "SecurePass123!",
        "full_name": "GW User",
    })
    assert resp.status_code == 201
