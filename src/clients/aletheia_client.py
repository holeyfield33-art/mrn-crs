"""Async HTTP client for the Aletheia security/audit service."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


class AletheiaClient:
    """Wraps calls to Aletheia's audit API."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.aletheia_url).rstrip("/")

    # ---- public API -------------------------------------------------------- #

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=0.3, max=2), reraise=True)
    async def audit(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /v1/audit – returns ``{"decision": "ALLOW"|"DENY", "receipt": ...}``."""
        url = f"{self.base_url}/v1/audit"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()

    # ---- convenience ------------------------------------------------------- #

    async def audit_step(self, step_data: dict[str, Any]) -> dict[str, Any]:
        """Audit a reasoning step and return the full response."""
        return await self.audit({"type": "reasoning_step", "data": step_data})

    async def audit_action(self, action: str, detail: dict[str, Any]) -> dict[str, Any]:
        """Audit an arbitrary action (e.g. self-healing)."""
        return await self.audit({"type": action, "data": detail})
