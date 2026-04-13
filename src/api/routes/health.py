"""GET /health – service health check."""

from __future__ import annotations

import httpx
from fastapi import APIRouter

from src.config import settings
from src.core.models import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health():
    """Return service status and reachability of downstream services."""
    services: dict[str, str] = {}
    for name, url in [
        ("aletheia", settings.aletheia_url),
        ("geometric", settings.geometric_url),
        ("mneme", settings.mneme_url),
    ]:
        try:
            base = url.rstrip("/")
            async with httpx.AsyncClient(timeout=httpx.Timeout(3.0)) as client:
                resp = await client.get(f"{base}/health")
                if not resp.is_success:
                    # fallback for services that use /healthz (e.g. geometric-brain)
                    resp = await client.get(f"{base}/healthz")
                services[name] = "ok" if resp.is_success else f"status_{resp.status_code}"
        except Exception:
            services[name] = "unreachable"

    return HealthResponse(
        status="ok",
        self_healing_active=settings.enable_self_healing,
        services=services,
    )
