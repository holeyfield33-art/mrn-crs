# MRN Constrained Reasoning System (CRS)

**Fully self-contained** – clone this repo, run `docker compose up`, and get the
entire MRN stack running locally. All downstream service images are pulled
automatically from Docker Hub.

Production-grade FastAPI service that orchestrates **constrained multi-agent reasoning**
with geometric self-healing, Aletheia security audit, Mneme memory persistence,
Geometric Brain spectral analysis, **entropy monitoring**, and **four-tier freeze logic**.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (v20.10+)
- [Docker Compose](https://docs.docker.com/compose/) (v2+, bundled with Docker Desktop)

No other repositories or local builds are required.

## Architecture

```text
┌──────────────┐   POST /reason    ┌────────────────────────────┐
│  Agent / UI  │ ────────────────► │  CRS  (FastAPI :8000)      │
└──────────────┘                   │                            │
                                   │  1. fingerprint            │
                                   │  2. Aletheia audit ──────► │──► Aletheia (:8300)
                                   │  3. Geometric health ────► │──► Geometric Brain (:8200)
                                   │  4. embed (MiniLM)         │
                                   │  5. spectral signature     │
                                   │  6. Mneme store ─────────► │──► Mneme (:8100)
                                   │  7. return receipts        │
                                   │                            │
                                   │  Background:               │
                                   │  self-healing loop ──────► │    ┌──────────┐
                                   │   ↕ drift detection        │    │ Postgres │
                                   │   ↕ entropy monitoring     │    │ (pgvector)│
                                   │   ↕ four-tier freeze       │    └──────────┘
                                   │   ↕ human escalation       │
                                   └────────────────────────────┘
```

## Quick start

```bash
# 1. Clone the repo
git clone https://github.com/holeyfield33/mrn-constrained-crs.git
cd mrn-constrained-crs

# 2. Copy environment config (works out of the box with defaults)
cp .env.example .env

# 3. Start all services (CRS + Aletheia + Geometric Brain + Mneme + Postgres + Redis)
docker compose up --build

# 4. Verify
curl http://localhost:8000/health
```

Docker pulls public images for Aletheia, Geometric Brain, Mneme, Postgres (pgvector),
and Redis automatically. Only the CRS service is built from this repo's `Dockerfile`.

See [docs/INSTALL.md](docs/INSTALL.md) for detailed setup and
[docs/RUN.md](docs/RUN.md) for operational guidance.

## Running locally (without Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
ENABLE_SELF_HEALING=false uvicorn src.main:app --reload
```

## API reference

### POST /reason

Submit a reasoning step through the full pipeline (audit, health-check, embed, spectral, store).

**Request:**

```json
{
  "agent_id": "agent-1",
  "premise": "All humans are mortal",
  "inference_type": "deductive",
  "conclusion": "Socrates is mortal",
  "confidence": 0.95
}
```

**Response (200):**

```json
{
  "step_id": "uuid",
  "fingerprint": "sha256hex",
  "receipts": [
    {"service": "aletheia", "receipt_id": "...", "detail": "ALLOW"},
    {"service": "mneme", "receipt_id": "...", "detail": "stored"}
  ],
  "spectral": {"r_ratio": 0.58, "shi": 0.94, "unitarity_check": true}
}
```

**Error codes:** 403 (policy denied), 422 (validation), 423 (human escalation).

### GET /trace?fingerprint=...

Retrieve non-superseded reasoning steps by SHA-256 fingerprint.

### POST /consensus/frame

Create a new consensus frame with competing step IDs.

```json
{"competing_steps": ["step-a", "step-b"]}
```

### POST /consensus/update

Add audited evidence to a consensus frame.

```json
{"frame_id": "...", "step_id": "step-a", "summary": "Strong evidence", "confidence": 0.92}
```

### GET /consensus/{frame_id}

Retrieve a consensus frame by ID.

### GET /health

Service health check with downstream service status.

### GET /live

Liveness probe. Always returns 200 if the process is running.

### GET /ready

Readiness probe. Returns 200 with `degraded: true/false` based on downstream reachability.

### GET /metrics

Prometheus metrics endpoint. Exposes:

- `crs_requests_total` (by endpoint, status, client)
- `crs_self_heal_total` (by outcome)
- `crs_client_call_duration_seconds` (by service)

## Configuration

All settings are read from environment variables (or `.env` file).

| Variable | Default | Description |
| --- | --- | --- |
| `ALETHEIA_URL` | `http://localhost:8300` | Aletheia service base URL |
| `GEOMETRIC_URL` | `http://localhost:8200` | Geometric Brain service base URL |
| `MNEME_URL` | `http://localhost:8100` | Mneme service base URL |
| `CRS_API_KEYS` | (empty) | Comma-separated API keys; empty disables auth |
| `CRS_RATE_LIMIT_PER_MINUTE` | `60` | Max requests per minute per API key / IP |
| `REDIS_URL` | (empty) | Redis URL for rate-limit storage; empty uses in-memory |
| `ENABLE_SELF_HEALING` | `true` | Enable the background self-healing loop |
| `SELF_HEAL_INTERVAL_SECONDS` | `60` | Seconds between self-healing cycles |
| `SELF_HEAL_DRIFT_THRESHOLD` | `0.5` | Drift threshold passed to Geometric Brain |
| `SELF_HEAL_HEALTHY_R_MIN` | `0.57` | Min r\_ratio for healthy memory retrieval |
| `SELF_HEAL_HEALTHY_R_MAX` | `0.59` | Max r\_ratio for healthy memory retrieval |
| `SELF_HEAL_HEALTHY_SHI_MIN` | `0.8` | Min SHI for healthy memory retrieval |
| `SELF_HEAL_MIN_MEMORIES` | `10` | Min memories with embeddings before healing |
| `SELF_HEAL_LEVEL_LOW` | `0.02` | Drift threshold for low-level actions |
| `SELF_HEAL_LEVEL_MEDIUM` | `0.05` | Drift threshold for medium-level actions |
| `SELF_HEAL_LEVEL_HIGH` | `0.10` | Drift threshold for high-level actions |
| `SELF_HEAL_ESCALATION_WEBHOOK` | (empty) | Webhook URL for human escalation POSTs |
| `SELF_HEAL_ESCALATION_FILE` | `escalations.jsonl` | File path for escalation log entries |
| `HEALING_HISTORY_DB` | `healing_history.db` | SQLite path for healing event history |
| `SAMPLING_TEMPERATURE` | `0.7` | Initial sampling temperature |
| `LOG_LEVEL` | `INFO` | Python log level (DEBUG, INFO, WARNING, ERROR) |

## Self-healing policies

The self-healing loop computes drift as `abs(current_r - 0.578)` (golden-ratio reference)
and classifies it into levels:

| Level | Drift range | Actions |
| --- | --- | --- |
| none | < 0.02 | No action |
| low | 0.02 – 0.05 | `inject_memories` |
| medium | 0.05 – 0.10 | `inject_memories`, `adjust_temperature` |
| high | > 0.10 | `reset_context`, `inject_memories`, `adjust_temperature`, `escalate_to_human` |

**Actions:**

- **inject\_memories** – Retrieve healthy memories from Mneme (r near 0.578, high SHI) and inject into the shared context buffer.
- **adjust\_temperature** – Lower the global sampling temperature proportionally to drift severity.
- **reset\_context** – Clear the context buffer entirely (re-populated by inject\_memories).
- **escalate\_to\_human** – Write a JSONL entry to the escalation file and optionally POST to a webhook.

Every action is audited via Aletheia and recorded in the healing history SQLite database.

## Entropy monitoring & four-tier freeze

Shannon entropy is computed from the covariance eigenvalues of recent embeddings on
every self-healing cycle.  The system **freezes** (stops all reasoning, writes
`freeze_manifest.json`, escalates to human) when any of four conditions is met:

| Tier | Condition | Trigger |
| --- | --- | --- |
| 1 – Semantic loop | 2 consecutive cycles with entropy < 0.35 | Repetitive / circular reasoning |
| 2 – Critical collapse | Single cycle entropy < 0.25 | Near-total information collapse |
| 3 – Runaway divergence | Single cycle drift > 0.25 | Spectral signature diverging far from golden ratio |
| 4 – Structural collapse | Fibonacci recovery score < 0.3 | Eigenvalue distribution deviating from golden-ratio ideal |

A **Fibonacci anchor** (normalised first 10 Fibonacci numbers) serves as the ideal
eigenvalue distribution.  Cosine similarity between the current eigenvalue vector and
this anchor is the *Fibonacci recovery score*.

## Testing

```bash
# Unit tests
pip install pytest pytest-asyncio
pytest tests/ -v

# Smoke test (requires running server)
bash scripts/run_demo.sh
```

## Deployment

1. Set `CRS_API_KEYS` to a strong comma-separated list of keys.
2. Set `REDIS_URL` to a Redis instance for distributed rate limiting.
3. Place behind a reverse proxy (nginx, Traefik) with TLS.
4. Point Prometheus at `/metrics` for monitoring.
5. Configure alerting on `crs_self_heal_total{outcome="high"}` for drift events.
6. Set `SELF_HEAL_ESCALATION_WEBHOOK` to a Slack/PagerDuty webhook for human escalation.

## License

MIT – see [LICENSE](LICENSE).
