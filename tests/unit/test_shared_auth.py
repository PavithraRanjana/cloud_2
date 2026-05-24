"""Tests for shared/auth.py — JWT, password hashing, RBAC."""
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from jose import jwt

import shared.auth as auth_module
from shared.auth import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    decode_token, RoleChecker, get_current_user,
    DEFAULT_SECRET, DEFAULT_ALGORITHM,
)


# ── Password hashing ────────────────────────────────────────────

def test_hash_password_returns_bcrypt_hash():
    hashed = hash_password("TestPass123")
    assert hashed.startswith("$2b$")


def test_verify_password_correct():
    hashed = hash_password("MySecurePass")
    assert verify_password("MySecurePass", hashed) is True


def test_verify_password_incorrect():
    hashed = hash_password("MySecurePass")
    assert verify_password("WrongPass", hashed) is False


# ── Token creation ───────────────────────────────────────────────

def test_create_access_token_contains_claims():
    data = {"sub": "user-1", "role": "passenger"}
    token = create_access_token(data)
    payload = jwt.decode(token, DEFAULT_SECRET, algorithms=[DEFAULT_ALGORITHM])
    assert payload["sub"] == "user-1"
    assert payload["role"] == "passenger"
    assert payload["type"] == "access"


def test_create_access_token_expiry():
    token = create_access_token({"sub": "u1"}, expires_minutes=1)
    payload = jwt.decode(token, DEFAULT_SECRET, algorithms=[DEFAULT_ALGORITHM])
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    # exp should be within ~2 minutes from now
    assert exp > datetime.now(timezone.utc)
    assert exp < datetime.now(timezone.utc) + timedelta(minutes=2)


def test_create_refresh_token_type_claim():
    token = create_refresh_token({"sub": "u1"})
    payload = jwt.decode(token, DEFAULT_SECRET, algorithms=[DEFAULT_ALGORITHM])
    assert payload["type"] == "refresh"


# ── Token decoding ───────────────────────────────────────────────

def test_decode_token_valid():
    token = create_access_token({"sub": "u1", "role": "admin"})
    payload = decode_token(token)
    assert payload["sub"] == "u1"
    assert payload["role"] == "admin"


def test_decode_token_expired_raises():
    token = create_access_token({"sub": "u1"}, expires_minutes=-1)
    with pytest.raises(HTTPException) as exc_info:
        decode_token(token)
    assert exc_info.value.status_code == 401


def test_decode_token_invalid_signature_raises():
    token = create_access_token({"sub": "u1"})
    parts = token.split(".")
    tampered = ".".join(parts[:-1]) + ".invalidsignature"
    with pytest.raises(HTTPException) as exc_info:
        decode_token(tampered)
    assert exc_info.value.status_code == 401


def test_decode_token_malformed_raises():
    with pytest.raises(HTTPException) as exc_info:
        decode_token("not.a.valid.jwt")
    assert exc_info.value.status_code == 401


# ── RoleChecker ──────────────────────────────────────────────────

def test_role_checker_allows_matching_role():
    checker = RoleChecker(["admin"])
    token = create_access_token({"sub": "u1", "role": "admin"})
    creds = MagicMock()
    creds.credentials = token
    result = checker(creds)
    assert result["role"] == "admin"


def test_role_checker_rejects_missing_role():
    checker = RoleChecker(["admin"])
    token = create_access_token({"sub": "u1", "role": "passenger"})
    creds = MagicMock()
    creds.credentials = token
    with pytest.raises(HTTPException) as exc_info:
        checker(creds)
    assert exc_info.value.status_code == 403


def test_role_checker_allows_admin_always():
    """Admin should pass any role-checker that includes 'admin'."""
    checker = RoleChecker(["admin"])
    token = create_access_token({"sub": "u1", "role": "admin"})
    creds = MagicMock()
    creds.credentials = token
    result = checker(creds)
    assert result["sub"] == "u1"


# ── get_current_user ─────────────────────────────────────────────

def test_get_current_user_valid_token():
    token = create_access_token({"sub": "user-42", "role": "passenger"})
    creds = MagicMock()
    creds.credentials = token
    result = get_current_user(creds)
    assert result["sub"] == "user-42"


def test_get_current_user_missing_header():
    creds = MagicMock()
    creds.credentials = "bad-token"
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(creds)
    assert exc_info.value.status_code == 401


# ── Cognito helper functions ─────────────────────────────────────

def test_cognito_issuer_prod_format():
    with patch.object(auth_module, "_AWS_REGION", "eu-west-1"), \
         patch.object(auth_module, "_COGNITO_USER_POOL_ID", "eu-west-1_ABC"):
        result = auth_module._cognito_issuer_prod()
    assert result == "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_ABC"


def test_jwks_base_url_with_endpoint_url():
    with patch.object(auth_module, "_AWS_ENDPOINT_URL", "http://localhost:4566"), \
         patch.object(auth_module, "_COGNITO_USER_POOL_ID", "eu-west-1_POOL"):
        result = auth_module._jwks_base_url()
    assert result == "http://localhost:4566/eu-west-1_POOL"


