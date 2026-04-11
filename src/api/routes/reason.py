"""POST /reason – store a new reasoning step through the full pipeline."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import get_aletheia, get_geometric, get_mneme
from src.clients.aletheia_client import AletheiaClient
from src.clients.geometric_client import GeometricClient
from src.clients.mneme_client import MnemeClient
from src.core.models import ReasonRequest, ReasonResponse
from src.services.reasoning import HumanEscalation, PolicyDenied, store_reasoning_step

router = APIRouter(tags=["reasoning"])


@router.post("/reason", response_model=ReasonResponse)
async def reason(
    req: ReasonRequest,
    aletheia: AletheiaClient = Depends(get_aletheia),
    geometric: GeometricClient = Depends(get_geometric),
    mneme: MnemeClient = Depends(get_mneme),
) -> ReasonResponse:
    """Accept a reasoning step, audit it, compute spectral data, and store it."""
    try:
        return await store_reasoning_step(
            req,
            aletheia=aletheia,
            geometric=geometric,
            mneme=mneme,
        )
    except PolicyDenied as exc:
        raise HTTPException(status_code=403, detail={"message": str(exc), "receipt": exc.receipt})
    except HumanEscalation as exc:
        raise HTTPException(status_code=423, detail={"message": str(exc), "detail": exc.detail})
