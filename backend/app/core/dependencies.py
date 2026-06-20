"""FastAPI dependency providers — singleton engine, Redis pool, DB sessions."""
import logging
from fastapi import Request
import redis.asyncio as aioredis

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def get_analytics_engine(request: Request):
    """Returns the singleton AnalyticsEngine from app state. Must be initialized in lifespan."""
    engine = getattr(request.app.state, "engine", None)
    if engine is None:
        raise RuntimeError("AnalyticsEngine not initialized. Check lifespan startup.")
    return engine


def get_redis_pool(request: Request):
    """Returns the shared Redis connection pool from app state."""
    pool = getattr(request.app.state, "redis_pool", None)
    if pool is None:
        raise RuntimeError("Redis pool not initialized. Check lifespan startup.")
    return pool


async def get_redis_client(request: Request):
    """Yields an async Redis client using the shared pool."""
    pool = get_redis_pool(request)
    client = aioredis.Redis(connection_pool=pool, decode_responses=True)
    try:
        yield client
    finally:
        await client.close()
