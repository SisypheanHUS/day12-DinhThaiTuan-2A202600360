# Day 12 Lab - Mission Answers

**Student:** Dinh Thai Tuan  
**Student ID:** 2A202600360  
**Date:** 2026-04-17

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found

Analyzing `01-localhost-vs-production/develop/app.py`:

1. **Hardcoded API key** — `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` exposes secrets if pushed to GitHub.
2. **Hardcoded database URL with password** — `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"` leaks credentials.
3. **No config management** — `DEBUG = True` and `MAX_TOKENS = 500` are hardcoded, cannot change between environments.
4. **Using `print()` instead of structured logging** — `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` logs secrets and is unparseable by log aggregators.
5. **No health check endpoint** — Platform has no way to know if the agent crashed, cannot auto-restart.
6. **Port hardcoded** — `port=8000` doesn't read from `PORT` env var. Cloud platforms inject PORT automatically.
7. **Host bound to localhost** — `host="localhost"` means the app is unreachable from outside the container.
8. **Debug reload enabled in production** — `reload=True` wastes resources and can cause instability.
9. **No graceful shutdown** — Ongoing requests are dropped when the process is killed.
10. **No input validation** — The `/ask` endpoint accepts raw `question: str` without length or type validation.

### Exercise 1.2: Running basic version

```bash
cd 01-localhost-vs-production/develop
pip install -r requirements.txt
python app.py
```

```bash
curl http://localhost:8000/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
```

Result: The agent responds successfully. It works on localhost but is NOT production-ready due to all the anti-patterns listed above.

### Exercise 1.3: Comparison table

| Feature | Develop (Basic) | Production (Advanced) | Why Important? |
|---------|----------------|----------------------|----------------|
| Config | Hardcoded values (`DEBUG=True`, `PORT=8000`) | Environment variables via `Settings` dataclass | Allows different config per environment without code changes; secrets stay out of git |
| Health check | None | `GET /health` returns status, uptime, version | Platform knows when to restart crashed containers; monitoring can alert on degraded state |
| Logging | `print()` statements, logs secrets | Structured JSON logging, no secrets logged | JSON logs are parseable by Datadog/Loki/ELK; structured format enables search and alerting |
| Shutdown | Abrupt termination | Graceful via SIGTERM handler + lifespan | In-flight requests complete before shutdown; no data loss during deployments |
| Host binding | `localhost` (local only) | `0.0.0.0` (all interfaces) | Container networking requires binding to all interfaces to be reachable |
| Port | Hardcoded `8000` | From `PORT` env var | Railway/Render inject PORT automatically; hardcoded port causes deploy failure |
| CORS | None | Configured via `ALLOWED_ORIGINS` | Controls which frontends can call the API; prevents unauthorized cross-origin requests |
| Security | API key printed in logs | No secrets in logs | Leaked secrets in logs can be exploited; compliance requirement |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions

Reading `02-docker/develop/Dockerfile`:

1. **Base image:** `python:3.11` — Full Python distribution including OS, Python runtime, pip, and build tools. ~1 GB in size.
2. **Working directory:** `/app` — This is where the application code lives inside the container. Set via `WORKDIR /app`.
3. **Why COPY requirements.txt first?** Docker layer caching. If `requirements.txt` hasn't changed, Docker reuses the cached layer from `RUN pip install`. Only code changes trigger a rebuild of the later layers, making builds much faster.
4. **CMD vs ENTRYPOINT:** `CMD` provides default arguments that can be overridden at runtime (`docker run myimage /bin/bash`). `ENTRYPOINT` sets a fixed executable that always runs — `CMD` arguments are appended to it. Use `ENTRYPOINT` when the container should always run the same program.

### Exercise 2.2: Build and run

```bash
cd ../../  # project root
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -p 8000:8000 my-agent:develop
```

Image size observation:
```bash
docker images my-agent:develop
# REPOSITORY    TAG       SIZE
# my-agent      develop   ~1.0 GB
```

### Exercise 2.3: Image size comparison

Reading `02-docker/production/Dockerfile`:

- **Stage 1 (builder):** Installs build tools (gcc, libpq-dev) and pip packages with `--user` flag into `/root/.local`. This stage is discarded after build.
- **Stage 2 (runtime):** Uses `python:3.11-slim` (minimal OS), copies only the installed packages from builder, copies app code, runs as non-root user.
- **Why smaller?** Build tools (gcc, apt cache) are left behind in Stage 1. Only runtime essentials are in the final image.

| Image | Size | Notes |
|-------|------|-------|
| Develop (`python:3.11`) | ~1000 MB | Full Python, build tools included |
| Production (`python:3.11-slim`, multi-stage) | ~250 MB | Slim base, no build tools, non-root |
| **Reduction** | **~75%** | Multi-stage build removes all build-time dependencies |

### Exercise 2.4: Architecture diagram

