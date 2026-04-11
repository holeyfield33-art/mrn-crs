# Changelog

All notable changes to the MRN Constrained Reasoning System (CRS) are documented here.

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
