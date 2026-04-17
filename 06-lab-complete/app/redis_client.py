"""Shared Redis client — single connection for all modules."""
from app.config import settings

USE_REDIS = False
client = None

try:
    import redis
    if settings.redis_url:
        client = redis.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        USE_REDIS = True
except Exception:
    pass
