"""Tests for services/auth-service/main.py."""
import sys
import os
import uuid
import importlib.util
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.database import Base

# Pre-mock boto3 to prevent potential hang from transitive imports
_mock_boto3 = MagicMock()
sys.modules.setdefault("boto3", _mock_boto3)


@pytest.fixture
def client(mock_db_session):
    """TestClient with mocked DB."""
    svc_path = os.path.join(os.path.dirname(__file__), "..", "services", "auth-service")
    sys.path.insert(0, svc_path)
    Base.metadata.clear()
    for mod_name in ["models", "schemas"]:
        sys.modules.pop(mod_name, None)

    mock_engine = MagicMock()
    mock_engine.begin.return_value = AsyncMock()
    mock_engine.dispose = AsyncMock()

    spec = importlib.util.spec_from_file_location(
        "auth_main", os.path.join(svc_path, "main.py"))
    mod = importlib.util.module_from_spec(spec)
    with patch("shared.database.create_db_engine", return_value=mock_engine), \
         patch("shared.database.create_session_factory"), \
         patch("shared.logging.setup_logging"):
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


# ── Register ─────────────────────────────────────────────────────

def test_register_success(client):
    c, db_session, mod = client

    # Mock: no existing user
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db_session.execute.return_value = result_mock

    # After flush/refresh, mock the user object
    def fake_refresh(user):
        user.id = uuid.uuid4()
        user.created_at = MagicMock()
        user.created_at.isoformat = MagicMock(return_value="2025-01-01T00:00:00")
        user.role = MagicMock(value="passenger")
        user.is_active = True
        user.airport_code = None
        user.airline_code = None
        user.api_key = None

    db_session.refresh = AsyncMock(side_effect=fake_refresh)

    resp = c.post("/api/v1/auth/register", json={
        "email": "new@aerolink.com",
        "username": "newuser",
        "password": "StrongPass1",
        "full_name": "New User",
    })
    assert resp.status_code == 201
    assert resp.json()["email"] == "new@aerolink.com"


def test_register_duplicate_email(client):
    c, db_session, mod = client
    existing_user = MagicMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = existing_user
    db_session.execute.return_value = result_mock

    resp = c.post("/api/v1/auth/register", json={
        "email": "dup@aerolink.com",
        "username": "dupuser",
        "password": "StrongPass1",
        "full_name": "Dup User",
    })
    assert resp.status_code == 409


def test_register_duplicate_username(client):
    c, db_session, mod = client
    existing = MagicMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = existing
    db_session.execute.return_value = result_mock

    resp = c.post("/api/v1/auth/register", json={
        "email": "unique@example.com",
        "username": "existinguser",
        "password": "StrongPass1",
        "full_name": "Dup User",
    })
    assert resp.status_code == 409


def test_register_default_role_passenger(client):
    c, db_session, mod = client
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db_session.execute.return_value = result_mock

    def fake_refresh(user):
        user.id = uuid.uuid4()
        user.created_at = MagicMock()
        user.role = MagicMock(value="passenger")
        user.is_active = True
        user.airport_code = None
        user.airline_code = None
        user.api_key = None

    db_session.refresh = AsyncMock(side_effect=fake_refresh)

    resp = c.post("/api/v1/auth/register", json={
        "email": "def@test.com",
        "username": "defuser",
        "password": "StrongPass1",
        "full_name": "Default Role",
    })
    assert resp.status_code == 201
    assert resp.json()["role"] == "passenger"


# ── Login ────────────────────────────────────────────────────────

def test_login_success_returns_tokens(client, sample_user):
    c, db_session, mod = client
    from shared.auth import hash_password
    user = sample_user(hashed_password=hash_password("CorrectPass1"))
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = user
    db_session.execute.return_value = result_mock

    resp = c.post("/api/v1/auth/login", json={
        "username": "testuser",
        "password": "CorrectPass1",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body


def test_login_wrong_password(client, sample_user):
    c, db_session, mod = client
    from shared.auth import hash_password
    user = sample_user(hashed_password=hash_password("CorrectPass1"))
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = user
    db_session.execute.return_value = result_mock

    resp = c.post("/api/v1/auth/login", json={
        "username": "testuser",
        "password": "WrongPass",
    })
    assert resp.status_code == 401


def test_login_nonexistent_user(client):
    c, db_session, mod = client
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db_session.execute.return_value = result_mock

    resp = c.post("/api/v1/auth/login", json={
        "username": "ghost",
        "password": "whatever",
    })
    assert resp.status_code == 401


def test_login_inactive_user(client, sample_user):
    c, db_session, mod = client
    from shared.auth import hash_password
    user = sample_user(hashed_password=hash_password("Pass1234"), is_active=False)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = user
    db_session.execute.return_value = result_mock

    resp = c.post("/api/v1/auth/login", json={
        "username": "testuser",
        "password": "Pass1234",
    })
    assert resp.status_code == 403


# ── Refresh ──────────────────────────────────────────────────────

def test_refresh_valid_token(client):
    c, db_session, mod = client
    from shared.auth import create_refresh_token
    token = create_refresh_token({
        "sub": str(uuid.uuid4()),
        "username": "testuser",
        "role": "passenger",
        "airport_code": None,
        "airline_code": None,
    })

    resp = c.post("/api/v1/auth/refresh", json={"refresh_token": token})
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body


def test_refresh_access_token_rejected(client):
    c, db_session, mod = client
    from shared.auth import create_access_token
    token = create_access_token({
        "sub": str(uuid.uuid4()),
        "username": "testuser",
        "role": "passenger",
    })

    resp = c.post("/api/v1/auth/refresh", json={"refresh_token": token})
    assert resp.status_code == 401




# ── Health ───────────────────────────────────────────────────────

def test_health_endpoint(client):
    c, db_session, mod = client
    resp = c.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "auth-service"
    assert "uptime_seconds" in body


# ── GET /auth/me ─────────────────────────────────────────────────

def test_get_me_success(client, auth_headers, sample_user):
    c, db_session, mod = client
    headers = auth_headers()
    user = sample_user()

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = user
    db_session.execute.return_value = result_mock

    resp = c.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "email" in body
    assert "username" in body


def test_get_me_user_not_found(client, auth_headers):
    c, db_session, mod = client
    headers = auth_headers()

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db_session.execute.return_value = result_mock

    resp = c.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 404


def test_get_me_unauthenticated(client):
    c, db_session, mod = client
    resp = c.get("/api/v1/auth/me")
    assert resp.status_code == 401


# ── GET /auth/validate ───────────────────────────────────────────

def test_validate_token_returns_claims(client, auth_headers):
    c, db_session, mod = client
    headers = auth_headers(role="admin")

    resp = c.get("/api/v1/auth/validate", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["role"] == "admin"


def test_validate_token_unauthenticated(client):
    c, db_session, mod = client
    resp = c.get("/api/v1/auth/validate")
    assert resp.status_code == 401


# ── Validation (422) ─────────────────────────────────────────────

def test_register_missing_email_returns_422(client):
    c, db_session, mod = client
    resp = c.post("/api/v1/auth/register", json={
        "username": "nomail",
        "password": "StrongPass1",
        "full_name": "No Mail",
        # email omitted
    })
    assert resp.status_code == 422


def test_login_missing_password_returns_422(client):
    c, db_session, mod = client
    resp = c.post("/api/v1/auth/login", json={"username": "user"})
    assert resp.status_code == 422


