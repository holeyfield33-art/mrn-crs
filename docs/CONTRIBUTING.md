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
| `main` | Constrained mode – human gates enabled, Aletheia active auditing |
| `unconstrained` | Autonomous mode – no human gates, passive Aletheia, faster healing cycle |

## Code style

- Python 3.11+
- Type hints on public functions
- `pytest` + `pytest-asyncio` for tests

## Pull requests

1. Fork the repo and create a feature branch from `main`.
2. Ensure all tests pass: `pytest tests/ -v`
3. Open a PR against `main`.
