"""GET /trace – retrieve reasoning steps by fingerprint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.dependencies import get_mneme
from src.clients.mneme_client import MnemeClient
from src.core.embedding import embed_text

router = APIRouter(tags=["trace"])


@router.get("/trace")
async def trace(
    fingerprint: str = Query(..., description="SHA-256 fingerprint of the reasoning step"),
    mneme: MnemeClient = Depends(get_mneme),
):
    """Query Mneme via geometric search for steps matching *fingerprint*.

    Returns the latest non-superseded steps.
    """
    # Embed the fingerprint text for geometric search
    embedding = embed_text(fingerprint).tolist()
    try:
        results = await mneme.geometric_search(embedding, top_k=20)
    except Exception:
        # Fallback: return empty if Mneme is unreachable
        results = []

    # Filter: match fingerprint, exclude superseded
    matched = [
        r
        for r in results
        if r.get("fingerprint") == fingerprint and r.get("superseded_by") is None
    ]

    if not matched:
        raise HTTPException(status_code=404, detail="No active steps found for this fingerprint")

    return {"fingerprint": fingerprint, "steps": matched}
