# Installation

## Requirements

| Tool | Version | Notes |
| --- | --- | --- |
| Docker | 20.10+ | [Install guide](https://docs.docker.com/get-docker/) |
| Docker Compose | v2+ | Bundled with Docker Desktop; on Linux install the `docker-compose-plugin` |

No other software, language runtimes, or separate repositories are needed.

## Steps

```bash
# Clone
git clone https://github.com/holeyfield33/mrn-constrained-crs.git
cd mrn-constrained-crs

# Create your environment file
cp .env.example .env
```

Edit `.env` to change any secrets or defaults. The file is pre-populated with
working defaults so you can skip this for local development.

### What gets pulled automatically

| Service | Image | Port |
| --- | --- | --- |
| Aletheia | `holeyfield33/aletheia-core:1.6.2` | 8300 |
| Geometric Brain | `holeyfield33/geometric-brain:latest` | 8200 |
| Mneme | `holeyfield33/mneme:latest` | 8100 |
| Postgres (pgvector) | `pgvector/pgvector:pg16` | 5432 |
| Redis | `redis:7-alpine` | 6379 |

The CRS service is built from the local `Dockerfile` on first run.

## Start the stack

```bash
docker compose up --build
```

First run downloads ~2 GB of images. Subsequent starts are near-instant.

## Verify

```bash
curl http://localhost:8000/health
# {"status": "ok", ...}
```

## Stopping

```bash
docker compose down          # stop containers
docker compose down -v       # stop and remove Postgres data volume
```
