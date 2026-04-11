"""Async HTTP client for the Geometric Brain spectral/manifold service."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


class GeometricClient:
    """Wraps calls to the Geometric Brain API."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.geometric_url).rstrip("/")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=0.3, max=2), reraise=True)
    async def health_check(self, text: str) -> dict[str, Any]:
        """POST /v1/brain/health-check – check if text is geometrically healthy.

        Expected response::

            {"healthy": true/false, "human_escalation": false, "shi": 0.92, ...}
        """
        url = f"{self.base_url}/v1/brain/health-check"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json={"text": text})
            resp.raise_for_status()
            return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=0.3, max=2), reraise=True)
    async def self_heal(
        self, embeddings: list[list[float]], *, current_r: float = 0.5,
    ) -> dict[str, Any]:
        """POST /v1/brain/self-heal – request geometric drift correction.

        Expected response::

            {"self_heal_needed": true/false, "corrections": [...], "correction": {...}}
        """
        url = f"{self.base_url}/v1/brain/self-heal"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                url, json={"embeddings": embeddings, "current_r": current_r},
            )
            resp.raise_for_status()
            return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=0.3, max=2), reraise=True)
    async def manifold_audit(self, embedding: list[float]) -> dict[str, Any]:
        """POST /v1/brain/manifold-audit – get spectral signature for an embedding.

        Expected response::

            {"r_ratio": 0.58, "shi": 0.94, "unitarity_check": true}
        """
        url = f"{self.base_url}/v1/brain/manifold-audit"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json={"embedding": embedding})
            resp.raise_for_status()
            return resp.json()
