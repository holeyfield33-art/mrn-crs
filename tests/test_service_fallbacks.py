"""Tests for service-down fallback paths and Tier-4 freeze logic."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import get_aletheia, get_geometric, get_mneme
from src.main import app
from src.services.self_healing import SelfHealingLoop, _GOLDEN_R, healthy_context_buffer


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #

SAMPLE_STEP = {
    "agent_id": "agent-test",
    "premise": "All humans are mortal",
    "inference_type": "deductive",
    "conclusion": "Socrates is mortal",
    "confidence": 0.95,
}


def _mock_aletheia_allow():
    m = AsyncMock()
    m.audit_step.return_value = {"decision": "PROCEED", "receipt": {"decision_token": "a-ok-1"}}
    return m


def _mock_aletheia_down():
    m = AsyncMock()
    m.audit_step.side_effect = httpx.ConnectError("unreachable")
    return m


def _mock_geometric_healthy():
    m = AsyncMock()
    m.health_check.return_value = {"healthy": True, "human_escalation": False, "shi": 0.92}
    m.manifold_audit.return_value = {"r_ratio": 0.58, "shi": 0.94, "unitarity_check": True}
    return m


def _mock_geometric_down():
    m = AsyncMock()
    m.health_check.side_effect = httpx.ConnectError("unreachable")
    m.manifold_audit.side_effect = httpx.ConnectError("unreachable")
    return m


def _mock_mneme():
    m = AsyncMock()
    m.store_with_geo_index.return_value = {"id": "mem-1", "receipt": {"id": "m-receipt-1"}}
    return m


def _mock_mneme_down():
    m = AsyncMock()
    m.store_with_geo_index.side_effect = httpx.ConnectError("unreachable")
    return m


def _diverse_embeddings(n: int = 10, dim: int = 384) -> list[list[float]]:
    rng = np.random.default_rng(42)
    return [rng.standard_normal(dim).tolist() for _ in range(n)]


@pytest.fixture(autouse=True)
def _reset_globals():
    import src.services.self_healing as mod
    healthy_context_buffer.clear()
    mod.sampling_temperature = 0.7
    yield
    healthy_context_buffer.clear()
    mod.sampling_temperature = 0.7


@pytest.fixture
def tmp_db(tmp_path):
    return str(tmp_path / "test_heal.db")


@pytest.fixture
def tmp_escalation(tmp_path):
    return str(tmp_path / "test_esc.jsonl")


def _make_loop(
    geo: AsyncMock,
    mneme: AsyncMock,
    aletheia: AsyncMock,
    *,
    healing_history_db: str = "healing_history.db",
    escalation_file: str = "escalations.jsonl",
    min_memories: int = 1,
) -> SelfHealingLoop:
    return SelfHealingLoop(
        mneme=mneme,
        geometric=geo,
        aletheia=aletheia,
        interval_seconds=1,
        min_memories=min_memories,
        healing_history_db=healing_history_db,
        escalation_file=escalation_file,
    )


# --------------------------------------------------------------------------- #
# reasoning.py – service-down fallback paths
# --------------------------------------------------------------------------- #


def test_aletheia_unreachable_proceeds():
    """When Aletheia is down the step still succeeds with receipt_id='unavailable'."""
    app.dependency_overrides[get_aletheia] = _mock_aletheia_down
    app.dependency_overrides[get_geometric] = _mock_geometric_healthy
    app.dependency_overrides[get_mneme] = _mock_mneme
    try:
        with TestClient(app) as client:
            resp = client.post("/reason", json=SAMPLE_STEP)
        assert resp.status_code == 200
        receipts = resp.json()["receipts"]
        aletheia_receipt = next(r for r in receipts if r["service"] == "aletheia")
        assert aletheia_receipt["receipt_id"] == "unavailable"
        assert aletheia_receipt["detail"] == "service_down"
    finally:
        app.dependency_overrides.clear()


def test_geometric_unreachable_proceeds():
    """When Geometric Brain is down the step still succeeds (no escalation raised)."""
    app.dependency_overrides[get_aletheia] = _mock_aletheia_allow
    app.dependency_overrides[get_geometric] = _mock_geometric_down
    app.dependency_overrides[get_mneme] = _mock_mneme
    try:
        with TestClient(app) as client:
            resp = client.post("/reason", json=SAMPLE_STEP)
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_mneme_unreachable_proceeds():
    """When Mneme is down the step still returns 200 with receipt_id='unavailable'."""
    app.dependency_overrides[get_aletheia] = _mock_aletheia_allow
    app.dependency_overrides[get_geometric] = _mock_geometric_healthy
    app.dependency_overrides[get_mneme] = _mock_mneme_down
    try:
        with TestClient(app) as client:
            resp = client.post("/reason", json=SAMPLE_STEP)
        assert resp.status_code == 200
        receipts = resp.json()["receipts"]
        mneme_receipt = next(r for r in receipts if r["service"] == "mneme")
        assert mneme_receipt["receipt_id"] == "unavailable"
        assert mneme_receipt["detail"] == "service_down"
    finally:
        app.dependency_overrides.clear()


def test_caller_supplied_fingerprint():
    """A fingerprint provided in the request body is echoed back unchanged."""
    app.dependency_overrides[get_aletheia] = _mock_aletheia_allow
    app.dependency_overrides[get_geometric] = _mock_geometric_healthy
    app.dependency_overrides[get_mneme] = _mock_mneme
    supplied_fp = "deadbeef1234567890abcdef"
    try:
        with TestClient(app) as client:
            resp = client.post("/reason", json={**SAMPLE_STEP, "fingerprint": supplied_fp})
        assert resp.status_code == 200
        assert resp.json()["fingerprint"] == supplied_fp
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# self_healing.py – Tier-4 structural collapse freeze
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_freeze_on_structural_collapse(tmp_db, tmp_escalation):
    """Highly correlated embeddings produce a low Fibonacci score → STRUCTURAL_COLLAPSE."""
    geo, mneme, aletheia = AsyncMock(), AsyncMock(), AsyncMock()

    # Near-identical embeddings with tiny noise → very low covariance eigenvalue spread
    rng = np.random.default_rng(0)
    base = rng.standard_normal(384)
    correlated = [(base + rng.standard_normal(384) * 0.001).tolist() for _ in range(10)]

    mneme.geometric_search_by_spectral.return_value = [{"embedding": e} for e in correlated]
    # Drift is healthy so Tiers 1–3 won't trigger; only Tier 4 (Fibonacci) can fire
    geo.self_heal.return_value = {"self_heal_needed": False, "current_r": _GOLDEN_R}
    aletheia.audit_step.return_value = {"decision": "ALLOW"}

    loop = _make_loop(geo, mneme, aletheia, healing_history_db=tmp_db, escalation_file=tmp_escalation)

    # Patch entropy to a healthy value so only Tier 4 is reachable
    with patch("src.services.self_healing.compute_entropy_from_embeddings", return_value=1.5):
        await loop._run_cycle()

    assert loop.frozen is True
    manifest_path = Path("freeze_manifest.json")
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["reason"] == "STRUCTURAL_COLLAPSE"
    manifest_path.unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# self_healing.py – Aletheia unreachable during cycle audit
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_aletheia_unreachable_in_cycle_continues(tmp_db):
    """If Aletheia is down during a healing cycle the cycle still completes."""
    geo, mneme, aletheia = AsyncMock(), AsyncMock(), AsyncMock()

    embs = _diverse_embeddings(10)
    mneme.geometric_search_by_spectral.side_effect = [
        [{"embedding": e} for e in embs],
        [{"id": "h1"}],
    ]
    geo.self_heal.return_value = {"self_heal_needed": True, "current_r": _GOLDEN_R + 0.03}
    aletheia.audit_step.side_effect = httpx.ConnectError("unreachable")

    loop = _make_loop(geo, mneme, aletheia, healing_history_db=tmp_db)
    # Should not raise
    await loop._run_cycle()

    # Healing history is still recorded despite Aletheia being down
    events = loop.history.recent(limit=10)
    assert len(events) == 1
    assert events[0]["level"] == "low"
