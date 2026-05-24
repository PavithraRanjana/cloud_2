"""Tests for services/passenger-service/main.py."""
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

# Pre-mock boto3 to prevent potential hang from transitive imports
_mock_boto3 = MagicMock()
sys.modules.setdefault("boto3", _mock_boto3)


@pytest.fixture
def passenger_app(mock_db_session, auth_headers):
    svc_path = os.path.join(os.path.dirname(__file__), "..", "services", "passenger-service")
    sys.path.insert(0, svc_path)
    Base.metadata.clear()
    for mod_name in ["models", "schemas"]:
        sys.modules.pop(mod_name, None)

    mock_engine = MagicMock()
    mock_engine.begin.return_value = AsyncMock()
    mock_engine.dispose = AsyncMock()

    spec = importlib.util.spec_from_file_location(
        "passenger_main", os.path.join(svc_path, "main.py"))
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


def _make_profile(**overrides):
    p = MagicMock()
    p.id = overrides.get("id", uuid.uuid4())
    p.user_id = overrides.get("user_id", uuid.uuid4())
    p.title = overrides.get("title", None)
    p.gender = overrides.get("gender", None)
    p.first_name = overrides.get("first_name", "John")
    p.middle_name = overrides.get("middle_name", None)
    p.last_name = overrides.get("last_name", "Doe")
    p.date_of_birth = overrides.get("date_of_birth", None)
    p.nationality = overrides.get("nationality", "IE")
    p.passport_number_encrypted = overrides.get("passport_number_encrypted", None)
    p.passport_expiry = overrides.get("passport_expiry", None)
    p.phone_number = overrides.get("phone_number", "+353851234567")
    p.loyalty_tier = overrides.get("loyalty_tier", "bronze")
    p.loyalty_points = overrides.get("loyalty_points", 0)
    p.meal_preference = overrides.get("meal_preference", None)
    p.seat_preference = overrides.get("seat_preference", None)
    p.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    return p


# ── Create Profile ───────────────────────────────────────────────

def test_create_profile_encrypts_passport(passenger_app, auth_headers):
    c, db, mod = passenger_app
    headers = auth_headers()

    no_existing = MagicMock()
    no_existing.scalar_one_or_none.return_value = None
    db.execute.return_value = no_existing

    captured = {}
    orig_add = db.add

    def capture_add(obj):
        captured["profile"] = obj
        return orig_add(obj)

    db.add = capture_add

    from shared.encryption import encrypt_field
    encrypted_passport = encrypt_field("AB1234567")

    def fake_refresh(obj):
        obj.id = uuid.uuid4()
        obj.user_id = uuid.uuid4()
        obj.first_name = "John"
        obj.last_name = "Doe"
        obj.date_of_birth = None
        obj.nationality = "IE"
        obj.passport_number_encrypted = encrypted_passport
        obj.phone_number = "+353851234567"
        obj.loyalty_tier = "bronze"
        obj.loyalty_points = 0
        obj.meal_preference = None
        obj.seat_preference = None
        obj.created_at = datetime.now(timezone.utc)

    db.refresh = AsyncMock(side_effect=fake_refresh)

    resp = c.post("/api/v1/passengers/profile", headers=headers, json={
        "first_name": "John",
        "last_name": "Doe",
        "nationality": "IE",
        "passport_number": "AB1234567",
        "phone_number": "+353851234567",
    })
    assert resp.status_code == 201
    # The stored profile should have encrypted passport, not plaintext
    if "profile" in captured:
        assert captured["profile"].passport_number_encrypted is not None
        assert captured["profile"].passport_number_encrypted != "AB1234567"


def test_create_profile_duplicate_rejected(passenger_app, auth_headers):
    c, db, mod = passenger_app
    headers = auth_headers()

    existing = MagicMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = existing
    db.execute.return_value = result_mock

    resp = c.post("/api/v1/passengers/profile", headers=headers, json={
        "first_name": "Dup",
        "last_name": "User",
    })
    assert resp.status_code == 409


# ── Get Profile ──────────────────────────────────────────────────

