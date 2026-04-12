"""Tests for the self-healing background cycle with multi-level policy engine."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import numpy as np
import pytest

from src.services.self_healing import (
    DEFAULT_LEVEL_ACTIONS,
    ENTROPY_CRITICAL_COLLAPSE,
    ENTROPY_SEMANTIC_LOOP,
    SelfHealingLoop,
    _GOLDEN_R,
    healthy_context_buffer,
    sampling_temperature,
)


def _diverse_embeddings(n: int = 10, dim: int = 384) -> list[list[float]]:
    """Generate *n* diverse random embeddings that produce healthy entropy."""
    rng = np.random.default_rng(42)
    return [rng.standard_normal(dim).tolist() for _ in range(n)]


@pytest.fixture(autouse=True)
def _reset_globals():
    """Reset module-level mutable state between tests."""
    import src.services.self_healing as mod

    healthy_context_buffer.clear()
    mod.sampling_temperature = 0.7
    yield
    healthy_context_buffer.clear()
    mod.sampling_temperature = 0.7


@pytest.fixture
def mock_clients():
    geo = AsyncMock()
    mneme = AsyncMock()
    aletheia = AsyncMock()
    return geo, mneme, aletheia


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
    interval_seconds: int = 1,
    drift_threshold: float = 0.5,
    healthy_r_min: float = 0.57,
    healthy_r_max: float = 0.59,
    healthy_shi_min: float = 0.8,
    min_memories: int = 1,
    level_low: float = 0.02,
    level_medium: float = 0.05,
    level_high: float = 0.10,
    escalation_webhook: str = "",
    escalation_file: str = "escalations.jsonl",
    healing_history_db: str = "healing_history.db",
) -> SelfHealingLoop:
    return SelfHealingLoop(
        mneme=mneme,
        geometric=geo,
        aletheia=aletheia,
        interval_seconds=interval_seconds,
        drift_threshold=drift_threshold,
        healthy_r_min=healthy_r_min,
        healthy_r_max=healthy_r_max,
        healthy_shi_min=healthy_shi_min,
        min_memories=min_memories,
        level_low=level_low,
        level_medium=level_medium,
        level_high=level_high,
        escalation_webhook=escalation_webhook,
        escalation_file=escalation_file,
        healing_history_db=healing_history_db,
    )


# ------------------------------------------------------------------ #
# Basic skip / no-op paths
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_no_recent_memories_skips(mock_clients, tmp_db):
    geo, mneme, aletheia = mock_clients
    mneme.geometric_search_by_spectral.return_value = []

    loop = _make_loop(geo, mneme, aletheia, healing_history_db=tmp_db)
    await loop._run_cycle()
    geo.self_heal.assert_not_called()


@pytest.mark.asyncio
async def test_too_few_embeddings_skips(mock_clients, tmp_db):
    geo, mneme, aletheia = mock_clients
    mneme.geometric_search_by_spectral.return_value = [
        {"spectral": {"shi": 0.5, "r_ratio": 0.5}},
    ]

    loop = _make_loop(geo, mneme, aletheia, min_memories=5, healing_history_db=tmp_db)
    await loop._run_cycle()
    geo.self_heal.assert_not_called()


@pytest.mark.asyncio
async def test_no_drift_does_not_inject(mock_clients, tmp_db):
    geo, mneme, aletheia = mock_clients
    embs = _diverse_embeddings(10)
    mneme.geometric_search_by_spectral.return_value = [
        {"embedding": e} for e in embs
    ]
    geo.self_heal.return_value = {"self_heal_needed": False}

    loop = _make_loop(geo, mneme, aletheia, min_memories=1, healing_history_db=tmp_db)
    await loop._run_cycle()
    assert len(healthy_context_buffer) == 0


# ------------------------------------------------------------------ #
# Drift classification
# ------------------------------------------------------------------ #


def test_classify_drift_none(mock_clients, tmp_db):
    loop = _make_loop(*mock_clients, healing_history_db=tmp_db)
    drift, level = loop._classify_drift(_GOLDEN_R + 0.01)
    assert level == "none"


def test_classify_drift_low(mock_clients, tmp_db):
    loop = _make_loop(*mock_clients, healing_history_db=tmp_db)
    drift, level = loop._classify_drift(_GOLDEN_R + 0.03)
    assert level == "low"


def test_classify_drift_medium(mock_clients, tmp_db):
    loop = _make_loop(*mock_clients, healing_history_db=tmp_db)
    drift, level = loop._classify_drift(_GOLDEN_R + 0.07)
    assert level == "medium"


def test_classify_drift_high(mock_clients, tmp_db):
    loop = _make_loop(*mock_clients, healing_history_db=tmp_db)
    drift, level = loop._classify_drift(_GOLDEN_R + 0.15)
    assert level == "high"


# ------------------------------------------------------------------ #
# Low-level drift: inject_memories only
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_low_drift_injects_memories(mock_clients, tmp_db):
    geo, mneme, aletheia = mock_clients
    embs = _diverse_embeddings(10)

    mneme.geometric_search_by_spectral.side_effect = [
        [{"embedding": e} for e in embs],
        [{"id": "h1", "embedding": embs[0]}],
    ]
    # current_r produces low drift: abs(0.608 - 0.578) = 0.03
    geo.self_heal.return_value = {
        "self_heal_needed": True,
        "current_r": _GOLDEN_R + 0.03,
        "correction": {"retrieve_shi_above": 0.85},
    }
    aletheia.audit_step.return_value = {"decision": "ALLOW"}

    loop = _make_loop(geo, mneme, aletheia, min_memories=1, healing_history_db=tmp_db)
    await loop._run_cycle()

    assert len(healthy_context_buffer) == 1
    # Low level => only inject_memories => 1 audit call
    assert aletheia.audit_step.call_count == 1
    audit_data = aletheia.audit_step.call_args[0][0]
    assert audit_data["action"] == "GEOMETRIC_SELF_HEAL_INJECT_MEMORIES"


# ------------------------------------------------------------------ #
# Medium-level drift: inject + adjust_temperature
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_medium_drift_adjusts_temperature(mock_clients, tmp_db):
    import src.services.self_healing as mod

    geo, mneme, aletheia = mock_clients
    embs = _diverse_embeddings(10)

    mneme.geometric_search_by_spectral.side_effect = [
        [{"embedding": e} for e in embs],
        [{"id": "h1"}],
    ]
    # current_r produces medium drift: abs(0.648 - 0.578) = 0.07
    geo.self_heal.return_value = {
        "self_heal_needed": True,
        "current_r": _GOLDEN_R + 0.07,
    }
    aletheia.audit_step.return_value = {"decision": "ALLOW"}

    loop = _make_loop(geo, mneme, aletheia, min_memories=1, healing_history_db=tmp_db)
    await loop._run_cycle()

    # Medium => inject_memories + adjust_temperature => 2 audit calls
    assert aletheia.audit_step.call_count == 2
    assert mod.sampling_temperature < 0.7


# ------------------------------------------------------------------ #
# High-level drift: reset + inject + adjust + escalate
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_high_drift_escalates_to_human(mock_clients, tmp_db, tmp_escalation):
    geo, mneme, aletheia = mock_clients
    embs = _diverse_embeddings(10)

    mneme.geometric_search_by_spectral.side_effect = [
        [{"embedding": e} for e in embs],
        [{"id": "h1"}],
    ]
    # current_r produces high drift but NOT runaway (< 0.25): abs(0.728 - 0.578) = 0.15
    geo.self_heal.return_value = {
        "self_heal_needed": True,
        "current_r": _GOLDEN_R + 0.15,
    }
    aletheia.audit_step.return_value = {"decision": "ALLOW"}

    loop = _make_loop(
        geo, mneme, aletheia,
        min_memories=1,
        healing_history_db=tmp_db,
        escalation_file=tmp_escalation,
    )
    await loop._run_cycle()

    # High => 4 actions => 4 audit calls
    assert aletheia.audit_step.call_count == 4

    # Escalation file written
    with open(tmp_escalation) as f:
        lines = f.readlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["level"] == "high"
    assert "human review required" in entry["message"]


# ------------------------------------------------------------------ #
# Healing history persistence
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_healing_history_recorded(mock_clients, tmp_db):
    geo, mneme, aletheia = mock_clients
    embs = _diverse_embeddings(10)

    mneme.geometric_search_by_spectral.side_effect = [
        [{"embedding": e} for e in embs],
        [{"id": "h1"}],
    ]
    geo.self_heal.return_value = {
        "self_heal_needed": True,
        "current_r": _GOLDEN_R + 0.03,
    }
    aletheia.audit_step.return_value = {"decision": "ALLOW"}

    loop = _make_loop(geo, mneme, aletheia, min_memories=1, healing_history_db=tmp_db)
    await loop._run_cycle()

    events = loop.history.recent(limit=10)
    assert len(events) == 1
    assert events[0]["level"] == "low"
    assert "inject_memories" in events[0]["actions"]


# ------------------------------------------------------------------ #
# Corrections list handling
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_corrections_list_fallback(mock_clients, tmp_db):
    geo, mneme, aletheia = mock_clients
    embs = _diverse_embeddings(10)
    mneme.geometric_search_by_spectral.side_effect = [
        [{"embedding": e} for e in embs],
        [{"id": "h1"}],
    ]
    geo.self_heal.return_value = {
        "self_heal_needed": True,
        "current_r": _GOLDEN_R + 0.03,
        "corrections": [{"retrieve_shi_above": 0.9}],
    }
    aletheia.audit_step.return_value = {"decision": "ALLOW"}

    loop = _make_loop(geo, mneme, aletheia, min_memories=1, healing_history_db=tmp_db)
    await loop._run_cycle()

    second_call = mneme.geometric_search_by_spectral.call_args_list[1]
    assert second_call.kwargs["shi_min"] == 0.9


# ------------------------------------------------------------------ #
# Four-tier freeze logic
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_freeze_on_critical_collapse(mock_clients, tmp_db, tmp_escalation):
    """Single step with entropy < 0.25 triggers CRITICAL_INFORMATION_COLLAPSE freeze."""
    geo, mneme, aletheia = mock_clients

    # Identical embeddings → near-zero entropy
    identical = [[0.1] * 384] * 10
    mneme.geometric_search_by_spectral.side_effect = [
        [{"embedding": e} for e in identical],
    ]
    geo.self_heal.return_value = {
        "self_heal_needed": False,
        "current_r": _GOLDEN_R,
    }
    aletheia.audit_step.return_value = {"decision": "ALLOW"}

    loop = _make_loop(geo, mneme, aletheia, min_memories=1,
                      healing_history_db=tmp_db, escalation_file=tmp_escalation)
    await loop._run_cycle()

    assert loop.frozen is True
    assert loop.enabled is False
    assert Path("freeze_manifest.json").exists()

    manifest = json.loads(Path("freeze_manifest.json").read_text())
    assert manifest["reason"] == "CRITICAL_INFORMATION_COLLAPSE"

    # Cleanup
    Path("freeze_manifest.json").unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_freeze_on_semantic_loop(mock_clients, tmp_db, tmp_escalation):
    """Two consecutive cycles with entropy < 0.35 triggers SEMANTIC_LOOP_DETECTED."""
    geo, mneme, aletheia = mock_clients
    aletheia.audit_step.return_value = {"decision": "ALLOW"}

    # Use diverse embeddings so the computed entropy is healthy (won't trigger tier 2)
    embs = _diverse_embeddings(10)
    mneme.geometric_search_by_spectral.return_value = [
        {"embedding": e} for e in embs
    ]
    geo.self_heal.return_value = {
        "self_heal_needed": False,
        "current_r": _GOLDEN_R,
    }

    loop = _make_loop(geo, mneme, aletheia, min_memories=1,
                      healing_history_db=tmp_db, escalation_file=tmp_escalation)

    # Pre-seed drift history with TWO low-entropy entries (simulating past cycles)
    loop.drift_history.append({"entropy": 0.30, "drift": 0.01})
    loop.drift_history.append({"entropy": 0.28, "drift": 0.01})

    # The check looks at the last 2 entries of drift_history BEFORE this cycle appends.
    # But _run_cycle appends the current entropy first then checks.
    # So we need the check to see the last 2 as low.
    # Actually, the cycle computes entropy from embeddings (which will be healthy ~2.x)
    # then appends it, then checks last 2.  So last 2 will be [0.28, 2.x] → won't trigger.
    #
    # Better approach: mock compute_entropy_from_embeddings to return low entropy.
    pass  # We'll use a mock approach below

    # Reset and try with mocking
    from unittest.mock import patch
    loop2 = _make_loop(geo, mneme, aletheia, min_memories=1,
                       healing_history_db=tmp_db, escalation_file=tmp_escalation)
    loop2.drift_history.append({"entropy": 0.30, "drift": 0.01})

    with patch("src.services.self_healing.compute_entropy_from_embeddings", return_value=0.32):
        await loop2._run_cycle()

    assert loop2.frozen is True
    manifest = json.loads(Path("freeze_manifest.json").read_text())
    assert manifest["reason"] == "SEMANTIC_LOOP_DETECTED"
    Path("freeze_manifest.json").unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_freeze_on_runaway_divergence(mock_clients, tmp_db, tmp_escalation):
    """Single step with drift > 0.25 triggers RUNAWAY_DIVERGENCE freeze."""
    geo, mneme, aletheia = mock_clients
    embs = _diverse_embeddings(10)

    mneme.geometric_search_by_spectral.return_value = [
        {"embedding": e} for e in embs
    ]
    # drift = abs(0.878 - 0.578) = 0.30 > 0.25
    geo.self_heal.return_value = {
        "self_heal_needed": True,
        "current_r": _GOLDEN_R + 0.30,
    }
    aletheia.audit_step.return_value = {"decision": "ALLOW"}

    loop = _make_loop(geo, mneme, aletheia, min_memories=1,
                      healing_history_db=tmp_db, escalation_file=tmp_escalation)
    await loop._run_cycle()

    assert loop.frozen is True
    manifest = json.loads(Path("freeze_manifest.json").read_text())
    assert manifest["reason"] == "RUNAWAY_DIVERGENCE"
    Path("freeze_manifest.json").unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_frozen_loop_skips_cycle(mock_clients, tmp_db):
    """Once frozen, subsequent cycles are skipped."""
    geo, mneme, aletheia = mock_clients

    loop = _make_loop(geo, mneme, aletheia, min_memories=1, healing_history_db=tmp_db)
    loop.frozen = True
    loop.enabled = True  # enabled but frozen

    await loop._run_cycle()
    mneme.geometric_search_by_spectral.assert_not_called()


# ------------------------------------------------------------------ #
# Stop flag
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_stop_flag(tmp_db):
    loop = _make_loop(AsyncMock(), AsyncMock(), AsyncMock(), healing_history_db=tmp_db)
    assert loop.enabled is True
    loop.stop()
    assert loop.enabled is False
