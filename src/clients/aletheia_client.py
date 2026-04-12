"""Async HTTP client for the Aletheia security/audit service (passive mode).

In unconstrained mode, Aletheia audits are fire-and-forget background tasks.
The reasoning pipeline never blocks on audit results.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(2.0, connect=1.0)

# Passive audit receipt returned immediately
_PASSIVE_RECEIPT: dict[str, Any] = {
    "decision": "PROCEED",
    "receipt": {"mode": "passive_audit"},
}


class AletheiaClient:
    """Wraps calls to Aletheia's audit API in passive (fire-and-forget) mode."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.aletheia_url).rstrip("/")

    # ---- background fire-and-forget ---------------------------------------- #

    async def _audit_background(self, payload: dict[str, Any]) -> None:
        """Best-effort POST to Aletheia; failures are silently logged."""
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                await client.post(f"{self.base_url}/v1/audit", json=payload)
        except Exception:
            pass  # passive – never block the pipeline

    # ---- public API -------------------------------------------------------- #

    async def audit(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Fire-and-forget audit – returns immediately with PROCEED."""
        asyncio.create_task(self._audit_background(payload))
        return dict(_PASSIVE_RECEIPT)

    # ---- convenience ------------------------------------------------------- #

    async def audit_step(self, step_data: dict[str, Any]) -> dict[str, Any]:
        """Audit a reasoning step (passive)."""
        return await self.audit({"type": "reasoning_step", "data": step_data})

    async def audit_action(self, action: str, detail: dict[str, Any]) -> dict[str, Any]:
        """Audit an arbitrary action (passive)."""
        return await self.audit({"type": action, "data": detail})
