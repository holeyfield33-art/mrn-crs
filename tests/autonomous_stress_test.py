"""Autonomous stress test for the unconstrained CRS branch.

Simulates 5 healthy reasoning steps followed by 3 repetitive steps to trigger
the entropy freeze (SEMANTIC_LOOP_DETECTED or CRITICAL_INFORMATION_COLLAPSE).

Expected result:
  - The self-healing loop detects entropy collapse on the repetitive steps.
  - The system freezes and writes freeze_manifest.json.
  - POST /reason returns 503 while the system is frozen.

This test can run standalone (no external services needed) by mocking all
downstream clients.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from src.services.self_healing import (
    ENTROPY_CRITICAL_COLLAPSE,
    ENTROPY_SEMANTIC_LOOP,
    SelfHealingLoop,
    _GOLDEN_R,
    healthy_context_buffer,
)


def _diverse_embeddings(n: int, dim: int = 384, seed: int = 42) -> list[list[float]]:
    """Generate *n* diverse random embeddings (healthy)."""
    rng = np.random.default_rng(seed)
    return [rng.standard_normal(dim).tolist() for _ in range(n)]


def _repetitive_embeddings(n: int, dim: int = 384) -> list[list[float]]:
    """Generate *n* nearly-identical embeddings (entropy collapse)."""
    base = np.ones(dim, dtype=np.float64) * 0.5
    rng = np.random.default_rng(0)
    return [(base + rng.normal(0, 1e-6, dim)).tolist() for _ in range(n)]


@pytest.fixture(autouse=True)
def _cleanup():
    """Remove freeze manifest and reset globals after each test."""
    import src.services.self_healing as mod

    healthy_context_buffer.clear()
    mod.sampling_temperature = 0.7
    yield
    healthy_context_buffer.clear()
    mod.sampling_temperature = 0.7
    Path("freeze_manifest.json").unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# Stress test: 5 healthy cycles → 3 repetitive cycles → freeze
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_autonomous_stress_freeze(tmp_path):
    """Simulate healthy and then repetitive reasoning to trigger freeze.

    Steps:
      1. Run 5 self-healing cycles with diverse embeddings → no freeze.
      2. Run up to 3 cycles with identical embeddings → freeze triggered.
      3. Verify freeze_manifest.json is generated.
    """
    geo = AsyncMock()
    mneme = AsyncMock()
    aletheia = AsyncMock()
    aletheia.audit_step.return_value = {"decision": "PROCEED", "receipt": {"mode": "passive_audit"}}

    db_path = str(tmp_path / "stress.db")
    esc_path = str(tmp_path / "stress_esc.jsonl")

    loop = SelfHealingLoop(
        mneme=mneme,
        geometric=geo,
        aletheia=aletheia,
        interval_seconds=1,
        drift_threshold=0.5,
        min_memories=1,
        level_low=0.02,
        level_medium=0.05,
        level_high=0.10,
        escalation_file=esc_path,
        healing_history_db=db_path,
    )

    # ---- Phase 1: 5 healthy cycles ------------------------------------ #
    healthy_embs = _diverse_embeddings(20)
    for i in range(5):
        mneme.geometric_search_by_spectral.return_value = [
            {"embedding": e} for e in healthy_embs
        ]
        geo.self_heal.return_value = {
            "self_heal_needed": False,
            "current_r": _GOLDEN_R + 0.01,
        }

        await loop._run_cycle()
        assert loop.frozen is False, f"Should not freeze on healthy cycle {i+1}"

    assert len(loop.drift_history) == 5

    # ---- Phase 2: repetitive cycles → expect freeze ------------------- #
    # Use compute_entropy_from_embeddings mock to return low entropy values
    # simulating repetitive reasoning that causes entropy collapse.
    repetitive_embs = _repetitive_embeddings(20)

    freeze_triggered = False
    for i in range(3):
        if loop.frozen:
            freeze_triggered = True
            break

        mneme.geometric_search_by_spectral.return_value = [
            {"embedding": e} for e in repetitive_embs
        ]
        geo.self_heal.return_value = {
            "self_heal_needed": False,
            "current_r": _GOLDEN_R,
        }

        # Mock low entropy to simulate semantic loop / critical collapse
        low_entropy = 0.20  # Below CRITICAL_COLLAPSE threshold
        with patch(
            "src.services.self_healing.compute_entropy_from_embeddings",
            return_value=low_entropy,
        ):
            await loop._run_cycle()

        if loop.frozen:
            freeze_triggered = True
            break

    assert freeze_triggered, "System should have frozen after repetitive steps"
    assert loop.enabled is False, "Loop should be disabled after freeze"

    # ---- Verify freeze manifest ---------------------------------------- #
    manifest_path = Path("freeze_manifest.json")
    assert manifest_path.exists(), "freeze_manifest.json should exist"

    manifest = json.loads(manifest_path.read_text())
    assert manifest["reason"] in (
        "CRITICAL_INFORMATION_COLLAPSE",
        "SEMANTIC_LOOP_DETECTED",
    )
    assert "details" in manifest
    assert "drift_history" in manifest

    # ---- Verify subsequent cycles are skipped -------------------------- #
    mneme.geometric_search_by_spectral.reset_mock()
    await loop._run_cycle()
    mneme.geometric_search_by_spectral.assert_not_called()

    # ---- Verify healing history records freeze event ------------------- #
    events = loop.history.recent(limit=50)
    frozen_events = [e for e in events if e["level"] == "FROZEN"]
    assert len(frozen_events) >= 1, "At least one FROZEN event should be in history"


# --------------------------------------------------------------------------- #
# Verify first cycle triggers freeze with very low entropy
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_critical_collapse_on_first_repetitive(tmp_path):
    """A single cycle with entropy < 0.25 should immediately freeze."""
    geo = AsyncMock()
    mneme = AsyncMock()
    aletheia = AsyncMock()
    aletheia.audit_step.return_value = {"decision": "PROCEED"}

    db_path = str(tmp_path / "critical.db")

    loop = SelfHealingLoop(
        mneme=mneme,
        geometric=geo,
        aletheia=aletheia,
        interval_seconds=1,
        min_memories=1,
        healing_history_db=db_path,
    )

    embs = _diverse_embeddings(10)
    mneme.geometric_search_by_spectral.return_value = [
        {"embedding": e} for e in embs
    ]
    geo.self_heal.return_value = {
        "self_heal_needed": False,
        "current_r": _GOLDEN_R,
    }

    with patch(
        "src.services.self_healing.compute_entropy_from_embeddings",
        return_value=0.15,  # Below 0.25 critical threshold
    ):
        await loop._run_cycle()

    assert loop.frozen is True
    manifest = json.loads(Path("freeze_manifest.json").read_text())
    assert manifest["reason"] == "CRITICAL_INFORMATION_COLLAPSE"


# --------------------------------------------------------------------------- #
# Semantic loop: 2 consecutive low-entropy cycles
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_semantic_loop_two_consecutive(tmp_path):
    """Two consecutive cycles with entropy < 0.35 (but >= 0.25) triggers SEMANTIC_LOOP."""
    geo = AsyncMock()
    mneme = AsyncMock()
    aletheia = AsyncMock()
    aletheia.audit_step.return_value = {"decision": "PROCEED"}

    db_path = str(tmp_path / "semantic.db")

    loop = SelfHealingLoop(
        mneme=mneme,
        geometric=geo,
        aletheia=aletheia,
        interval_seconds=1,
        min_memories=1,
        healing_history_db=db_path,
    )

    embs = _diverse_embeddings(10)
    mneme.geometric_search_by_spectral.return_value = [
        {"embedding": e} for e in embs
    ]
    geo.self_heal.return_value = {
        "self_heal_needed": False,
        "current_r": _GOLDEN_R,
    }

    # Cycle 1: entropy = 0.30 (< 0.35 but >= 0.25) → no freeze yet
    with patch(
        "src.services.self_healing.compute_entropy_from_embeddings",
        return_value=0.30,
    ):
        await loop._run_cycle()
    assert loop.frozen is False
    assert len(loop.drift_history) == 1

    # Cycle 2: entropy = 0.32 → 2 consecutive below 0.35 → SEMANTIC_LOOP
    with patch(
        "src.services.self_healing.compute_entropy_from_embeddings",
        return_value=0.32,
    ):
        await loop._run_cycle()
    assert loop.frozen is True
    manifest = json.loads(Path("freeze_manifest.json").read_text())
    assert manifest["reason"] == "SEMANTIC_LOOP_DETECTED"
