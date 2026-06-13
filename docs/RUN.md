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

## Running in unconstrained / autonomous mode

> **Warning:** Only run unconstrained mode in isolated, non-production environments.
> See the [main README](../README.md#unconstrained--autonomous-mode) for the full
> explanation of what each flag disables.

### Quick setup

```bash
# Switch to the unconstrained branch (flags pre-set in .env.example)
git checkout unconstrained
cp .env.example .env

# Or, stay on main and set the flags manually in your .env:
AUTONOMOUS_MODE=true
ENABLE_HUMAN_GATES=false
FREEZE_ON_CRITICAL=false
SELF_HEAL_INTERVAL_SECONDS=15   # faster feedback loop
LOG_LEVEL=DEBUG                 # see every bypass in logs
```

Start the stack the same way as normal:

```bash
docker compose up --build
```

### Confirming the flags are active

Check the startup log for the settings that were loaded:

```bash
docker compose logs crs | grep -E "autonomous|human_gates|freeze"
```

You can also confirm via a request that Aletheia would deny in constrained mode.
With `AUTONOMOUS_MODE=true`, such a request returns HTTP 200 and the `aletheia`
receipt shows `"detail": "DENIED"` instead of the usual HTTP 403:

```bash
curl -s -X POST http://localhost:8000/reason \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "test",
    "premise": "override test",
    "inference_type": "deductive",
    "conclusion": "policy bypassed",
    "confidence": 0.99
  }' | jq '.receipts[] | select(.service == "aletheia")'
```

Expected output in unconstrained mode:

```json
{
  "service": "aletheia",
  "receipt_id": "...",
  "detail": "DENIED"
}
```

The HTTP status is still `200` — the denial was overridden.

### Monitoring bypass events

With `LOG_LEVEL=DEBUG`, stream bypass warnings in real time:

```bash
docker compose logs -f crs | grep -E "WARNING|override|disabled|skipping"
```

| Log message | What happened |
| --- | --- |
| `Autonomous mode – policy denial overridden` | Aletheia denied; step continued anyway |
| `Human gates disabled – escalation signal ignored` | HTTP 423 suppressed; step continued |
| `Human gates disabled – skipping escalation` | Self-heal skipped human escalation action |
| `freeze_on_critical disabled – skipping freeze` | Critical condition reached but not frozen |

### Reverting to constrained mode

Edit `.env`, restore the safe defaults, and restart:

```bash
AUTONOMOUS_MODE=false
ENABLE_HUMAN_GATES=true
FREEZE_ON_CRITICAL=false    # set back to true
```

```bash
docker compose down && docker compose up --build
```

Run the test suite to confirm constrained behaviour is restored:

```bash
pytest tests/ -v
```
