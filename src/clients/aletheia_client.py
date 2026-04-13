"""Async HTTP client for the Aletheia security/audit service."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


class AletheiaClient:
    """Wraps calls to Aletheia's audit API."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        self.base_url = (base_url or settings.aletheia_url).rstrip("/")
        self._api_key = api_key or settings.aletheia_api_key

    # ---- public API -------------------------------------------------------- #

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=0.3, max=2), reraise=True)
    async def audit(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /v1/audit – returns ``{"decision": "ALLOW"|"DENY", ...}``."""
        url = f"{self.base_url}/v1/audit"
        headers = {}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()

    # ---- convenience ------------------------------------------------------- #

    async def audit_step(self, step_data: dict[str, Any]) -> dict[str, Any]:
        """Audit a reasoning step and return the full response."""
        return await self.audit({
            "payload": json.dumps(step_data, default=str)[:10000],
            "origin": "crs",
            "action": "reasoning_step",
        })

    async def audit_action(self, action: str, detail: dict[str, Any]) -> dict[str, Any]:
        """Audit an arbitrary action (e.g. self-healing)."""
        return await self.audit({
            "payload": json.dumps(detail, default=str)[:10000],
            "origin": "crs",
            "action": action,
        })
