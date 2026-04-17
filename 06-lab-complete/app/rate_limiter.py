"""Rate Limiter — Sliding Window Counter"""
import time
from fastapi import HTTPException

from app.config import settings
from app.redis_client import USE_REDIS, client as _redis

if not USE_REDIS:
    from collections import defaultdict, deque
    _local_windows: dict[str, deque] = defaultdict(deque)


def check_rate_limit(key: str):
    now = time.time()
    window_seconds = 60
    max_requests = settings.rate_limit_per_minute

    if USE_REDIS:
        redis_key = f"ratelimit:{key}"
        _redis.zremrangebyscore(redis_key, 0, now - window_seconds)
        current = _redis.zcard(redis_key)
        if current >= max_requests:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {max_requests} req/min",
                headers={"Retry-After": "60"},
            )
        _redis.zadd(redis_key, {str(now): now})
        _redis.expire(redis_key, window_seconds + 1)
    else:
        window = _local_windows[key]
        while window and window[0] < now - window_seconds:
            window.popleft()
        if len(window) >= max_requests:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {max_requests} req/min",
                headers={"Retry-After": "60"},
            )
        window.append(now)