Reading `02-docker/production/docker-compose.yml`:

```
Client (browser/curl)
       │
       ▼
┌──────────────┐
│  Nginx:80    │  ← Reverse proxy, load balancer
└──────┬───────┘
       │
       ├──────────┐
       ▼          ▼
┌──────────┐ ┌──────────┐
│ Agent:8k │ │ Agent:8k │  ← FastAPI app (scalable replicas)
└────┬─────┘ └────┬─────┘
     │            │
     └──────┬─────┘
            ▼
     ┌────────────┐
     │ Redis:6379 │  ← Session cache, rate limiting
     └────────────┘
            │
     ┌────────────┐
     │ Qdrant:6333│  ← Vector database for RAG
     └────────────┘
```

Services started: agent (FastAPI), redis (cache/sessions), qdrant (vector DB), nginx (reverse proxy/LB).
Communication: Nginx routes HTTP traffic to agent instances. Agents connect to Redis for state and Qdrant for vector search. All services are on an internal bridge network.

---

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment

Steps performed:
1. Installed Railway CLI: `npm i -g @railway/cli`
2. Logged in: `railway login`
3. Initialized project: `railway init`
4. Set environment variables:
   ```bash
   railway variables set PORT=8000
   railway variables set AGENT_API_KEY=my-secret-key
   railway variables set ENVIRONMENT=production
   ```
5. Deployed: `railway up`
6. Got domain: `railway domain`

Test commands:
```bash
# Health check
curl https://<app-name>.railway.app/health
# Expected: {"status": "ok", ...}

# Agent endpoint
curl -X POST https://<app-name>.railway.app/ask \
  -H "X-API-Key: my-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
```

### Exercise 3.2: Render vs Railway comparison

| Aspect | `railway.toml` | `render.yaml` |
|--------|---------------|---------------|
| Format | TOML | YAML |
| Builder | `NIXPACKS` (auto-detect) | Explicit `buildCommand` |
| Start | `startCommand` field | `startCommand` field |
| Health check | `healthcheckPath` | `healthCheckPath` |
| Env vars | Set via CLI (`railway variables set`) | Inline in YAML or dashboard |
| Redis | Separate service, manual setup | Built-in `type: redis` add-on |
| Auto deploy | Via GitHub integration | `autoDeploy: true` |
| Region | Auto-selected | Configurable (`region: singapore`) |

Key difference: Render uses Blueprint (render.yaml) for Infrastructure-as-Code, defining all services in one file. Railway uses simpler config + CLI for env vars.

### Exercise 3.3: GCP Cloud Run (Optional)

Reading `cloudbuild.yaml` and `service.yaml`:

- `cloudbuild.yaml` defines a CI/CD pipeline: build Docker image → push to Container Registry → deploy to Cloud Run.
- `service.yaml` defines the Cloud Run service spec: container image, port, env vars, scaling (min/max instances), resource limits, and health check path.
- This is the most production-grade setup with full CI/CD automation, auto-scaling, and managed infrastructure.

---

## Part 4: API Security

### Exercise 4.1: API Key authentication

Reading `04-api-gateway/develop/app.py`:

- **Where is API key checked?** In the `verify_api_key()` function, which is a FastAPI dependency injected via `Depends(verify_api_key)`. It reads the `X-API-Key` header using `APIKeyHeader`.
- **What happens with wrong key?** Returns HTTP 403 "Invalid API key." If no key is provided, returns HTTP 401 "Missing API key."
- **How to rotate key?** Change the `AGENT_API_KEY` environment variable and restart the service. No code change needed. In production, support multiple active keys for zero-downtime rotation.

Test results:
```bash
# Without key → 401
curl -X POST http://localhost:8000/ask -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
# {"detail": "Missing API key. Include header: X-API-Key: <your-key>"}

# With key → 200
curl -X POST http://localhost:8000/ask \
  -H "X-API-Key: demo-key-change-in-production" \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
# {"question": "Hello", "answer": "..."}
```

### Exercise 4.2: JWT authentication

Reading `04-api-gateway/production/auth.py`:

JWT Flow:
1. Client sends `POST /auth/token` with username/password
2. Server validates credentials against user store
3. Server creates JWT with payload: `sub` (username), `role`, `iat` (issued at), `exp` (expiry)
4. Server signs JWT with `SECRET_KEY` using HS256 algorithm
5. Client includes JWT in subsequent requests: `Authorization: Bearer <token>`
6. Server verifies signature and checks expiry on each request

```bash
# Get token
curl -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username": "student", "password": "demo123"}'
# Returns: {"access_token": "eyJ...", "token_type": "bearer", "expires_in_minutes": 60}

# Use token
curl -X POST http://localhost:8000/ask \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"question": "Explain JWT"}'
```

### Exercise 4.3: Rate limiting

Reading `04-api-gateway/production/rate_limiter.py`:

