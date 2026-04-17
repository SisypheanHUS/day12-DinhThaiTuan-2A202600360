"""Cost Guard — Budget Protection"""
import time
from fastapi import HTTPException

from app.config import settings
from app.redis_client import USE_REDIS, client as _redis

PRICE_PER_1K_INPUT = 0.00015
PRICE_PER_1K_OUTPUT = 0.0006

_local_daily_cost = 0.0
_local_cost_day = time.strftime("%Y-%m-%d")


def check_and_record_cost(input_tokens: int, output_tokens: int):
    global _local_daily_cost, _local_cost_day
    today = time.strftime("%Y-%m-%d")
    cost = (input_tokens / 1000) * PRICE_PER_1K_INPUT + (output_tokens / 1000) * PRICE_PER_1K_OUTPUT

    if USE_REDIS:
        key = f"cost:{today}"
        current = float(_redis.get(key) or 0)
        if current >= settings.daily_budget_usd:
            raise HTTPException(503, "Daily budget exhausted. Try tomorrow.")
        _redis.incrbyfloat(key, cost)
        _redis.expire(key, 90000)
    else:
        if today != _local_cost_day:
            _local_daily_cost = 0.0
            _local_cost_day = today
        if _local_daily_cost >= settings.daily_budget_usd:
            raise HTTPException(503, "Daily budget exhausted. Try tomorrow.")
        _local_daily_cost += cost