def test_get_profile_decrypts_passport(passenger_app, auth_headers):
    c, db, mod = passenger_app
    headers = auth_headers()

    from shared.encryption import encrypt_field
    enc = encrypt_field("XY9876543")

    profile = _make_profile(passport_number_encrypted=enc)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = profile
    db.execute.return_value = result_mock

    resp = c.get("/api/v1/passengers/profile", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["passport_number"] == "XY9876543"


def test_get_profile_decryption_error_masked(passenger_app, auth_headers):
    c, db, mod = passenger_app
    headers = auth_headers()

    profile = _make_profile(passport_number_encrypted="invalid-ciphertext")
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = profile
    db.execute.return_value = result_mock

    resp = c.get("/api/v1/passengers/profile", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["passport_number"] == "***ENCRYPTED***"


# ── Update Profile ───────────────────────────────────────────────

def test_update_profile_partial_fields(passenger_app, auth_headers):
    c, db, mod = passenger_app
    headers = auth_headers()

    profile = _make_profile()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = profile
    db.execute.return_value = result_mock
    db.refresh = AsyncMock(side_effect=lambda obj: None)

    resp = c.put("/api/v1/passengers/profile", headers=headers, json={
        "meal_preference": "vegetarian",
    })
    assert resp.status_code == 200


def test_update_profile_re_encrypts_passport(passenger_app, auth_headers):
    c, db, mod = passenger_app
    headers = auth_headers()

    from shared.encryption import encrypt_field
    original_enc = encrypt_field("OLD123")

    profile = _make_profile(passport_number_encrypted=original_enc)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = profile
    db.execute.return_value = result_mock
    db.refresh = AsyncMock(side_effect=lambda obj: None)

    resp = c.put("/api/v1/passengers/profile", headers=headers, json={
        "passport_number": "NEW456",
    })
    assert resp.status_code == 200
    # After update, the encrypted passport should differ from original
    assert profile.passport_number_encrypted != original_enc


# ── Delete Profile (GDPR) ───────────────────────────────────────

def test_delete_profile_gdpr_erasure(passenger_app, auth_headers):
    c, db, mod = passenger_app
    headers = auth_headers()

    profile = _make_profile()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = profile

    consents_mock = MagicMock()
    consents_mock.scalars.return_value.all.return_value = []

    db.execute.side_effect = [result_mock, consents_mock]

    with patch("httpx.AsyncClient") as mock_httpx, \
         patch.object(mod, "record_audit", new_callable=AsyncMock):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client

        resp = c.delete("/api/v1/passengers/profile", headers=headers)
    assert resp.status_code == 204


def test_delete_profile_audit_logged(passenger_app, auth_headers):
    c, db, mod = passenger_app
    headers = auth_headers()

    profile = _make_profile()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = profile

    consents_mock = MagicMock()
    consents_mock.scalars.return_value.all.return_value = []

    db.execute.side_effect = [result_mock, consents_mock]

    with patch("httpx.AsyncClient") as mock_httpx, \
         patch.object(mod, "record_audit", new_callable=AsyncMock) as mock_audit:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client

        c.delete("/api/v1/passengers/profile", headers=headers)
    mock_audit.assert_called_once()
    assert "gdpr.erasure" in mock_audit.call_args[0]


def test_delete_profile_cascades_to_services(passenger_app, auth_headers):
    c, db, mod = passenger_app
    headers = auth_headers()

    profile = _make_profile()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = profile

    consents_mock = MagicMock()
    consents_mock.scalars.return_value.all.return_value = []

    db.execute.side_effect = [result_mock, consents_mock]

    with patch("httpx.AsyncClient") as mock_httpx, \
         patch.object(mod, "record_audit", new_callable=AsyncMock):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client

        c.delete("/api/v1/passengers/profile", headers=headers)
    # Should have called cascade POST to other services
    assert mock_client.post.call_count >= 1


# ── GDPR Consent ─────────────────────────────────────────────────

def test_grant_consent_new(passenger_app, auth_headers):
    c, db, mod = passenger_app
    headers = auth_headers()

    no_existing = MagicMock()
    no_existing.scalar_one_or_none.return_value = None
    db.execute.return_value = no_existing

    def fake_refresh(obj):
        obj.id = uuid.uuid4()
        obj.user_id = uuid.uuid4()
        obj.purpose = "marketing"
        obj.granted = True
        obj.granted_at = datetime.now(timezone.utc)
        obj.revoked_at = None
        obj.created_at = datetime.now(timezone.utc)

    db.refresh = AsyncMock(side_effect=fake_refresh)

    with patch.object(mod, "record_audit", new_callable=AsyncMock):
        resp = c.post("/api/v1/passengers/consent", headers=headers, json={
            "purpose": "marketing",
            "granted": True,
        })
    assert resp.status_code == 201
    assert resp.json()["granted"] is True


def test_grant_consent_revoke(passenger_app, auth_headers):
    c, db, mod = passenger_app
    headers = auth_headers()

    existing_consent = MagicMock()
    existing_consent.id = uuid.uuid4()
    existing_consent.user_id = uuid.uuid4()
    existing_consent.purpose = "marketing"
    existing_consent.granted = True
    existing_consent.granted_at = datetime.now(timezone.utc)
    existing_consent.revoked_at = None
    existing_consent.created_at = datetime.now(timezone.utc)

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = existing_consent
    db.execute.return_value = result_mock
    db.refresh = AsyncMock(side_effect=lambda obj: None)

    with patch.object(mod, "record_audit", new_callable=AsyncMock):
        resp = c.post("/api/v1/passengers/consent", headers=headers, json={
            "purpose": "marketing",
            "granted": False,
        })
    assert resp.status_code == 201
    # The consent should now be revoked
    assert existing_consent.granted is False


def test_list_consents(passenger_app, auth_headers):
    c, db, mod = passenger_app
    headers = auth_headers()

    consent = MagicMock()
    consent.id = uuid.uuid4()
    consent.user_id = uuid.uuid4()
    consent.purpose = "analytics"
    consent.granted = True
    consent.granted_at = datetime.now(timezone.utc)
    consent.revoked_at = None
    consent.created_at = datetime.now(timezone.utc)

    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [consent]
    db.execute.return_value = result_mock

    resp = c.get("/api/v1/passengers/consent", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) == 1


# ── Health ───────────────────────────────────────────────────────

def test_health_endpoint(passenger_app):
    c, db, mod = passenger_app
    resp = c.get("/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "passenger-service"


# ── 404 paths ────────────────────────────────────────────────────

def test_get_profile_not_found(passenger_app, auth_headers):
    c, db, mod = passenger_app
    headers = auth_headers()

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    resp = c.get("/api/v1/passengers/profile", headers=headers)
    assert resp.status_code == 404


def test_update_profile_not_found(passenger_app, auth_headers):
    c, db, mod = passenger_app
    headers = auth_headers()

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    resp = c.put("/api/v1/passengers/profile", headers=headers, json={"meal_preference": "vegan"})
    assert resp.status_code == 404


def test_delete_profile_not_found(passenger_app, auth_headers):
    c, db, mod = passenger_app
    headers = auth_headers()

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    resp = c.delete("/api/v1/passengers/profile", headers=headers)
    assert resp.status_code == 404


# ── Unauthenticated access ────────────────────────────────────────

def test_get_profile_unauthenticated(passenger_app):
    c, db, mod = passenger_app
    resp = c.get("/api/v1/passengers/profile")
    assert resp.status_code == 401


# ── Validation (422) ─────────────────────────────────────────────

def test_create_profile_missing_required_fields_422(passenger_app, auth_headers):
    c, db, mod = passenger_app
    headers = auth_headers()
    resp = c.post("/api/v1/passengers/profile", headers=headers, json={
        "first_name": "Alice"
        # last_name required but omitted
    })
    assert resp.status_code == 422


def test_grant_consent_missing_required_field_422(passenger_app, auth_headers):
    c, db, mod = passenger_app
    headers = auth_headers()
    resp = c.post("/api/v1/passengers/consent", headers=headers, json={
        "purpose": "marketing"
        # granted required but omitted
    })
    assert resp.status_code == 422
