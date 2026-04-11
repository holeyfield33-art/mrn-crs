"""Consensus frame management service."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from src.clients.aletheia_client import AletheiaClient
from src.core.models import ConsensusFrame, ConsensusStatus, EvidenceEntry

logger = logging.getLogger(__name__)

# In-memory store – replace with Mneme persistence in production
_frames: dict[str, ConsensusFrame] = {}


def get_frame(frame_id: str) -> ConsensusFrame | None:
    return _frames.get(frame_id)


def create_frame(competing_steps: list[str]) -> ConsensusFrame:
    frame = ConsensusFrame(competing_steps=competing_steps)
    _frames[frame.frame_id] = frame
    return frame


async def add_evidence(
    frame_id: str,
    step_id: str,
    summary: str,
    confidence: float,
    *,
    aletheia: AletheiaClient,
) -> ConsensusFrame:
    frame = _frames.get(frame_id)
    if frame is None:
        raise KeyError(f"Frame {frame_id} not found")

    # Audit the evidence addition
    try:
        audit = await aletheia.audit_action(
            "consensus_evidence",
            {"frame_id": frame_id, "step_id": step_id, "summary": summary},
        )
        if audit.get("decision") == "DENY":
            raise PermissionError("Aletheia denied consensus evidence update")
    except httpx.HTTPError as exc:
        logger.warning("Aletheia unreachable during consensus update: %s", exc)

    entry = EvidenceEntry(step_id=step_id, summary=summary, confidence=confidence)
    frame.evidence_log.append(entry)
    frame.confidence_trajectory.append(confidence)
    frame.updated_at = datetime.utcnow()

    # Auto-resolve when confidence converges above 0.9
    if len(frame.confidence_trajectory) >= 3:
        recent = frame.confidence_trajectory[-3:]
        if all(c >= 0.9 for c in recent):
            frame.status = ConsensusStatus.RESOLVED
            frame.resolution = f"Auto-resolved via high-confidence evidence from step {step_id}"

    _frames[frame_id] = frame
    return frame
