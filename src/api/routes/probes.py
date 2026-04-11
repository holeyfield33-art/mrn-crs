"""Readiness & liveness probe endpoints."""

from __future__ import annotations

import httpx
from fastapi import APIRouter

from src.config import settings

router = APIRouter(tags=["probes"])


@router.get("/live")
async def liveness():
    """Always returns 200 if the process is alive."""
    return {"status": "alive"}


@router.get("/ready")
async def readiness():
    """Returns 200 with downstream health status.

    If any downstream service is unreachable, ``degraded`` is ``true``
    but the probe still returns 200 (graceful degradation).
    """
    services: dict[str, str] = {}
    for name, url in [
        ("aletheia", settings.aletheia_url),
        ("geometric", settings.geometric_url),
        ("mneme", settings.mneme_url),
    ]:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(3.0)) as client:
                resp = await client.get(f"{url.rstrip('/')}/health")
                services[name] = "ok" if resp.is_success else f"status_{resp.status_code}"
        except Exception:
            services[name] = "unreachable"

    degraded = any(v != "ok" for v in services.values())
    return {"status": "ready", "degraded": degraded, "services": services}