def test_jwks_base_url_without_endpoint_url():
    with patch.object(auth_module, "_AWS_ENDPOINT_URL", ""), \
         patch.object(auth_module, "_AWS_REGION", "us-east-1"), \
         patch.object(auth_module, "_COGNITO_USER_POOL_ID", "us-east-1_XYZ"):
        result = auth_module._jwks_base_url()
    assert "us-east-1.amazonaws.com" in result
    assert "us-east-1_XYZ" in result


def test_fetch_jwks_returns_cached_when_fresh():
    original_cache = auth_module._jwks_cache
    original_time = auth_module._jwks_fetched_at
    try:
        auth_module._jwks_cache = {"kid-cached": {"kty": "RSA"}}
        auth_module._jwks_fetched_at = time.time()
        result = auth_module._fetch_jwks()
        assert "kid-cached" in result
    finally:
        auth_module._jwks_cache = original_cache
        auth_module._jwks_fetched_at = original_time


def test_fetch_jwks_refreshes_on_empty_cache():
    original_cache = auth_module._jwks_cache
    original_time = auth_module._jwks_fetched_at
    try:
        auth_module._jwks_cache = {}
        auth_module._jwks_fetched_at = 0.0
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"keys": [{"kid": "fresh-kid", "kty": "RSA"}]}
        with patch.object(auth_module, "_jwks_base_url", return_value="http://fake-jwks"), \
             patch("httpx.get", return_value=mock_resp):
            result = auth_module._fetch_jwks()
        assert "fresh-kid" in result
    finally:
        auth_module._jwks_cache = original_cache
        auth_module._jwks_fetched_at = original_time


# ── _claims_to_user ──────────────────────────────────────────────

def test_claims_to_user_with_groups_uses_first_group_as_role():
    claims = {
        "sub": "abc-123",
        "email": "user@example.com",
        "cognito:username": "testuser",
        "cognito:groups": ["admin", "passenger"],
        "name": "Test User",
    }
    user = auth_module._claims_to_user(claims, "raw_token")
    assert user["sub"] == "abc-123"
    assert user["role"] == "admin"
    assert user["groups"] == ["admin", "passenger"]
    assert user["full_name"] == "Test User"
    assert user["_token"] == "raw_token"


def test_claims_to_user_no_groups_defaults_to_passenger():
    claims = {
        "sub": "xyz",
        "email": "a@b.com",
        "cognito:username": "u1",
        "given_name": "First",
        "family_name": "Last",
    }
    user = auth_module._claims_to_user(claims, "tok")
    assert user["role"] == "passenger"
    assert user["full_name"] == "First Last"


def test_claims_to_user_sub_used_as_username_fallback():
    claims = {"sub": "sub-id-999"}
    user = auth_module._claims_to_user(claims, "t")
    assert user["username"] == "sub-id-999"


# ── _verify_cognito_token ────────────────────────────────────────

def test_verify_cognito_token_success():
    mock_claims = {
        "sub": "u-123", "email": "u@e.com",
        "cognito:username": "uname",
        "cognito:groups": ["passenger"],
        "iss": "https://cognito-idp.eu-west-1.amazonaws.com/pool",
    }
    with patch.object(auth_module, "_COGNITO_USER_POOL_ID", "eu-west-1_POOL"), \
         patch.object(auth_module, "_AWS_ENDPOINT_URL", ""), \
         patch.object(auth_module, "_fetch_jwks", return_value={"kid-1": {"kty": "RSA"}}), \
         patch.object(auth_module.jwt, "get_unverified_header",
                      return_value={"kid": "kid-1", "alg": "RS256"}), \
         patch.object(auth_module.jwt, "get_unverified_claims", return_value=mock_claims), \
         patch.object(auth_module.jwt, "decode", return_value=mock_claims):
        result = auth_module._verify_cognito_token("fake.jwt.token")
    assert result["sub"] == "u-123"


def test_verify_cognito_token_unknown_kid_raises_401():
    mock_claims = {"sub": "u1", "iss": "https://example.com/pool"}
    with patch.object(auth_module, "_COGNITO_USER_POOL_ID", "eu-west-1_POOL"), \
         patch.object(auth_module, "_AWS_ENDPOINT_URL", ""), \
         patch.object(auth_module, "_fetch_jwks", return_value={"other-kid": {}}), \
         patch.object(auth_module.jwt, "get_unverified_header",
                      return_value={"kid": "unknown-kid", "alg": "RS256"}), \
         patch.object(auth_module.jwt, "get_unverified_claims", return_value=mock_claims):
        with pytest.raises(HTTPException) as exc_info:
            auth_module._verify_cognito_token("fake.jwt.token")
    assert exc_info.value.status_code == 401


def test_decode_token_routes_to_cognito_when_pool_id_set():
    mock_user = {"sub": "u1", "role": "passenger", "email": "u@e.com",
                 "username": "u1", "full_name": "", "groups": []}
    with patch.object(auth_module, "_COGNITO_USER_POOL_ID", "eu-west-1_POOL"), \
         patch.object(auth_module, "_verify_cognito_token", return_value={}), \
         patch.object(auth_module, "_claims_to_user", return_value=mock_user):
        result = auth_module.decode_token("fake.token")
    assert result["sub"] == "u1"
