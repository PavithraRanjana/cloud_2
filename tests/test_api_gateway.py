"""Tests for api-gateway/main.py."""
import sys
import os
import time
import importlib.util
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.database import Base


@pytest.fixture
def gw_app():
    svc_path = os.path.join(os.path.dirname(__file__), "..", "api-gateway")
    sys.path.insert(0, svc_path)
    Base.metadata.clear()
    for mod_name in ["models", "schemas"]:
        sys.modules.pop(mod_name, None)

    spec = importlib.util.spec_from_file_location(
        "gw_main", os.path.join(svc_path, "main.py"))
    mod = importlib.util.module_from_spec(spec)
    with patch("shared.logging.setup_logging"):
        spec.loader.exec_module(mod)

    with TestClient(mod.app, raise_server_exceptions=False) as c:
        yield c, mod
    for mod_name in ["models", "schemas"]:
        sys.modules.pop(mod_name, None)
    if svc_path in sys.path:
        sys.path.remove(svc_path)


# ── is_public_path ───────────────────────────────────────────────

def test_is_public_path_auth_endpoints(gw_app):
    c, mod = gw_app
    assert mod.is_public_path("/api/v1/auth/register") is True
    assert mod.is_public_path("/api/v1/auth/login") is True
    assert mod.is_public_path("/api/v1/auth/refresh") is True


def test_is_public_path_flights_search(gw_app):
    c, mod = gw_app
    assert mod.is_public_path("/api/v1/flights") is True
    assert mod.is_public_path("/api/v1/flights?origin=DUB") is True


def test_is_public_path_health(gw_app):
    c, mod = gw_app
    assert mod.is_public_path("/health") is True


def test_is_private_path_bookings(gw_app):
    c, mod = gw_app
    assert mod.is_public_path("/api/v1/bookings") is False
    assert mod.is_public_path("/api/v1/payments") is False


# ── resolve_service ──────────────────────────────────────────────

def test_resolve_service_booking(gw_app):
    c, mod = gw_app
    url = mod.resolve_service("/api/v1/bookings/123")
    assert url is not None
    assert "8003" in url


def test_resolve_service_unknown_returns_none(gw_app):
    c, mod = gw_app
    assert mod.resolve_service("/api/v1/unknown/path") is None


# ── Proxy behaviour ──────────────────────────────────────────────

def test_proxy_public_path_no_auth_needed(gw_app, auth_headers):
    c, mod = gw_app

    mock_resp = MagicMock()
    mock_resp.content = b'{"status":"ok"}'
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/json"}

    with patch("httpx.AsyncClient") as mock_httpx:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client

        resp = c.get("/api/v1/auth/login")
    assert resp.status_code == 200


def test_proxy_protected_path_requires_auth(gw_app):
    c, mod = gw_app
    # No auth header → 401
    resp = c.get("/api/v1/bookings")
    assert resp.status_code == 401


def test_proxy_service_unavailable_503(gw_app, auth_headers):
    c, mod = gw_app
    from shared.auth import create_access_token
    token = create_access_token({"sub": "u1", "role": "passenger"})
    headers = {"Authorization": f"Bearer {token}"}

    with patch("httpx.AsyncClient") as mock_httpx:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client

        resp = c.get("/api/v1/bookings", headers=headers)
    assert resp.status_code == 503
