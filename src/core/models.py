"""Pydantic data models for the MRN Constrained Reasoning System."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #


class InferenceType(str, Enum):
    DEDUCTIVE = "deductive"
    INDUCTIVE = "inductive"
    ABDUCTIVE = "abductive"
    ANALOGICAL = "analogical"
    BAYESIAN = "bayesian"


class ConsensusStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


# --------------------------------------------------------------------------- #
# JSON-LD Reasoning Step
# --------------------------------------------------------------------------- #


class JSONLDStep(BaseModel):
    """A single reasoning step in JSON-LD compatible form."""

    step_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    premise: str
    inference_type: InferenceType
    conclusion: str
    confidence: float = Field(ge=0.0, le=1.0)
    depends_on: list[str] = Field(default_factory=list)
    fingerprint: Optional[str] = None
    epistemic_value: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    superseded_by: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# --------------------------------------------------------------------------- #
# Consensus Frame
# --------------------------------------------------------------------------- #


class EvidenceEntry(BaseModel):
    """One piece of evidence attached to a consensus frame."""

    step_id: str
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    added_at: datetime = Field(default_factory=datetime.utcnow)


class ConsensusFrame(BaseModel):
    """A consensus frame tracking competing reasoning steps."""

    frame_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    competing_steps: list[str] = Field(default_factory=list)
    status: ConsensusStatus = ConsensusStatus.OPEN
    resolution: Optional[str] = None
    evidence_log: list[EvidenceEntry] = Field(default_factory=list)
    confidence_trajectory: list[float] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# --------------------------------------------------------------------------- #
# Spectral / Geometric metadata
# --------------------------------------------------------------------------- #


class SpectralSignature(BaseModel):
    """Geometric Brain spectral metrics for a reasoning step."""

    r_ratio: float
    shi: float  # Spectral Health Index
    unitarity_check: bool = True


# --------------------------------------------------------------------------- #
# API request / response schemas
# --------------------------------------------------------------------------- #


class ReasonRequest(BaseModel):
    """POST /reason request body."""

    agent_id: str
    premise: str
    inference_type: InferenceType
    conclusion: str
    confidence: float = Field(ge=0.0, le=1.0)
    depends_on: list[str] = Field(default_factory=list)
    fingerprint: Optional[str] = None
    epistemic_value: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class Receipt(BaseModel):
    """A generic receipt returned by an external service."""

    service: str
    receipt_id: str
    detail: Optional[str] = None


class ReasonResponse(BaseModel):
    """POST /reason response body."""

    step_id: str
    fingerprint: str
    receipts: list[Receipt] = Field(default_factory=list)
    spectral: Optional[SpectralSignature] = None


class ConsensusCreateRequest(BaseModel):
    """POST /consensus/frame request."""

    competing_steps: list[str]


class ConsensusUpdateRequest(BaseModel):
    """POST /consensus/update request."""

    frame_id: str
    step_id: str
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)


class HealthResponse(BaseModel):
    """GET /health response."""

    status: str = "ok"
    self_healing_active: bool = False
    services: dict[str, str] = Field(default_factory=dict)

