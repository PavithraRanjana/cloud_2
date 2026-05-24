"""Tests for shared/cache.py — Redis helper functions."""
import sys
import os
import json
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.cache import (
    create_redis_client, redis_get_json, redis_set_json,
    redis_delete, redis_set_nx, redis_incr_with_ttl,
)


# ── create_redis_client ──────────────────────────────────────────

def test_create_redis_client_success():
    mock_client = MagicMock()
    with patch("redis.Redis.from_url", return_value=mock_client):
        result = create_redis_client("redis://localhost:6379/0")
    assert result is mock_client
    mock_client.ping.assert_called_once()


def test_create_redis_client_connection_failure_returns_none():
    with patch("redis.Redis.from_url", side_effect=Exception("Connection refused")):
        result = create_redis_client("redis://bad-host:9999/0")
    assert result is None


def test_create_redis_client_ping_failure_returns_none():
    mock_client = MagicMock()
    mock_client.ping.side_effect = Exception("ping failed")
    with patch("redis.Redis.from_url", return_value=mock_client):
        result = create_redis_client("redis://localhost:6379/0")
    assert result is None


# ── redis_get_json ───────────────────────────────────────────────

def test_redis_get_json_returns_none_when_client_is_none():
    assert redis_get_json(None, "any-key") is None


def test_redis_get_json_returns_parsed_dict():
    client = MagicMock()
    client.get.return_value = '{"x": 42, "y": "hello"}'
    result = redis_get_json(client, "k")
    assert result == {"x": 42, "y": "hello"}


def test_redis_get_json_returns_none_for_missing_key():
    client = MagicMock()
    client.get.return_value = None
    assert redis_get_json(client, "missing") is None


def test_redis_get_json_returns_none_on_exception():
    client = MagicMock()
    client.get.side_effect = Exception("redis timeout")
    assert redis_get_json(client, "k") is None


# ── redis_set_json ───────────────────────────────────────────────

def test_redis_set_json_noop_when_client_is_none():
    redis_set_json(None, "k", {"a": 1}, 60)  # must not raise


def test_redis_set_json_stores_with_ttl():
    client = MagicMock()
    redis_set_json(client, "my-key", {"a": 1}, 120)
    client.setex.assert_called_once_with("my-key", 120, '{"a": 1}')


def test_redis_set_json_silences_exception():
    client = MagicMock()
    client.setex.side_effect = Exception("write error")
    redis_set_json(client, "k", {}, 60)  # must not raise


# ── redis_delete ─────────────────────────────────────────────────

def test_redis_delete_noop_when_client_is_none():
    redis_delete(None, "k1", "k2")  # must not raise


def test_redis_delete_noop_when_no_keys_given():
    client = MagicMock()
    redis_delete(client)
    client.delete.assert_not_called()


def test_redis_delete_calls_client_with_all_keys():
    client = MagicMock()
    redis_delete(client, "k1", "k2", "k3")
    client.delete.assert_called_once_with("k1", "k2", "k3")


def test_redis_delete_silences_exception():
    client = MagicMock()
    client.delete.side_effect = Exception("network error")
    redis_delete(client, "k")  # must not raise


# ── redis_set_nx ─────────────────────────────────────────────────

def test_redis_set_nx_returns_true_when_client_is_none():
    assert redis_set_nx(None, "lock", "1", 60) is True


def test_redis_set_nx_returns_true_when_key_is_new():
    client = MagicMock()
    client.set.return_value = True  # SET NX succeeded
    assert redis_set_nx(client, "lock", "1", 30) is True
    client.set.assert_called_once_with("lock", "1", nx=True, ex=30)


def test_redis_set_nx_returns_false_when_key_already_exists():
    client = MagicMock()
    client.set.return_value = None  # SET NX failed — key exists
    assert redis_set_nx(client, "lock", "1", 30) is False


def test_redis_set_nx_returns_true_on_exception():
    client = MagicMock()
    client.set.side_effect = Exception("redis down")
    assert redis_set_nx(client, "lock", "1", 30) is True


# ── redis_incr_with_ttl ──────────────────────────────────────────

def test_redis_incr_with_ttl_returns_zero_when_client_is_none():
    assert redis_incr_with_ttl(None, "counter", 60) == 0


def test_redis_incr_with_ttl_sets_expire_on_first_increment():
    client = MagicMock()
    client.incr.return_value = 1
    count = redis_incr_with_ttl(client, "counter", 60)
    assert count == 1
    client.expire.assert_called_once_with("counter", 60)


def test_redis_incr_with_ttl_no_expire_on_subsequent_increments():
    client = MagicMock()
    client.incr.return_value = 5
    count = redis_incr_with_ttl(client, "counter", 60)
    assert count == 5
    client.expire.assert_not_called()


def test_redis_incr_with_ttl_returns_zero_on_exception():
    client = MagicMock()
    client.incr.side_effect = Exception("redis down")
    assert redis_incr_with_ttl(client, "counter", 60) == 0
