"""Healing history – stores self-healing events in a local SQLite database."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS healing_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    drift       REAL    NOT NULL,
    level       TEXT    NOT NULL,
    actions     TEXT    NOT NULL,
    memories_injected INTEGER NOT NULL DEFAULT 0,
    details     TEXT    NOT NULL DEFAULT '{}'
);
"""


class HealingHistory:
    """Thin wrapper around a SQLite database for healing event persistence."""

    def __init__(self, db_path: str = "healing_history.db") -> None:
        self._db_path = db_path
        self._ensure_table()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _ensure_table(self) -> None:
        with self._connect() as conn:
            conn.execute(_CREATE_TABLE)

    def record(
        self,
        drift: float,
        level: str,
        actions: list[str],
        memories_injected: int = 0,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record a healing event."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO healing_events (timestamp, drift, level, actions, memories_injected, details) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    drift,
                    level,
                    json.dumps(actions),
                    memories_injected,
                    json.dumps(details or {}),
                ),
            )

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent healing events."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM healing_events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()

        return [
            {
                "id": r["id"],
                "timestamp": r["timestamp"],
                "drift": r["drift"],
                "level": r["level"],
                "actions": json.loads(r["actions"]),
                "memories_injected": r["memories_injected"],
                "details": json.loads(r["details"]),
            }
            for r in rows
        ]
