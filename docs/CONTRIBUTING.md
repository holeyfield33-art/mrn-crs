# Contributing

## Repository structure

This repo contains only the **Constrained Reasoning System (CRS)**.
The downstream services run from pre-built Docker images:

| Service | Source repo | Image |
| --- | --- | --- |
| Aletheia | [holeyfield33/aletheia-core](https://github.com/holeyfield33/aletheia-core) | `holeyfield33/aletheia-core:1.6.2` |
| Geometric Brain | [holeyfield33/geometric-brain](https://github.com/holeyfield33/geometric-brain) | `holeyfield33/geometric-brain:latest` |
| Mneme | [holeyfield33/mneme](https://github.com/holeyfield33/mneme) | `holeyfield33/mneme:latest` |

To modify those services, clone their respective repos.

## Working on CRS

```bash
# 1. Clone and set up
git clone https://github.com/holeyfield33/mrn-constrained-crs.git
cd mrn-constrained-crs
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Run tests
pytest tests/ -v

# 3. Run locally (without Docker)
ENABLE_SELF_HEALING=false uvicorn src.main:app --reload
```

## Branches

| Branch | Purpose |
| --- | --- |
| `main` | Constrained mode – human gates enabled, Aletheia active auditing, freeze logic active |
| `unconstrained` | Autonomous mode – no human gates, policy overrides, freeze logic disabled, faster healing |

### `main` branch (default)

This is the production-safe branch. All three safety flags carry their default values:

```
AUTONOMOUS_MODE=false
ENABLE_HUMAN_GATES=true
FREEZE_ON_CRITICAL=true
```

- Aletheia `DENIED` → HTTP 403, step rejected.
- Geometric Brain `human_escalation: true` → HTTP 423, step held for review.
- Entropy/drift crossing a critical threshold → system freezes, `freeze_manifest.json` written, human alerted.

All PRs must target `main`. CI runs the full test suite including the regression guards in `tests/test_unconstrained.py` that verify the constrained behaviour is intact.

### `unconstrained` branch

This branch is for **development, benchmarking, and research** against a fully autonomous CRS. It carries permissive flag values in `.env.example`:

```
AUTONOMOUS_MODE=true
ENABLE_HUMAN_GATES=false
FREEZE_ON_CRITICAL=false
SELF_HEAL_INTERVAL_SECONDS=15
LOG_LEVEL=DEBUG
```

**What changes compared to `main`:**

| Subsystem | Constrained (`main`) | Unconstrained |
| --- | --- | --- |
| Aletheia `DENIED` result | HTTP 403 | Logged warning, step continues (HTTP 200) |
| Geometric `human_escalation` (request) | HTTP 423 | Logged warning, step continues (HTTP 200) |
| Self-heal `escalate_to_human` action | Writes JSONL + calls webhook | Skipped entirely |
| Freeze on critical entropy/drift | Halts loop, writes manifest | Logged, loop continues |
| Healing cycle interval | 60 s | 15 s |
| Log level | INFO | DEBUG |

**What does NOT change:**

- Aletheia still audits every step — the receipt is recorded even when the decision is overridden.
- Geometric Brain still runs health-checks and computes spectral signatures.
- Entropy, drift, and Fibonacci recovery scores are still computed and logged every cycle.
- Rate limiting, API key auth, and input validation are unaffected.

#### Working on the unconstrained branch

```bash
git checkout unconstrained
cp .env.example .env   # permissive defaults are pre-set
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run the test suite (all eight unconstrained-mode tests must pass)
pytest tests/test_unconstrained.py -v

# Start the stack
docker compose up --build
```

#### Developing features on the unconstrained branch

1. Feature branches off `unconstrained` should be named `unconstrained/<feature>`.
2. Any code change that touches the bypass paths in `src/services/reasoning.py` or `src/services/self_healing.py` **must** include or update a test in `tests/test_unconstrained.py`.
3. Do **not** merge `unconstrained` into `main` — the permissive `.env.example` values must never land on `main`.
4. Changes that should apply to both branches (e.g. a bug fix in the pipeline itself) should be PRed to `main` first and then cherry-picked to `unconstrained`.

#### Safety checklist before pushing to `unconstrained`

- [ ] `pytest tests/test_unconstrained.py -v` passes (all 8 tests).
- [ ] `pytest tests/ -v` passes (full suite, including constrained regression guards).
- [ ] No hardcoded credentials or real service URLs in the diff.
- [ ] `.env.example` on this branch still shows `AUTONOMOUS_MODE=true` / `ENABLE_HUMAN_GATES=false` / `FREEZE_ON_CRITICAL=false` — do not accidentally revert them.
- [ ] Any new bypass path is logged with `logger.warning(...)` so operators can observe it.

## Code style

- Python 3.11+
- Type hints on public functions
- `pytest` + `pytest-asyncio` for tests

## Pull requests

1. Fork the repo and create a feature branch from `main`.
2. Ensure all tests pass: `pytest tests/ -v`
3. Open a PR against `main`.
