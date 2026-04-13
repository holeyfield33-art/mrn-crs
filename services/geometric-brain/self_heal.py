"""CRS adapter: adds /v1/brain/self-heal endpoint to geometric-brain-mcp.

This router composes existing spectral_engine functions (manifold_audit +
compute_correction) into the single endpoint the CRS self-healing loop expects.
"""

from __future__ import annotations

import uuid
from typing import Any

import numpy as np
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

# Upstream geometric-brain-mcp modules (available at runtime)
from spectral_engine import manifold_audit, compute_correction  # type: ignore[import-untyped]
from config import SCHEMA_VERSION  # type: ignore[import-untyped]

router = APIRouter()

# GUE golden-ratio reference r
_GUE_R = 0.578


class SelfHealRequest(BaseModel):
    embeddings: list[list[float]] = Field(..., min_length=1)
    current_r: float = Field(default=0.5)


def _request_id(request: Request) -> str:
    return request.headers.get("x-request-id", str(uuid.uuid4()))


@router.post("/v1/brain/self-heal")
async def self_heal_endpoint(request: Request, req: SelfHealRequest) -> dict[str, Any]:
    """Analyse a batch of embeddings for geometric drift and compute corrections.

    Request body::

        {"embeddings": [[0.1, ...], ...], "current_r": 0.5}

    Response::

        {"self_heal_needed": true, "current_r": 0.58, "correction": {...}, ...}
    """
    mat = np.array(req.embeddings, dtype=np.float64)

    # Derive eigenvalues from the covariance matrix of the embedding batch
    if mat.shape[0] >= 2:
        cov = np.cov(mat, rowvar=True)
        eigenvalues = np.linalg.eigvalsh(cov).tolist()
    else:
        eigenvalues = mat.flatten().tolist()

    # Run upstream manifold_audit with eigenvalues
    audit: dict[str, Any] = manifold_audit(
        source_type="eigenvalues",
        eigenvalues=eigenvalues,
    )

    measured_r = audit.get("mean_r_ratio", audit.get("r_ratio", req.current_r))
    shi = audit.get("spectral_health_index", audit.get("shi", 50.0))
    regime = audit.get("spectral_regime", "intermediate")

    # Determine if healing is needed
    drift = abs(measured_r - _GUE_R)
    self_heal_needed = drift > 0.05 or regime == "poisson_like"

    # Compute correction via upstream helper
    correction: dict[str, Any] = {}
    if self_heal_needed:
        corr = compute_correction(current_r_ratio=measured_r)
        correction = {
            "delta": corr.get("delta", 0.0),
            "direction": corr.get("direction", "none"),
            "recommended_action": corr.get("recommended_action", "none"),
            "retrieve_shi_above": max(0.5, (shi / 100.0) * 0.8),
        }

    return {
        "self_heal_needed": self_heal_needed,
        "current_r": measured_r,
        "correction": correction,
        "spectral_health_index": shi,
        "regime": regime,
        "drift": drift,
        "schema_version": SCHEMA_VERSION,
        "request_id": _request_id(request),
    }
