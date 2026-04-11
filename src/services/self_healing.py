"""Self-healing background loop – multi-level policy engine with healing history."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from src.api.metrics import crs_self_heal_total
from src.clients.aletheia_client import AletheiaClient
from src.clients.geometric_client import GeometricClient
from src.clients.mneme_client import MnemeClient
from src.services.healing_history import HealingHistory

logger = logging.getLogger(__name__)

# Golden-ratio reference r
_GOLDEN_R = 0.578

# Shared healthy-context buffer that the reasoning endpoint can optionally read
healthy_context_buffer: list[dict[str, Any]] = []

# Mutable global sampling temperature (adjusted by self-healing)
sampling_temperature: float = 0.7

# Level → default actions mapping
DEFAULT_LEVEL_ACTIONS: dict[str, list[str]] = {
    "low": ["inject_memories"],
    "medium": ["inject_memories", "adjust_temperature"],
    "high": ["reset_context", "inject_memories", "adjust_temperature", "escalate_to_human"],
}


class SelfHealingLoop:
    """Periodically queries Mneme for recent memories, checks Geometric Brain
    for drift, and applies multi-level correction policies."""

    def __init__(
        self,
        mneme: MnemeClient,
        geometric: GeometricClient,
        aletheia: AletheiaClient,
        *,
        interval_seconds: int = 60,
        drift_threshold: float = 0.5,
        healthy_r_min: float = 0.57,
        healthy_r_max: float = 0.59,
        healthy_shi_min: float = 0.8,
        min_memories: int = 10,
        level_low: float = 0.02,
        level_medium: float = 0.05,
        level_high: float = 0.10,
        escalation_webhook: str = "",
        escalation_file: str = "escalations.jsonl",
        healing_history_db: str = "healing_history.db",
    ) -> None:
        self.mneme = mneme
        self.geometric = geometric
        self.aletheia = aletheia
        self.interval_seconds = interval_seconds
        self.drift_threshold = drift_threshold
        self.healthy_r_min = healthy_r_min
        self.healthy_r_max = healthy_r_max
        self.healthy_shi_min = healthy_shi_min
        self.min_memories = min_memories
        self.level_low = level_low
        self.level_medium = level_medium
        self.level_high = level_high
        self.escalation_webhook = escalation_webhook
        self.escalation_file = escalation_file
        self.enabled = True
        self.history = HealingHistory(healing_history_db)

    # ---------------------------------------------------------------------- #
    # Drift classification
    # ---------------------------------------------------------------------- #

    def _classify_drift(self, current_r: float) -> tuple[float, str]:
        """Return (drift_magnitude, level_name)."""
        drift = abs(current_r - _GOLDEN_R)
        if drift >= self.level_high:
            return drift, "high"
        if drift >= self.level_medium:
            return drift, "medium"
        if drift >= self.level_low:
            return drift, "low"
        return drift, "none"

    # ---------------------------------------------------------------------- #
    # Action implementations
    # ---------------------------------------------------------------------- #

    async def _action_inject_memories(self, retrieve_shi_above: float) -> list[dict[str, Any]]:
        """Retrieve healthy memories from Mneme and inject into the context buffer."""
        try:
            healthy = await self.mneme.geometric_search_by_spectral(
                r_min=self.healthy_r_min,
                r_max=self.healthy_r_max,
                shi_min=retrieve_shi_above,
                top_k=20,
            )
        except httpx.HTTPError as exc:
            logger.warning("Mneme unreachable fetching healthy memories: %s", exc)
            healthy = []

        healthy_context_buffer.clear()
        healthy_context_buffer.extend(healthy[:20])
        return healthy

    def _action_adjust_temperature(self, drift: float) -> float:
        """Lower sampling temperature proportionally to drift severity."""
        global sampling_temperature
        reduction = min(drift * 2, 0.3)
        sampling_temperature = max(0.1, 0.7 - reduction)
        logger.info("Sampling temperature adjusted to %.2f", sampling_temperature)
        return sampling_temperature

    def _action_reset_context(self) -> None:
        """Clear context buffer entirely (will be re-populated by inject_memories)."""
        healthy_context_buffer.clear()
        logger.info("Context buffer reset")

    async def _action_escalate_to_human(self, drift: float, level: str) -> None:
        """Write escalation to file and optionally POST to a webhook."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "drift": drift,
            "level": level,
            "message": "Geometric drift exceeds safe threshold – human review required",
        }

        # Always write to escalation file
        path = Path(self.escalation_file)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        logger.warning("Human escalation written to %s", self.escalation_file)

        # Optionally POST to webhook
        if self.escalation_webhook:
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                    await client.post(self.escalation_webhook, json=entry)
            except httpx.HTTPError:
                logger.warning("Escalation webhook unreachable")

    # ---------------------------------------------------------------------- #
    # Single cycle
    # ---------------------------------------------------------------------- #

    async def _run_cycle(self) -> None:
        """Execute one self-healing cycle with multi-level policy."""

        # 1. Query Mneme for recent memories in the broad spectral range
        try:
            recent = await self.mneme.geometric_search_by_spectral(
                r_min=0.4, r_max=0.7, shi_min=0.0, top_k=100,
            )
        except httpx.HTTPError as exc:
            logger.warning("Mneme unreachable in self-heal cycle: %s", exc)
            return

        if not recent:
            logger.debug("No recent memories – skipping self-heal cycle")
            return

        # 2. Extract embeddings; skip if below minimum threshold
        embeddings = [m["embedding"] for m in recent if "embedding" in m]
        if len(embeddings) < self.min_memories:
            logger.debug(
                "Only %d memories with embeddings (need %d) – skipping",
                len(embeddings), self.min_memories,
            )
            return

        # 3. Ask Geometric Brain whether drift correction is needed
        try:
            result = await self.geometric.self_heal(embeddings, current_r=self.drift_threshold)
        except httpx.HTTPError as exc:
            logger.warning("Geometric Brain unreachable in self-heal cycle: %s", exc)
            return

        if not result.get("self_heal_needed"):
            logger.debug("No drift detected – self-heal not needed")
            crs_self_heal_total.labels(outcome="no_drift").inc()
            return

        # 4. Determine current_r and classify drift
        current_r = result.get("current_r", self.drift_threshold)
        drift, level = self._classify_drift(current_r)

        if level == "none":
            logger.debug("Drift %.4f below low threshold – no action", drift)
            crs_self_heal_total.labels(outcome="below_threshold").inc()
            return

        logger.info("Geometric drift detected: %.4f (level=%s)", drift, level)

        # 5. Determine retrieval thresholds from correction dict
        correction = result.get("correction", result.get("corrections", {}))
        if isinstance(correction, list):
            correction = correction[0] if correction else {}
        retrieve_shi_above = correction.get("retrieve_shi_above", self.healthy_shi_min)

        # 6. Execute actions for the detected level
        actions = DEFAULT_LEVEL_ACTIONS.get(level, ["inject_memories"])
        executed_actions: list[str] = []
        memories_injected = 0

        for action in actions:
            if action == "reset_context":
                self._action_reset_context()
                executed_actions.append("reset_context")
            elif action == "inject_memories":
                healthy = await self._action_inject_memories(retrieve_shi_above)
                memories_injected = len(healthy)
                executed_actions.append("inject_memories")
            elif action == "adjust_temperature":
                self._action_adjust_temperature(drift)
                executed_actions.append("adjust_temperature")
            elif action == "escalate_to_human":
                await self._action_escalate_to_human(drift, level)
                executed_actions.append("escalate_to_human")

        # 7. Audit each action via Aletheia
        memory_ids = [m.get("id", m.get("step_id", "unknown")) for m in healthy_context_buffer]
        for action_name in executed_actions:
            try:
                await self.aletheia.audit_step({
                    "step_id": str(uuid.uuid4()),
                    "agent_id": "self-healing-loop",
                    "action": f"GEOMETRIC_SELF_HEAL_{action_name.upper()}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "drift": drift,
                        "level": level,
                        "action": action_name,
                        "memory_ids": memory_ids,
                        "correction": correction,
                    },
                })
            except httpx.HTTPError:
                logger.warning("Aletheia unreachable – audit for %s skipped", action_name)

        # 8. Record healing event in history
        self.history.record(
            drift=drift,
            level=level,
            actions=executed_actions,
            memories_injected=memories_injected,
            details={"correction": correction, "current_r": current_r},
        )

        crs_self_heal_total.labels(outcome=level).inc()
        logger.info(
            "Self-healing cycle complete: drift=%.4f level=%s actions=%s memories=%d",
            drift, level, executed_actions, memories_injected,
        )

    # ---------------------------------------------------------------------- #
    # Long-running loop
    # ---------------------------------------------------------------------- #

    async def run(self) -> None:
        """Long-running loop that runs self-healing cycles at a configurable interval."""
        logger.info(
            "Self-healing loop started (interval=%ds, drift_threshold=%.2f)",
            self.interval_seconds, self.drift_threshold,
        )
        while self.enabled:
            try:
                await self._run_cycle()
            except Exception:
                logger.exception("Unhandled error in self-healing cycle")
            await asyncio.sleep(self.interval_seconds)

    def stop(self) -> None:
        """Signal the loop to exit after the current cycle."""
        self.enabled = False
