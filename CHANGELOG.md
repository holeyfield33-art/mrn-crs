# Changelog

All notable changes to the MRN Constrained Reasoning System (CRS) are documented here.

## [1.1.0] - 2026-04-12

### Added (v1.1.0)

- **Entropy monitoring** – Shannon entropy computed from covariance eigenvalues of recent embeddings on every self-healing cycle.
- **Four-tier freeze logic** – system freezes (stops reasoning, writes `freeze_manifest.json`, escalates to human) on:
  - Tier 1: Semantic loop – 2 consecutive cycles with entropy < 0.35.
  - Tier 2: Critical information collapse – single cycle entropy < 0.25.
  - Tier 3: Runaway divergence – single cycle drift > 0.25.
  - Tier 4: Structural collapse – Fibonacci recovery score < 0.3.
- **Fibonacci anchor** – normalised Fibonacci sequence as ideal eigenvalue distribution; cosine similarity used as recovery metric.
- **Windowed spectral signature** – `compute_windowed_spectral_signature()` for covariance-based r\_ratio/SHI over embedding windows.
- **Shannon entropy utilities** – `compute_shannon_entropy()`, `compute_entropy_from_embeddings()` in `spectral_utils.py`.
- **`fibonacci_recovery_score()`** – cosine similarity between eigenvalue distribution and Fibonacci anchor.
- **Drift history tracking** – rolling 100-entry history of entropy/drift per cycle in `SelfHealingLoop`.
- **`FreezeEvent` exception** – raised when the system enters a frozen state.
- **`.env.example`** – example environment file with all configuration variables.

### Changed (v1.1.0)

- `SelfHealingLoop._run_cycle()` now computes entropy, checks freeze conditions before applying corrective actions.
- `_action_escalate_to_human()` accepts a custom `message` parameter.
- Entropy is included in Aletheia audit payloads and healing history records.
- README updated with entropy monitoring and four-tier freeze documentation.

## [1.0.0] - 2026-04-11

### Added (v1.0.0)

- **API key authentication** – `CRS_API_KEYS` env var; Bearer token required on all non-public routes.
- **Rate limiting** – slowapi with Redis (or in-memory) backend; configurable via `CRS_RATE_LIMIT_PER_MINUTE`.
- **Structured JSON logging** – python-json-logger with method, path, status, latency, client_id, request_id.
- **Prometheus metrics** – `/metrics` endpoint with `crs_requests_total`, `crs_self_heal_total`, `crs_client_call_duration_seconds`.
- **Readiness & liveness probes** – `GET /ready` (downstream health + degraded flag), `GET /live`.
- **Graceful shutdown** – stops self-healing loop, cancels background task on SIGTERM.
- **Multi-level self-healing policies** – drift classification (none / low / medium / high) with configurable actions: `inject_memories`, `adjust_temperature`, `reset_context`, `escalate_to_human`.
- **Human escalation** – JSONL file logging + optional webhook POST for high-drift events.
- **Healing history** – SQLite database recording every healing event (drift, level, actions, memories injected).
- **Redis service** in docker-compose for distributed rate limiting.
- **32 passing tests** covering reasoning, consensus, self-healing policies, auth, probes, metrics, and healing history.

### Changed (v1.0.0)

- `SelfHealingLoop` now accepts level thresholds, escalation config, and healing history DB path.
- `docker-compose.yml` includes Redis alongside Aletheia, Geometric Brain, Mneme, and Postgres.
- README fully rewritten with architecture diagram, full API reference, configuration table, and deployment guide.

## [0.2.0] - 2026-04-11

### Added (v0.2.0)

- `SelfHealingLoop` class (refactored from function-based loop).
- `MnemeClient.geometric_search_by_spectral()` method.
- `GeometricClient.self_heal()` accepts `current_r` parameter.
- Full docker-compose stack: CRS + Aletheia + Geometric Brain + Mneme + Postgres.
- Self-healing configuration env vars (drift threshold, healthy r/SHI ranges, min memories).

### Changed (v0.2.0)

- `main.py` stores loop in `app.state` for graceful shutdown.
- docker-compose uses `pgvector/pgvector:pg16` for Postgres.

## [0.1.0] - 2026-04-11

### Added (v0.1.0)

- Initial CRS FastAPI service with `POST /reason`, `GET /trace`, consensus endpoints, `GET /health`.
- Aletheia audit integration (ALLOW / DENY with receipts).
- Geometric Brain health-check and manifold-audit integration.
- Mneme memory storage with geometric index.
- SHA-256 fingerprinting of reasoning steps.
- Sentence-transformers embedding (with deterministic hash-based fallback).
- Local SVD-based spectral signature computation (r_ratio, SHI, unitarity_check).
- Consensus frame management with auto-resolution.
- Graceful degradation when external services are unreachable.
- 10 unit tests (reasoning, consensus, self-healing).
- Dockerfile and docker-compose.yml.
