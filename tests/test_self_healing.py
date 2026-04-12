"""Tests for the self-healing background cycle with multi-level policy engine."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from src.services.self_healing import (
    DEFAULT_LEVEL_ACTIONS,
    SelfHealingLoop,
    _GOLDEN_R,
    healthy_context_buffer,
    sampling_temperature,
)


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
    mneme.geometric_search_by_spectral.return_value = [
        {"embedding": [0.1] * 384},
    ]
    geo.self_heal.return_value = {"self_heal_needed": False}

    loop = _make_loop(geo, mneme, aletheia, healing_history_db=tmp_db)
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

    mneme.geometric_search_by_spectral.side_effect = [
        [{"embedding": [0.1] * 384}],
        [{"id": "h1", "embedding": [0.2] * 384}],
    ]
    # current_r produces low drift: abs(0.608 - 0.578) = 0.03
    geo.self_heal.return_value = {
        "self_heal_needed": True,
        "current_r": _GOLDEN_R + 0.03,
        "correction": {"retrieve_shi_above": 0.85},
    }
    aletheia.audit_step.return_value = {"decision": "ALLOW"}

    loop = _make_loop(geo, mneme, aletheia, healing_history_db=tmp_db)
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

    mneme.geometric_search_by_spectral.side_effect = [
        [{"embedding": [0.1] * 384}],
        [{"id": "h1"}],
    ]
    # current_r produces medium drift: abs(0.648 - 0.578) = 0.07
    geo.self_heal.return_value = {
        "self_heal_needed": True,
        "current_r": _GOLDEN_R + 0.07,
    }
    aletheia.audit_step.return_value = {"decision": "ALLOW"}

    loop = _make_loop(geo, mneme, aletheia, healing_history_db=tmp_db)
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

    mneme.geometric_search_by_spectral.side_effect = [
        [{"embedding": [0.1] * 384}],
        [{"id": "h1"}],
    ]
    # current_r produces high drift: abs(0.728 - 0.578) = 0.15
    geo.self_heal.return_value = {
        "self_heal_needed": True,
        "current_r": _GOLDEN_R + 0.15,
    }
    aletheia.audit_step.return_value = {"decision": "ALLOW"}

    loop = _make_loop(
        geo, mneme, aletheia,
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

    mneme.geometric_search_by_spectral.side_effect = [
        [{"embedding": [0.1] * 384}],
        [{"id": "h1"}],
    ]
    geo.self_heal.return_value = {
        "self_heal_needed": True,
        "current_r": _GOLDEN_R + 0.03,
    }
    aletheia.audit_step.return_value = {"decision": "ALLOW"}

    loop = _make_loop(geo, mneme, aletheia, healing_history_db=tmp_db)
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
    mneme.geometric_search_by_spectral.side_effect = [
        [{"embedding": [0.1] * 384}],
        [{"id": "h1"}],
    ]
    geo.self_heal.return_value = {
        "self_heal_needed": True,
        "current_r": _GOLDEN_R + 0.03,
        "corrections": [{"retrieve_shi_above": 0.9}],
    }
    aletheia.audit_step.return_value = {"decision": "ALLOW"}

    loop = _make_loop(geo, mneme, aletheia, healing_history_db=tmp_db)
    await loop._run_cycle()

    second_call = mneme.geometric_search_by_spectral.call_args_list[1]
    assert second_call.kwargs["shi_min"] == 0.9


# ------------------------------------------------------------------ #
# Stop flag
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_stop_flag(tmp_db):
    loop = _make_loop(AsyncMock(), AsyncMock(), AsyncMock(), healing_history_db=tmp_db)
    assert loop.enabled is True
    loop.stop()
    assert loop.enabled is False