- **Algorithm:** Sliding Window Counter. Each user has a deque of request timestamps. Old timestamps (outside the 60s window) are removed before checking.
- **Limit:** User tier: 10 requests/minute. Admin tier: 100 requests/minute.
- **How to bypass for admin?** The code creates two `RateLimiter` instances: `rate_limiter_user` (10 req/min) and `rate_limiter_admin` (100 req/min). The endpoint checks the user's role from JWT and applies the appropriate limiter.

Test result:
```bash
for i in {1..15}; do
  curl -X POST http://localhost:8000/ask \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"question": "Test '$i'"}'
done
# Requests 1-10: 200 OK
# Requests 11+: 429 Too Many Requests
# {"error": "Rate limit exceeded", "retry_after_seconds": ...}
```

### Exercise 4.4: Cost guard implementation

Reading `04-api-gateway/production/cost_guard.py`:

Approach:
- Each user has a `UsageRecord` tracking daily input/output tokens and cost
- Before each LLM call, `check_budget()` verifies both per-user ($1/day) and global ($10/day) budgets
- After LLM call, `record_usage()` updates token counts and cost
- Cost calculation: `(input_tokens / 1000) * $0.00015 + (output_tokens / 1000) * $0.0006` (GPT-4o-mini pricing)
- Warning logged at 80% budget usage
- Returns HTTP 402 (Payment Required) for per-user limit, HTTP 503 for global limit
- Resets daily (checks date string)

For production with Redis:
```python
def check_budget(user_id: str, estimated_cost: float) -> bool:
    month_key = datetime.now().strftime("%Y-%m")
    key = f"budget:{user_id}:{month_key}"
    current = float(r.get(key) or 0)
    if current + estimated_cost > 10:
        return False
    r.incrbyfloat(key, estimated_cost)
    r.expire(key, 32 * 24 * 3600)  # 32 days TTL
    return True
```

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health and readiness checks

Reading `05-scaling-reliability/develop/app.py`:

Implementation:
```python
@app.get("/health")
def health():
    # Liveness probe - checks if process is alive
    # Returns: status, uptime, version, memory usage
    # Platform restarts container if this returns non-200
    return {"status": "ok", "uptime_seconds": ..., "checks": {"memory": ...}}

@app.get("/ready")
def ready():
    # Readiness probe - checks if ready to serve traffic
    # Checks: _is_ready flag (set after startup completes)
    # Returns 503 during startup/shutdown
    # Load balancer stops routing traffic if 503
    if not _is_ready:
        raise HTTPException(503, "Agent not ready yet")
    return {"ready": True}
```

Key difference:
- **Health (liveness):** "Is the process alive?" → Platform restarts if not
- **Ready (readiness):** "Can it handle requests?" → Load balancer skips if not

### Exercise 5.2: Graceful shutdown

Implementation using SIGTERM handler and lifespan context:

```python
def handle_sigterm(signum, frame):
    logger.info("Received SIGTERM — initiating graceful shutdown")

signal.signal(signal.SIGTERM, handle_sigterm)
```

Combined with lifespan shutdown:
1. Set `_is_ready = False` → readiness probe returns 503 → LB stops routing new requests
2. Wait for `_in_flight_requests` to reach 0 (up to 30s timeout)
3. Close connections and clean up
4. Exit cleanly

Test:
```bash
python app.py &
PID=$!
kill -TERM $PID
# Log shows: "Graceful shutdown initiated..."
# Log shows: "Waiting for N in-flight requests..."
# Log shows: "Shutdown complete"
```

### Exercise 5.3: Stateless design

Reading `05-scaling-reliability/production/app.py`:

Anti-pattern (stateful):
```python
# State in memory — lost when instance restarts, not shared across replicas
conversation_history = {}
```

Correct (stateless with Redis):
```python
def save_session(session_id, data, ttl_seconds=3600):
    _redis.setex(f"session:{session_id}", ttl_seconds, json.dumps(data))

def load_session(session_id):
    data = _redis.get(f"session:{session_id}")
    return json.loads(data) if data else {}
```

Why stateless matters: When scaling to multiple instances, each has its own memory. User A's request goes to Instance 1 (saves conversation), next request goes to Instance 2 (no conversation!). With Redis, any instance can serve any user.

### Exercise 5.4: Load balancing

```bash
docker compose up --scale agent=3
```

Observations:
- 3 agent instances started, each with unique `INSTANCE_ID`
- Nginx distributes requests round-robin across instances
- Each response includes `served_by` field showing which instance handled it
- If one instance dies, Nginx routes to remaining healthy instances

### Exercise 5.5: Test stateless

```bash
python test_stateless.py
```

Script creates a session, sends 5 questions. Each request may be served by a different instance (shown in `served_by` field). Despite different instances handling requests, conversation history is preserved because it's stored in Redis. All instances read from the same Redis, so session data is always available regardless of which instance handles the request.
