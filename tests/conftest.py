"""Shared test fixtures for AeroLink test suite."""
import sys
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure project root is on path so shared/ and services/ are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Note: boto3 and psycopg2 are mocked in individual test files that need them,
# not here in conftest, to avoid PyO3 re-initialization conflicts with cryptography.


# ── Mock DB Session ──────────────────────────────────────────────

@pytest.fixture
def mock_db_session():
    """AsyncMock of SQLAlchemy AsyncSession."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.delete = AsyncMock()
    return session


# ── Mock Redis ───────────────────────────────────────────────────

@pytest.fixture
def mock_redis():
    """Mock Redis client with get/set/delete/keys."""
    r = MagicMock()
    r.get = MagicMock(return_value=None)
    r.set = MagicMock(return_value=True)
    r.setex = MagicMock(return_value=True)
    r.delete = MagicMock(return_value=1)
    r.keys = MagicMock(return_value=[])
    r.ping = MagicMock(return_value=True)
    return r


# ── Mock Event Publisher ─────────────────────────────────────────

@pytest.fixture
def mock_event_publisher():
    """Mock of shared.events.EventPublisher."""
    pub = MagicMock()
    pub.publish = MagicMock(return_value={"FailedEntryCount": 0})
    return pub


# ── Mock httpx client ────────────────────────────────────────────

@pytest.fixture
def mock_httpx_client():
    """AsyncMock httpx.AsyncClient for inter-service calls."""
    client = AsyncMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {}
    response.raise_for_status = MagicMock()
    client.get = AsyncMock(return_value=response)
    client.post = AsyncMock(return_value=response)
    client.put = AsyncMock(return_value=response)
    client.delete = AsyncMock(return_value=response)
    client.request = AsyncMock(return_value=response)
    return client


# ── Auth helper ──────────────────────────────────────────────────

@pytest.fixture
def auth_headers():
    """Factory that returns Authorization headers for a given role."""
    from shared.auth import create_access_token

    def _make(role="passenger", sub=None, username="testuser"):
        user_id = sub or str(uuid.uuid4())
        token = create_access_token({
            "sub": user_id,
            "username": username,
            "role": role,
        })
        return {"Authorization": f"Bearer {token}"}

    return _make


# ── Sample model factories ───────────────────────────────────────

@pytest.fixture
def sample_user():
    """Factory returning a mock User DB model object."""
    def _make(**overrides):
        user = MagicMock()
        user.id = overrides.get("id", uuid.uuid4())
        user.email = overrides.get("email", "test@aerolink.com")
        user.username = overrides.get("username", "testuser")
        user.hashed_password = overrides.get("hashed_password", "$2b$12$fakehash")
        user.full_name = overrides.get("full_name", "Test User")

        # Use a mock for role that behaves like UserRole enum
        role_val = overrides.get("role", "passenger")
        role_mock = MagicMock()
        role_mock.value = role_val
        role_mock.__eq__ = lambda s, o: s.value == (o.value if hasattr(o, 'value') else o)
        user.role = role_mock

        user.is_active = overrides.get("is_active", True)
        user.created_at = overrides.get("created_at", datetime.now(timezone.utc))
        return user
    return _make


@pytest.fixture
def sample_flight():
    """Factory returning a mock Flight DB model object."""
    def _make(**overrides):
        flight = MagicMock()
        flight.id = overrides.get("id", uuid.uuid4())
        flight.flight_number = overrides.get("flight_number", "AL100")
        flight.airline = overrides.get("airline", "AeroLink")
        flight.origin = overrides.get("origin", "DUB")
        flight.destination = overrides.get("destination", "LHR")
        flight.departure_date = overrides.get("departure_date", datetime.now(timezone.utc).date())
        flight.departure_time = overrides.get("departure_time", datetime.now(timezone.utc).time())
        flight.arrival_date = overrides.get("arrival_date", datetime.now(timezone.utc).date())
        flight.arrival_time = overrides.get("arrival_time", datetime.now(timezone.utc).time())

        status_mock = MagicMock()
        status_mock.value = overrides.get("status", "scheduled")
        flight.status = status_mock

        flight.aircraft_type = overrides.get("aircraft_type", "A320")
        flight.available_seats_economy = overrides.get("available_seats_economy", 150)
        flight.available_seats_business = overrides.get("available_seats_business", 30)
        flight.available_seats_first = overrides.get("available_seats_first", 10)
        flight.total_seats_economy = overrides.get("total_seats_economy", 150)
        flight.total_seats_business = overrides.get("total_seats_business", 30)
        flight.total_seats_first = overrides.get("total_seats_first", 10)
        flight.price_economy = overrides.get("price_economy", 199.99)
        flight.price_business = overrides.get("price_business", 599.99)
        flight.price_first = overrides.get("price_first", 1299.99)
        flight.gate = overrides.get("gate", "A1")
        flight.terminal = overrides.get("terminal", "T1")
        flight.version = overrides.get("version", 1)
        flight.created_at = overrides.get("created_at", datetime.now(timezone.utc))
        return flight
    return _make


@pytest.fixture
def sample_booking():
    """Factory returning a mock Booking DB model object."""
    def _make(**overrides):
        booking = MagicMock()
        booking.id = overrides.get("id", uuid.uuid4())
        booking.booking_reference = overrides.get("booking_reference", "AL1ABC23")
        booking.user_id = overrides.get("user_id", uuid.uuid4())
        booking.flight_id = overrides.get("flight_id", uuid.uuid4())
        booking.passenger_name = overrides.get("passenger_name", "John Doe")
        booking.passenger_email = overrides.get("passenger_email", "john@example.com")
        booking.cabin_class = overrides.get("cabin_class", "economy")
        booking.num_passengers = overrides.get("num_passengers", 1)
        booking.total_price = overrides.get("total_price", 199.99)

        status_mock = MagicMock()
        status_mock.value = overrides.get("status", "pending")
        booking.status = status_mock

        booking.payment_id = overrides.get("payment_id", None)
        booking.seat_numbers = overrides.get("seat_numbers", None)
        booking.special_requests = overrides.get("special_requests", None)
        booking.trip_type = overrides.get("trip_type", "one_way")
        booking.group_booking_id = overrides.get("group_booking_id", None)
        booking.title = overrides.get("title", None)
        booking.gender = overrides.get("gender", None)
        booking.first_name = overrides.get("first_name", None)
        booking.middle_name = overrides.get("middle_name", None)
        booking.last_name = overrides.get("last_name", None)
        booking.date_of_birth = overrides.get("date_of_birth", None)
        booking.nationality = overrides.get("nationality", None)
        booking.passport_number = overrides.get("passport_number", None)
        booking.passport_expiry = overrides.get("passport_expiry", None)
        booking.country_code = overrides.get("country_code", None)
        booking.phone_number = overrides.get("phone_number", None)
        booking.created_at = overrides.get("created_at", datetime.now(timezone.utc))
        return booking
    return _make


@pytest.fixture
def sample_payment():
    """Factory returning a mock Payment DB model object (Stripe-based)."""
    def _make(**overrides):
        payment = MagicMock()
        payment.id = overrides.get("id", uuid.uuid4())
        payment.booking_id = overrides.get("booking_id", uuid.uuid4())
        payment.user_id = overrides.get("user_id", uuid.uuid4())
        payment.amount = overrides.get("amount", 199.99)
        payment.currency = overrides.get("currency", "EUR")

        status_mock = MagicMock()
        status_mock.value = overrides.get("status", "completed")
        payment.status = status_mock

        payment.provider = overrides.get("provider", "stripe")
        payment.idempotency_key = overrides.get("idempotency_key", str(uuid.uuid4()))
        payment.transaction_ref = overrides.get("transaction_ref", "TXN-ABC123")
        payment.failure_reason = overrides.get("failure_reason", None)
        payment.stripe_payment_intent_id = overrides.get("stripe_payment_intent_id", None)
        payment.payment_method_type = overrides.get("payment_method_type", None)
        payment.wallet_brand = overrides.get("wallet_brand", None)
        payment.last_four = overrides.get("last_four", None)
        payment.created_at = overrides.get("created_at", datetime.now(timezone.utc))
        return payment
    return _make
