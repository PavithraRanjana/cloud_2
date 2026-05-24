"""Tests for lambdas/pricing_recalculation/handler.py."""
import sys
import os
import json
import importlib.util
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# pg8000 and psycopg2 are not installed; mock both before loading the handler module
_mock_psycopg2 = MagicMock()
sys.modules["psycopg2"] = _mock_psycopg2
_mock_pg8000 = MagicMock()
_mock_pg8000_dbapi = MagicMock()
sys.modules["pg8000"] = _mock_pg8000
sys.modules["pg8000.dbapi"] = _mock_pg8000_dbapi

# Use importlib to load the specific handler file to avoid name collisions
_handler_path = os.path.join(
    os.path.dirname(__file__), "..", "..", "lambdas", "pricing_recalculation", "handler.py"
)
_spec = importlib.util.spec_from_file_location("pricing_handler", _handler_path)
pricing_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pricing_mod)

_clamp = pricing_mod._clamp
_adjust_price = pricing_mod._adjust_price
handler = pricing_mod.handler
PRICE_BOUNDS = pricing_mod.PRICE_BOUNDS


# ── _clamp ───────────────────────────────────────────────────────

def test_clamp_within_range():
    assert _clamp(50.0, 10.0, 100.0) == 50.0


def test_clamp_below_min():
    assert _clamp(5.0, 10.0, 100.0) == 10.0


def test_clamp_above_max():
    assert _clamp(150.0, 10.0, 100.0) == 100.0


# ── _adjust_price ────────────────────────────────────────────────

def test_adjust_price_high_demand_increase():
    result = _adjust_price(100.0, available=10, total=100, seat_class="economy")
    assert result > 100.0
    assert result == round(100.0 * 1.15, 2)


def test_adjust_price_low_demand_decrease():
    result = _adjust_price(200.0, available=90, total=100, seat_class="economy")
    assert result < 200.0
    assert result == round(200.0 * 0.90, 2)


def test_adjust_price_mid_range_no_change():
    result = _adjust_price(300.0, available=50, total=100, seat_class="economy")
    assert result == 300.0


def test_adjust_price_clamped_to_max():
    result = _adjust_price(990.0, available=5, total=100, seat_class="economy")
    assert result == PRICE_BOUNDS["economy"]["max"]


def test_adjust_price_clamped_to_min():
    result = _adjust_price(52.0, available=90, total=100, seat_class="economy")
    assert result == PRICE_BOUNDS["economy"]["min"]


def test_adjust_price_zero_total_seats():
    result = _adjust_price(100.0, available=0, total=0, seat_class="economy")
    assert result == 100.0


# ── handler ──────────────────────────────────────────────────────

def test_handler_updates_flight_prices():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchall.return_value = [
        ("id-1", "AL100",
         100, 10, 200.0,
         30, 5, 500.0,
         10, 1, 1000.0),
    ]
    with patch.object(pricing_mod, "pg8000") as mock_pg8000:
        mock_pg8000.connect.return_value = mock_conn
        result = handler({}, None)
    body = json.loads(result["body"])
    assert body["evaluated"] == 1
    assert body["updated"] == 1
    mock_conn.commit.assert_called_once()


def test_handler_no_scheduled_flights():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchall.return_value = []
    with patch.object(pricing_mod, "pg8000") as mock_pg8000:
        mock_pg8000.connect.return_value = mock_conn
        result = handler({}, None)
    body = json.loads(result["body"])
    assert body["evaluated"] == 0
    assert body["updated"] == 0


def test_handler_rolls_back_on_error():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchall.side_effect = Exception("DB error")
    with patch.object(pricing_mod, "pg8000") as mock_pg8000:
        mock_pg8000.connect.return_value = mock_conn
        try:
            handler({}, None)
        except Exception:
            pass
    mock_conn.rollback.assert_called_once()
