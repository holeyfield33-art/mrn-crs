"""Tests for unconstrained / autonomous-mode code paths."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import get_aletheia, get_geometric, get_mneme
from src.main import app
from src.services.self_healing import SelfHealingLoop, _GOLDEN_R, healthy_context_buffer


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #

def _mock_aletheia_deny():
    m = AsyncMock()
    m.audit_step.return_value = {"decision": "DENIED", "receipt": {"decision_token": "a-deny-1"}}
    return m


def _mock_aletheia_allow():
    m = AsyncMock()
    m.audit_step.return_value = {"decision": "PROCEED", "receipt": {"decision_token": "a-ok-1"}}
    return m


def _mock_geometric_escalate():
    m = AsyncMock()
    m.health_check.return_value = {"healthy": False, "human_escalation": True, "shi": 0.3}
    return m


def _mock_geometric_healthy():
    m = AsyncMock()
    m.health_check.return_value = {"healthy": True, "human_escalation": False, "shi": 0.92}
    m.manifold_audit.return_value = {"r_ratio": 0.58, "shi": 0.94, "unitarity_check": True}
    return m


def _mock_mneme():
    m = AsyncMock()
    m.store_with_geo_index.return_value = {"id": "mem-1", "receipt": {"id": "m-receipt-1"}}
    return m


SAMPLE_STEP = {
    "agent_id": "agent-test",
    "premise": "All humans are mortal",
    "inference_type": "deductive",
    "conclusion": "Socrates is mortal",
    "confidence": 0.95,
}


def _settings_mock(*, autonomous_mode: bool = False, enable_human_gates: bool = True):
    s = MagicMock()
    s.autonomous_mode = autonomous_mode
    s.enable_human_gates = enable_human_gates
    return s


import numpy as np


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
    enable_human_gates: bool = True,
    freeze_on_critical: bool = True,
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
        enable_human_gates=enable_human_gates,
        freeze_on_critical=freeze_on_critical,
        healing_history_db=healing_history_db,
        escalation_file=escalation_file,
    )


# --------------------------------------------------------------------------- #
# Reasoning – autonomous_mode bypasses policy denial
# --------------------------------------------------------------------------- #


def test_autonomous_mode_bypasses_policy_denial():
    """With autonomous_mode=True, a DENIED Aletheia decision still returns 200."""
    app.dependency_overrides[get_aletheia] = _mock_aletheia_deny
    app.dependency_overrides[get_geometric] = _mock_geometric_healthy
    app.dependency_overrides[get_mneme] = _mock_mneme
    try:
        with patch(
            "src.services.reasoning.settings",
            _settings_mock(autonomous_mode=True, enable_human_gates=True),
        ):
            with TestClient(app) as client:
                resp = client.post("/reason", json=SAMPLE_STEP)
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_constrained_mode_policy_denial_still_403():
    """Regression guard – autonomous_mode=False keeps the 403 behaviour."""
    app.dependency_overrides[get_aletheia] = _mock_aletheia_deny
    app.dependency_overrides[get_geometric] = _mock_geometric_healthy
    app.dependency_overrides[get_mneme] = _mock_mneme
    try:
        with patch(
            "src.services.reasoning.settings",
            _settings_mock(autonomous_mode=False, enable_human_gates=True),
        ):
            with TestClient(app) as client:
                resp = client.post("/reason", json=SAMPLE_STEP)
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Reasoning – enable_human_gates=False bypasses human escalation
# --------------------------------------------------------------------------- #


def test_no_human_gates_bypasses_escalation():
    """With enable_human_gates=False, human_escalation signal is ignored → 200."""
    app.dependency_overrides[get_aletheia] = _mock_aletheia_allow
    app.dependency_overrides[get_geometric] = _mock_geometric_escalate
    app.dependency_overrides[get_mneme] = _mock_mneme
    try:
        with patch(
            "src.services.reasoning.settings",
            _settings_mock(autonomous_mode=False, enable_human_gates=False),
        ):
            with TestClient(app) as client:
                resp = client.post("/reason", json=SAMPLE_STEP)
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_human_gates_on_escalation_still_423():
    """Regression guard – enable_human_gates=True keeps the 423 behaviour."""
    app.dependency_overrides[get_aletheia] = _mock_aletheia_allow
    app.dependency_overrides[get_geometric] = _mock_geometric_escalate
    app.dependency_overrides[get_mneme] = _mock_mneme
    try:
        with patch(
            "src.services.reasoning.settings",
            _settings_mock(autonomous_mode=False, enable_human_gates=True),
        ):
            with TestClient(app) as client:
                resp = client.post("/reason", json=SAMPLE_STEP)
        assert resp.status_code == 423
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Self-healing – freeze_on_critical=False skips freeze conditions
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_freeze_on_critical_false_skips_critical_collapse(tmp_db, tmp_escalation):
    """freeze_on_critical=False: identical embeddings (entropy < 0.25) do NOT freeze."""
    geo, mneme, aletheia = AsyncMock(), AsyncMock(), AsyncMock()

    identical = [[0.1] * 384] * 10
    mneme.geometric_search_by_spectral.return_value = [{"embedding": e} for e in identical]
    geo.self_heal.return_value = {"self_heal_needed": False, "current_r": _GOLDEN_R}
    aletheia.audit_step.return_value = {"decision": "ALLOW"}

    loop = _make_loop(
        geo, mneme, aletheia,
        freeze_on_critical=False,
        healing_history_db=tmp_db,
        escalation_file=tmp_escalation,
    )
    await loop._run_cycle()

    assert loop.frozen is False
    assert loop.enabled is True


@pytest.mark.asyncio
async def test_freeze_on_critical_false_skips_runaway_divergence(tmp_db, tmp_escalation):
    """freeze_on_critical=False: drift > 0.25 does NOT freeze the loop."""
    geo, mneme, aletheia = AsyncMock(), AsyncMock(), AsyncMock()

    embs = _diverse_embeddings(10)
    mneme.geometric_search_by_spectral.side_effect = [
        [{"embedding": e} for e in embs],
        [{"id": "h1"}],
    ]
    # drift = abs(0.878 - 0.578) = 0.30 > 0.25
    geo.self_heal.return_value = {"self_heal_needed": True, "current_r": _GOLDEN_R + 0.30}
    aletheia.audit_step.return_value = {"decision": "ALLOW"}

    loop = _make_loop(
        geo, mneme, aletheia,
        freeze_on_critical=False,
        healing_history_db=tmp_db,
        escalation_file=tmp_escalation,
    )
    await loop._run_cycle()

    assert loop.frozen is False


# --------------------------------------------------------------------------- #
# Self-healing – enable_human_gates=False skips escalate_to_human
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_no_human_gates_skips_escalation_action(tmp_db, tmp_escalation):
    """enable_human_gates=False: high drift does NOT write an escalation file entry."""
    geo, mneme, aletheia = AsyncMock(), AsyncMock(), AsyncMock()

    embs = _diverse_embeddings(10)
    mneme.geometric_search_by_spectral.side_effect = [
        [{"embedding": e} for e in embs],
        [{"id": "h1"}],
    ]
    # high drift but not runaway so no freeze
    geo.self_heal.return_value = {"self_heal_needed": True, "current_r": _GOLDEN_R + 0.15}
    aletheia.audit_step.return_value = {"decision": "ALLOW"}

    loop = _make_loop(
        geo, mneme, aletheia,
        enable_human_gates=False,
        healing_history_db=tmp_db,
        escalation_file=tmp_escalation,
    )
    await loop._run_cycle()

    assert not Path(tmp_escalation).exists()
    assert loop.frozen is False


@pytest.mark.asyncio
async def test_human_gates_on_still_escalates(tmp_db, tmp_escalation):
    """Regression guard – enable_human_gates=True (default) still escalates on high drift."""
    geo, mneme, aletheia = AsyncMock(), AsyncMock(), AsyncMock()

    embs = _diverse_embeddings(10)
    mneme.geometric_search_by_spectral.side_effect = [
        [{"embedding": e} for e in embs],
        [{"id": "h1"}],
    ]
    geo.self_heal.return_value = {"self_heal_needed": True, "current_r": _GOLDEN_R + 0.15}
    aletheia.audit_step.return_value = {"decision": "ALLOW"}

    loop = _make_loop(
        geo, mneme, aletheia,
        enable_human_gates=True,
        healing_history_db=tmp_db,
        escalation_file=tmp_escalation,
    )
    await loop._run_cycle()

    assert Path(tmp_escalation).exists()
    lines = Path(tmp_escalation).read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["level"] == "high"
