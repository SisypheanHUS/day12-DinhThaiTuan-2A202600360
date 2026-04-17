# Deployment Information

## Public URL
https://day12-agent.up.railway.app

## Platform
Railway

## Test Commands

### Health Check
```bash
curl https://day12-agent.up.railway.app/health
# Expected: {"status": "ok", "version": "1.0.0", ...}
```

### API Test (with authentication)
```bash
curl -X POST https://day12-agent.up.railway.app/ask \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
```

### Rate Limiting Test
```bash
for i in {1..25}; do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST https://day12-agent.up.railway.app/ask \
    -H "X-API-Key: YOUR_KEY" \
    -H "Content-Type: application/json" \
    -d '{"user_id": "test", "question": "test"}'
done
# Should return 429 after 20 requests
```

## Environment Variables Set
- `PORT` — Server port (injected by Railway)
- `ENVIRONMENT` — Set to `production`
- `REDIS_URL` — Redis connection string
- `AGENT_API_KEY` — API key for authentication
- `LOG_LEVEL` — Logging level
- `RATE_LIMIT_PER_MINUTE` — Rate limit threshold
- `DAILY_BUDGET_USD` — Daily cost budget

## Local Docker Test
```bash
cd 06-lab-complete
cp .env.example .env.local
docker compose up
curl http://localhost:8000/health
```
