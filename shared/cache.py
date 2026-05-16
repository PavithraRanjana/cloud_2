import json
import redis
import structlog

logger = structlog.get_logger()


def create_redis_client(redis_url: str):
    """
    Create a Redis client. Returns None on failure so callers degrade gracefully.
    Works with local Redis and AWS ElastiCache (non-cluster replication group).
    socket_timeout prevents blocking the event loop on a dead node.
    """
    try:
        client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
            retry_on_timeout=False,
        )
        client.ping()
        logger.info("redis_connected", url=redis_url)
        return client
    except Exception as e:
        logger.warning("redis_unavailable", error=str(e))
        return None


def redis_get_json(client, key: str):
    """Return a JSON-decoded value, or None if missing/unavailable."""
    if not client:
        return None
    try:
        raw = client.get(key)
        return json.loads(raw) if raw is not None else None
    except Exception:
        return None


def redis_set_json(client, key: str, value, ttl: int):
    """JSON-encode and store a value with a TTL (seconds). Silent no-op if unavailable."""
    if not client:
        return
    try:
        client.setex(key, ttl, json.dumps(value, default=str))
    except Exception:
        pass


def redis_delete(client, *keys):
    """Delete one or more keys. Silent no-op if unavailable."""
    if not client or not keys:
        return
    try:
        client.delete(*keys)
    except Exception:
        pass


def redis_set_nx(client, key: str, value: str, ttl: int) -> bool:
    """
    SET if Not eXists with TTL. Returns True if the key was set (lock acquired),
    False if it already existed (lock held by another).
    Falls back to True (allow) when Redis is unavailable so operations are never
    permanently blocked by a cache outage.
    """
    if not client:
        return True
    try:
        result = client.set(key, value, nx=True, ex=ttl)
        return result is not None
    except Exception:
        return True


def redis_incr_with_ttl(client, key: str, ttl: int) -> int:
    """
    Increment a counter and set TTL on first write.
    Returns the new counter value, or 0 if Redis is unavailable.
    """
    if not client:
        return 0
    try:
        count = client.incr(key)
        if count == 1:
            client.expire(key, ttl)
        return count
    except Exception:
        return 0
