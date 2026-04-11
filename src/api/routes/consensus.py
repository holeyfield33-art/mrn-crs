"""Consensus frame endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import get_aletheia
from src.clients.aletheia_client import AletheiaClient
from src.core.models import ConsensusCreateRequest, ConsensusFrame, ConsensusUpdateRequest
from src.services.consensus import add_evidence, create_frame, get_frame

router = APIRouter(prefix="/consensus", tags=["consensus"])


@router.post("/frame", response_model=ConsensusFrame)
async def create_consensus_frame(req: ConsensusCreateRequest):
    """Create a new consensus frame with competing step IDs."""
    return create_frame(req.competing_steps)


@router.post("/update", response_model=ConsensusFrame)
async def update_consensus_frame(
    req: ConsensusUpdateRequest,
    aletheia: AletheiaClient = Depends(get_aletheia),
):
    """Add evidence to an existing consensus frame (audited via Aletheia)."""
    try:
        return await add_evidence(
            frame_id=req.frame_id,
            step_id=req.step_id,
            summary=req.summary,
            confidence=req.confidence,
            aletheia=aletheia,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Consensus frame {req.frame_id} not found")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/{frame_id}", response_model=ConsensusFrame)
async def get_consensus_frame(frame_id: str):
    """Retrieve a consensus frame by ID."""
    frame = get_frame(frame_id)
    if frame is None:
        raise HTTPException(status_code=404, detail=f"Consensus frame {frame_id} not found")
    return frame
