"""
Production AI Agent — Day 12 Final Project

  - Config from environment (12-factor)
  - Structured JSON logging
  - API Key authentication
  - Rate limiting (Redis-backed)
  - Cost guard (Redis-backed)
  - Input validation (Pydantic)
  - Health check + Readiness probe
  - Graceful shutdown
  - Stateless design (conversation history in Redis)
  - Security headers + CORS
"""
import os
import time
import signal
import logging
import json
import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from app.config import settings
from app.auth import verify_api_key
from app.rate_limiter import check_rate_limit
from app.cost_guard import check_and_record_cost
from app.redis_client import USE_REDIS, client as _redis

from utils.mock_llm import ask as llm_ask

# ── Logging ──
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

START_TIME = time.time()
_is_ready = False
_request_count = 0
_error_count = 0

if not USE_REDIS:
    _memory_sessions: dict[str, list] = {}


def _get_history(user_id: str) -> list:
    if USE_REDIS:
        data = _redis.get(f"history:{user_id}")
        return json.loads(data) if data else []
    return _memory_sessions.get(user_id, [])


def _save_history(user_id: str, history: list):
    if len(history) > 20:
        history = history[-20:]
    if USE_REDIS:
        _redis.setex(f"history:{user_id}", 3600, json.dumps(history))
    else:
        _memory_sessions[user_id] = history


# ── Lifespan ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready
    logger.info(json.dumps({
        "event": "startup",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "storage": "redis" if USE_REDIS else "in-memory",
    }))
    time.sleep(0.1)
    _is_ready = True
    logger.info(json.dumps({"event": "ready"}))
    yield
    _is_ready = False
    logger.info(json.dumps({"event": "shutdown"}))


# ── App ──
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    global _request_count, _error_count
    start = time.time()
    _request_count += 1
    try:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers.pop("server", None)
        duration = round((time.time() - start) * 1000, 1)
        logger.info(json.dumps({
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": duration,
        }))
        return response
    except Exception:
        _error_count += 1
        raise


# ── Models ──
class AskRequest(BaseModel):
    user_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8],
                         description="User ID for conversation tracking")
    question: str = Field(..., min_length=1, max_length=2000,
                          description="Your question for the agent")


class AskResponse(BaseModel):
    question: str
    answer: str
    user_id: str
    model: str
    timestamp: str
    storage: str


# ── Endpoints ──
@app.get("/", tags=["Info"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "endpoints": {
            "ask": "POST /ask (requires X-API-Key)",
            "health": "GET /health",
            "ready": "GET /ready",
        },
    }


@app.post("/ask", response_model=AskResponse, tags=["Agent"])
async def ask_agent(
    body: AskRequest,
    request: Request,
    _key: str = Depends(verify_api_key),
):
    check_rate_limit(_key[:8])

    input_tokens = len(body.question.split()) * 2
    check_and_record_cost(input_tokens, 0)

    logger.info(json.dumps({
        "event": "agent_call",
        "user_id": body.user_id,
        "q_len": len(body.question),
        "client": str(request.client.host) if request.client else "unknown",
    }))

    history = _get_history(body.user_id)
    history.append({"role": "user", "content": body.question})

    answer = llm_ask(body.question)

    history.append({"role": "assistant", "content": answer})
    _save_history(body.user_id, history)

    output_tokens = len(answer.split()) * 2
    check_and_record_cost(0, output_tokens)

    return AskResponse(
        question=body.question,
        answer=answer,
        user_id=body.user_id,
        model=settings.llm_model,
        timestamp=datetime.now(timezone.utc).isoformat(),
        storage="redis" if USE_REDIS else "in-memory",
    )


@app.get("/health", tags=["Operations"])
def health():
    status = "ok"
    checks = {"llm": "mock" if not settings.openai_api_key else "openai"}
    if USE_REDIS:
        try:
            _redis.ping()
            checks["redis"] = "connected"
        except Exception:
            checks["redis"] = "disconnected"
            status = "degraded"
    return {
        "status": status,
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Operations"])
def ready():
    if not _is_ready:
        raise HTTPException(503, "Not ready")
    if USE_REDIS:
        try:
            _redis.ping()
        except Exception:
            raise HTTPException(503, "Redis not available")
    return {"ready": True}


@app.get("/metrics", tags=["Operations"])
def metrics(_key: str = Depends(verify_api_key)):
    return {
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "error_count": _error_count,
    }


# ── Graceful Shutdown ──
def _handle_signal(signum, _frame):
    logger.info(json.dumps({"event": "signal", "signum": signum}))


signal.signal(signal.SIGTERM, _handle_signal)


if __name__ == "__main__":
    logger.info(f"Starting {settings.app_name} on {settings.host}:{settings.port}")
    logger.info(f"API Key: {settings.agent_api_key[:4]}****")
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
