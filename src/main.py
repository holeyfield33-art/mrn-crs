"""FastAPI application entry point with production hardening."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.api.dependencies import get_aletheia, get_geometric, get_mneme, verify_api_key
from src.api.metrics import crs_requests_total
from src.api.routes import consensus, health, probes, reason, trace
from src.config import settings
from src.services.self_healing import SelfHealingLoop

# --------------------------------------------------------------------------- #
# Structured JSON logging
# --------------------------------------------------------------------------- #

try:
    from pythonjsonlogger.json import JsonFormatter  # type: ignore[import-untyped]

    _handler = logging.StreamHandler()
    _handler.setFormatter(JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
    ))
    logging.root.handlers = [_handler]
except ImportError:
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

logging.root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Rate limiter (in-memory; Redis backend when REDIS_URL is set)
# --------------------------------------------------------------------------- #


def _key_func(request: Request) -> str:
    """Use API key prefix if present, otherwise client IP."""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer ") and len(auth) > 15:
        return auth[7:15]
    return get_remote_address(request)


limiter = Limiter(
    key_func=_key_func,
    default_limits=[f"{settings.crs_rate_limit_per_minute}/minute"],
    storage_uri=settings.redis_url or "memory://",
)

# Paths exempt from auth
_PUBLIC_PATHS = {"/health", "/live", "/ready", "/metrics", "/openapi.json", "/docs", "/redoc"}


# --------------------------------------------------------------------------- #
# Lifespan
# --------------------------------------------------------------------------- #


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the self-healing background task on startup; cancel on shutdown."""
    heal_task: asyncio.Task[None] | None = None
    loop: SelfHealingLoop | None = None

    if settings.enable_self_healing:
        logger.info("Starting self-healing background loop")
        loop = SelfHealingLoop(
            mneme=get_mneme(),
            geometric=get_geometric(),
            aletheia=get_aletheia(),
            interval_seconds=settings.self_heal_interval_seconds,
            drift_threshold=settings.self_heal_drift_threshold,
            healthy_r_min=settings.self_heal_healthy_r_min,
            healthy_r_max=settings.self_heal_healthy_r_max,
            healthy_shi_min=settings.self_heal_healthy_shi_min,
            min_memories=settings.self_heal_min_memories,
            level_low=settings.self_heal_level_low,
            level_medium=settings.self_heal_level_medium,
            level_high=settings.self_heal_level_high,
            escalation_webhook=settings.self_heal_escalation_webhook,
            escalation_file=settings.self_heal_escalation_file,
            healing_history_db=settings.healing_history_db,
        )
        heal_task = asyncio.create_task(loop.run())
        app.state.self_healing_loop = loop
        app.state.self_healing_task = heal_task

    yield

    # Graceful shutdown
    if loop is not None:
        loop.stop()
    if heal_task is not None:
        heal_task.cancel()
        try:
            await heal_task
        except asyncio.CancelledError:
            logger.info("Self-healing loop stopped")


# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #

app = FastAPI(
    title="MRN Constrained Reasoning System",
    version="1.1.0",
    description="Orchestrates reasoning steps, consensus frames, and geometric self-healing with entropy monitoring and four-tier freeze logic.",
    lifespan=lifespan,
)
app.state.limiter = limiter


# Rate-limit error handler
@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})


# --------------------------------------------------------------------------- #
# Middleware: request logging, auth, and metrics
# --------------------------------------------------------------------------- #


@app.middleware("http")
async def request_middleware(request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    start = time.monotonic()

    # Auth check (skip public paths)
    if request.url.path not in _PUBLIC_PATHS:
        try:
            client_id = await verify_api_key(request)
        except Exception as exc:
            # Re-raise as 401 JSON
            from fastapi import HTTPException as _H
            if isinstance(exc, _H):
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                    headers=getattr(exc, "headers", None) or {},
                )
            raise
    else:
        client_id = None

    response: Response = await call_next(request)
    latency = time.monotonic() - start

    # Structured log
    logger.info(
        "request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "latency_ms": round(latency * 1000, 1),
            "client_id": client_id or "anon",
            "request_id": request_id,
        },
    )

    # Prometheus counter
    crs_requests_total.labels(
        endpoint=request.url.path,
        status=str(response.status_code),
        client=client_id or "anon",
    ).inc()

    response.headers["x-request-id"] = request_id
    return response


# --------------------------------------------------------------------------- #
# Prometheus Instrumentator (adds /metrics endpoint)
# --------------------------------------------------------------------------- #

Instrumentator(
    excluded_handlers=["/metrics", "/live", "/ready"],
).instrument(app).expose(app, endpoint="/metrics")

# --------------------------------------------------------------------------- #
# Register routers
# --------------------------------------------------------------------------- #

app.include_router(reason.router)
app.include_router(trace.router)
app.include_router(consensus.router)
app.include_router(health.router)
app.include_router(probes.router)
