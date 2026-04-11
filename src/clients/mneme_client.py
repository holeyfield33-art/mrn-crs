"""Async HTTP client for the Mneme memory service."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


class MnemeClient:
    """Wraps calls to the Mneme memory API."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.mneme_url).rstrip("/")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=0.3, max=2), reraise=True)
    async def store(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /memory/store – persist a memory entry.

        Returns ``{"id": ..., "receipt": ...}``.
        """
        url = f"{self.base_url}/memory/store"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=0.3, max=2), reraise=True)
    async def store_with_geo_index(
        self,
        payload: dict[str, Any],
        embedding: list[float],
        spectral: dict[str, Any],
    ) -> dict[str, Any]:
        """POST /memory/store with geometric index metadata."""
        body = {
            **payload,
            "embedding": embedding,
            "spectral": spectral,
        }
        return await self.store(body)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=0.3, max=2), reraise=True)
    async def geometric_search(
        self,
        embedding: list[float],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """POST /memory/geometric-search – nearest-neighbour search."""
        url = f"{self.base_url}/memory/geometric-search"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json={"embedding": embedding, "top_k": top_k})
            resp.raise_for_status()
            return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=0.3, max=2), reraise=True)
    async def get_receipt(self, memory_id: str) -> dict[str, Any]:
        """GET /memory/{id}/receipt – retrieve HMAC receipt for a stored memory."""
        url = f"{self.base_url}/memory/{memory_id}/receipt"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=0.3, max=2), reraise=True)
    async def recent_steps(self, limit: int = 100) -> list[dict[str, Any]]:
        """GET /memory/recent – fetch recently stored reasoning steps."""
        url = f"{self.base_url}/memory/recent"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params={"limit": limit})
            resp.raise_for_status()
            return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=0.3, max=2), reraise=True)
    async def geometric_search_by_spectral(
        self,
        *,
        r_min: float = 0.4,
        r_max: float = 0.7,
        shi_min: float = 0.0,
        top_k: int = 100,
    ) -> list[dict[str, Any]]:
        """POST /memory/geometric-search with spectral range filters."""
        url = f"{self.base_url}/memory/geometric-search"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                url,
                json={
                    "r_min": r_min,
                    "r_max": r_max,
                    "shi_min": shi_min,
                    "top_k": top_k,
                },
            )
            resp.raise_for_status()
            return resp.json()
