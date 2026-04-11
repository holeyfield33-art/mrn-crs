"""SHA-256 fingerprint generation for reasoning steps."""

from __future__ import annotations

import hashlib


def compute_fingerprint(premise: str, conclusion: str, agent_id: str) -> str:
    """Return a deterministic SHA-256 hex digest for the given fields."""
    payload = f"{agent_id}:{premise}:{conclusion}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
