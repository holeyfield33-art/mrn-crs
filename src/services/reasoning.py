"""Reasoning step storage – the main orchestration logic behind POST /reason."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.api.metrics import crs_client_call_duration_seconds
from src.clients.aletheia_client import AletheiaClient
from src.clients.geometric_client import GeometricClient
from src.clients.mneme_client import MnemeClient
from src.core.embedding import embed_text
from src.core.fingerprint import compute_fingerprint
from src.core.models import (
    JSONLDStep,
    ReasonRequest,
    ReasonResponse,
    Receipt,
    SpectralSignature,
)
from src.core.spectral_utils import local_spectral_signature

logger = logging.getLogger(__name__)


class PolicyDenied(Exception):
    """Raised when Aletheia denies the reasoning step."""

    def __init__(self, receipt: dict[str, Any]) -> None:
        self.receipt = receipt
        super().__init__("Aletheia audit denied this step")


class HumanEscalation(Exception):
    """Raised when the Geometric Brain requires human escalation."""

    def __init__(self, detail: dict[str, Any]) -> None:
        self.detail = detail
        super().__init__("Geometric health-check requires human escalation")


async def store_reasoning_step(
    req: ReasonRequest,
    *,
    aletheia: AletheiaClient,
    geometric: GeometricClient,
    mneme: MnemeClient,
) -> ReasonResponse:
    """Full pipeline: audit → health-check → embed → spectral → store → respond."""

    # 1. Build the step
    step = JSONLDStep(
        agent_id=req.agent_id,
        premise=req.premise,
        inference_type=req.inference_type,
        conclusion=req.conclusion,
        confidence=req.confidence,
        depends_on=req.depends_on,
        epistemic_value=req.epistemic_value,
    )

    # 2. Compute fingerprint (if caller didn't supply one)
    fp = req.fingerprint or compute_fingerprint(req.premise, req.conclusion, req.agent_id)
    step.fingerprint = fp

    receipts: list[Receipt] = []

    # 3. Aletheia audit
    try:
        with crs_client_call_duration_seconds.labels(service="aletheia").time():
            audit_resp = await aletheia.audit_step(step.model_dump(mode="json"))
        decision = audit_resp.get("decision", "PROCEED")
        if decision == "DENIED":
            raise PolicyDenied(audit_resp)
        receipt = audit_resp.get("receipt", {})
        receipt_id = receipt.get("decision_token") or receipt.get("id", "n/a")
        receipts.append(
            Receipt(
                service="aletheia",
                receipt_id=receipt_id,
                detail=decision,
            )
        )
    except httpx.HTTPError as exc:
        logger.warning("Aletheia unreachable – proceeding without audit: %s", exc)
        receipts.append(Receipt(service="aletheia", receipt_id="unavailable", detail="service_down"))

    # 4. Geometric Brain health-check
    combined_text = f"{req.premise} → {req.conclusion}"
    try:
        with crs_client_call_duration_seconds.labels(service="geometric").time():
            health = await geometric.health_check(combined_text)
        if health.get("human_escalation"):
            raise HumanEscalation(health)
    except httpx.HTTPError as exc:
        logger.warning("Geometric Brain unreachable – skipping health-check: %s", exc)

    # 5. Compute embedding
    embedding = embed_text(combined_text)
    embedding_list = embedding.tolist()

    # 6. Spectral signature (try Geometric Brain, fall back to local)
    spectral: SpectralSignature | None = None
    try:
        with crs_client_call_duration_seconds.labels(service="geometric").time():
            manifold = await geometric.manifold_audit(embedding_list)
        spectral = SpectralSignature(**manifold)
    except Exception:
        logger.info("Using local spectral fallback")
        spectral = local_spectral_signature(embedding)

    # 7. Store in Mneme
    try:
        with crs_client_call_duration_seconds.labels(service="mneme").time():
            store_resp = await mneme.store_with_geo_index(
                payload=step.model_dump(mode="json"),
                embedding=embedding_list,
                spectral=spectral.model_dump(),
            )
        receipts.append(
            Receipt(
                service="mneme",
                receipt_id=store_resp.get("receipt", {}).get("id", store_resp.get("id", "n/a")),
                detail="stored",
            )
        )
    except httpx.HTTPError as exc:
        logger.warning("Mneme unreachable – step not persisted: %s", exc)
        receipts.append(Receipt(service="mneme", receipt_id="unavailable", detail="service_down"))

    return ReasonResponse(
        step_id=step.step_id,
        fingerprint=fp,
        receipts=receipts,
        spectral=spectral,
    )
