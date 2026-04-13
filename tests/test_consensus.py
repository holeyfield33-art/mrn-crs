"""Tests for consensus frame endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from src.api.dependencies import get_aletheia
from src.main import app


def _mock_aletheia():
    m = AsyncMock()
    m.audit_action.return_value = {"decision": "PROCEED", "receipt": {"decision_token": "c-audit-1"}}
    return m


def test_create_and_get_frame():
    app.dependency_overrides[get_aletheia] = _mock_aletheia
    try:
        with TestClient(app) as client:
            resp = client.post("/consensus/frame", json={"competing_steps": ["s1", "s2"]})
            assert resp.status_code == 200
            frame = resp.json()
            assert frame["status"] == "open"
            fid = frame["frame_id"]

            get_resp = client.get(f"/consensus/{fid}")
            assert get_resp.status_code == 200
            assert get_resp.json()["frame_id"] == fid
    finally:
        app.dependency_overrides.clear()


def test_update_frame():
    app.dependency_overrides[get_aletheia] = _mock_aletheia
    try:
        with TestClient(app) as client:
            resp = client.post("/consensus/frame", json={"competing_steps": ["s1", "s2"]})
            fid = resp.json()["frame_id"]

            update = client.post(
                "/consensus/update",
                json={"frame_id": fid, "step_id": "s1", "summary": "Strong evidence", "confidence": 0.85},
            )
            assert update.status_code == 200
            assert len(update.json()["evidence_log"]) == 1
    finally:
        app.dependency_overrides.clear()


def test_get_missing_frame():
    with TestClient(app) as client:
        resp = client.get("/consensus/nonexistent")
        assert resp.status_code == 404
