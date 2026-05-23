"""Tests for shared/auth.py — JWT, password hashing, RBAC."""
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from jose import jwt

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
    with pytest.raises(HTTPException) as exc_info:
        decode_token(token, secret="wrong-secret")
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
