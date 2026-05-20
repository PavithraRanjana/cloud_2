"""
Shared helpers for health-check endpoints.
Returns real dependency status by probing each connection.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


async def check_db(db: AsyncSession) -> str:
    try:
        await db.execute(text("SELECT 1"))
        return "healthy"
    except Exception:
        return "unhealthy"


def check_redis(redis_client) -> str:
    if redis_client is None:
        return "unavailable"
    try:
        redis_client.ping()
        return "healthy"
    except Exception:
        return "unhealthy"
