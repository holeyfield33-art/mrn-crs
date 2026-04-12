# Running the MRN Stack

## Starting

```bash
docker compose up --build    # foreground (see logs)
docker compose up --build -d # background (detached)
```

## Service endpoints

| Service | URL | Description |
| --- | --- | --- |
| CRS | http://localhost:8000 | Main API |
| Aletheia | http://localhost:8300 | Security audit oracle |
| Geometric Brain | http://localhost:8200 | Spectral analysis |
| Mneme | http://localhost:8100 | Memory persistence |

## Health & probes

```bash
curl http://localhost:8000/health   # full health with downstream status
curl http://localhost:8000/live     # liveness (always 200)
curl http://localhost:8000/ready    # readiness (includes degraded flag)
```

## Submitting a reasoning step

```bash
curl -X POST http://localhost:8000/reason \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent-1",
    "premise": "All humans are mortal",
    "inference_type": "deductive",
    "conclusion": "Socrates is mortal",
    "confidence": 0.95
  }'
```

If `CRS_API_KEYS` is set in `.env`, add `-H "Authorization: Bearer <key>"`.

## Smoke test script

```bash
bash scripts/run_demo.sh
```

## Environment variables

All configuration is in `.env`. See the main [README](../README.md#configuration)
for the full variable table.

Key variables for first-time users:

| Variable | Purpose |
| --- | --- |
| `CRS_API_KEYS` | Protect the API (comma-separated keys); empty = open |
| `ENABLE_SELF_HEALING` | Toggle the background drift-detection loop |
| `LOG_LEVEL` | `DEBUG` for verbose output, `INFO` for production |
| `POSTGRES_PASSWORD` | Postgres password used by Mneme |

## Viewing logs

```bash
docker compose logs -f crs        # CRS only
docker compose logs -f             # all services
```

## Restarting a single service

```bash
docker compose restart crs
```

## Prometheus metrics

Scrape `http://localhost:8000/metrics` with Prometheus. Key metrics:

- `crs_requests_total` – request count by endpoint, status, client
- `crs_self_heal_total` – healing events by outcome
- `crs_client_call_duration_seconds` – downstream call latency
