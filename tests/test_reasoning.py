"""Tests for the reasoning pipeline (POST /reason)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import get_aletheia, get_geometric, get_mneme
from src.main import app


# --------------------------------------------------------------------------- #
# Helpers – mock external services
# --------------------------------------------------------------------------- #

def _mock_aletheia_allow():
    m = AsyncMock()
    m.audit_step.return_value = {"decision": "ALLOW", "receipt": {"id": "a-receipt-1"}}
    return m


def _mock_aletheia_deny():
    m = AsyncMock()
    m.audit_step.return_value = {"decision": "DENY", "receipt": {"id": "a-deny-1"}}
    return m


def _mock_geometric_healthy():
    m = AsyncMock()
    m.health_check.return_value = {"healthy": True, "human_escalation": False, "shi": 0.92}
    m.manifold_audit.return_value = {"r_ratio": 0.58, "shi": 0.94, "unitarity_check": True}
    return m


def _mock_geometric_escalate():
    m = AsyncMock()
    m.health_check.return_value = {"healthy": False, "human_escalation": True, "shi": 0.3}
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


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_reason_success():
    app.dependency_overrides[get_aletheia] = _mock_aletheia_allow
    app.dependency_overrides[get_geometric] = _mock_geometric_healthy
    app.dependency_overrides[get_mneme] = _mock_mneme
    try:
        with TestClient(app) as client:
            resp = client.post("/reason", json=SAMPLE_STEP)
        assert resp.status_code == 200
        body = resp.json()
        assert "step_id" in body
        assert "fingerprint" in body
        assert len(body["receipts"]) >= 1
    finally:
        app.dependency_overrides.clear()


def test_reason_policy_denied():
    app.dependency_overrides[get_aletheia] = _mock_aletheia_deny
    app.dependency_overrides[get_geometric] = _mock_geometric_healthy
    app.dependency_overrides[get_mneme] = _mock_mneme
    try:
        with TestClient(app) as client:
            resp = client.post("/reason", json=SAMPLE_STEP)
        assert resp.status_code == 403
        assert "receipt" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_reason_human_escalation():
    app.dependency_overrides[get_aletheia] = _mock_aletheia_allow
    app.dependency_overrides[get_geometric] = _mock_geometric_escalate
    app.dependency_overrides[get_mneme] = _mock_mneme
    try:
        with TestClient(app) as client:
            resp = client.post("/reason", json=SAMPLE_STEP)
        assert resp.status_code == 423
    finally:
        app.dependency_overrides.clear()


def test_reason_invalid_body():
    app.dependency_overrides[get_aletheia] = _mock_aletheia_allow
    app.dependency_overrides[get_geometric] = _mock_geometric_healthy
    app.dependency_overrides[get_mneme] = _mock_mneme
    try:
        with TestClient(app) as client:
            resp = client.post("/reason", json={"agent_id": "x"})
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()
