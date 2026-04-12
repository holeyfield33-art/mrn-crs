"""Tests for Phase 3 production hardening: auth, rate limiting, probes, metrics."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import get_aletheia, get_geometric, get_mneme


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _mock_aletheia():
    m = AsyncMock()
    m.audit_step.return_value = {"decision": "ALLOW", "receipt": {"id": "a-1"}}
    return m


def _mock_geometric():
    m = AsyncMock()
    m.health_check.return_value = {"healthy": True, "human_escalation": False, "shi": 0.92}
    m.manifold_audit.return_value = {"r_ratio": 0.58, "shi": 0.94, "unitarity_check": True}
    return m


def _mock_mneme():
    m = AsyncMock()
    m.store_with_geo_index.return_value = {"id": "mem-1", "receipt": {"id": "m-1"}}
    return m


SAMPLE_STEP = {
    "agent_id": "agent-test",
    "premise": "All humans are mortal",
    "inference_type": "deductive",
    "conclusion": "Socrates is mortal",
    "confidence": 0.95,
}


# --------------------------------------------------------------------------- #
# API key auth tests
# --------------------------------------------------------------------------- #


class TestAPIKeyAuth:
    """Test API key authentication middleware."""

    def test_health_no_auth_required(self):
        """Public endpoints don't need auth even when keys are configured."""
        from src.main import app

        with patch.object(
            type(app.state), "limiter", create=True,
        ):
            with TestClient(app) as client:
                resp = client.get("/health")
                # Health endpoint is public — should not return 401
                assert resp.status_code != 401

    def test_live_probe_no_auth(self):
        from src.main import app

        with TestClient(app) as client:
            resp = client.get("/live")
            assert resp.status_code == 200
            assert resp.json()["status"] == "alive"

    def test_ready_probe_no_auth(self):
        from src.main import app

        with TestClient(app) as client:
            resp = client.get("/ready")
            assert resp.status_code == 200
            body = resp.json()
            assert "degraded" in body

    def test_reason_without_key_when_keys_configured(self):
        """When CRS_API_KEYS is set, requests without a key get 401."""
        from src.config import Settings

        with patch("src.api.dependencies.settings", Settings(crs_api_keys="test-key-123")):
            from src.main import app

            app.dependency_overrides[get_aletheia] = _mock_aletheia
            app.dependency_overrides[get_geometric] = _mock_geometric
            app.dependency_overrides[get_mneme] = _mock_mneme
            try:
                with TestClient(app) as client:
                    resp = client.post("/reason", json=SAMPLE_STEP)
                    assert resp.status_code == 401
            finally:
                app.dependency_overrides.clear()

    def test_reason_with_valid_key(self):
        """With correct key, request succeeds."""
        from src.config import Settings

        with patch("src.api.dependencies.settings", Settings(crs_api_keys="test-key-123")):
            from src.main import app

            app.dependency_overrides[get_aletheia] = _mock_aletheia
            app.dependency_overrides[get_geometric] = _mock_geometric
            app.dependency_overrides[get_mneme] = _mock_mneme
            try:
                with TestClient(app) as client:
                    resp = client.post(
                        "/reason",
                        json=SAMPLE_STEP,
                        headers={"Authorization": "Bearer test-key-123"},
                    )
                    assert resp.status_code == 200
            finally:
                app.dependency_overrides.clear()

    def test_reason_with_invalid_key(self):
        """Wrong key returns 401."""
        from src.config import Settings

        with patch("src.api.dependencies.settings", Settings(crs_api_keys="real-key")):
            from src.main import app

            app.dependency_overrides[get_aletheia] = _mock_aletheia
            app.dependency_overrides[get_geometric] = _mock_geometric
            app.dependency_overrides[get_mneme] = _mock_mneme
            try:
                with TestClient(app) as client:
                    resp = client.post(
                        "/reason",
                        json=SAMPLE_STEP,
                        headers={"Authorization": "Bearer wrong-key"},
                    )
                    assert resp.status_code == 401
            finally:
                app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Probes
# --------------------------------------------------------------------------- #


class TestProbes:
    def test_liveness_always_ok(self):
        from src.main import app

        with TestClient(app) as client:
            resp = client.get("/live")
            assert resp.status_code == 200
            assert resp.json()["status"] == "alive"

    def test_readiness_returns_service_status(self):
        from src.main import app

        with TestClient(app) as client:
            resp = client.get("/ready")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "ready"
            assert "services" in body
            # External services are down in test → degraded=True
            assert body["degraded"] is True


# --------------------------------------------------------------------------- #
# Metrics endpoint
# --------------------------------------------------------------------------- #


class TestMetrics:
    def test_metrics_endpoint_exists(self):
        from src.main import app

        with TestClient(app) as client:
            resp = client.get("/metrics")
            assert resp.status_code == 200
            # Prometheus text format
            assert "crs_requests_total" in resp.text or "HELP" in resp.text

    def test_request_id_header(self):
        from src.main import app

        with TestClient(app) as client:
            resp = client.get("/health")
            assert "x-request-id" in resp.headers


# --------------------------------------------------------------------------- #
# Healing history
# --------------------------------------------------------------------------- #


class TestHealingHistory:
    def test_record_and_retrieve(self, tmp_path):
        from src.services.healing_history import HealingHistory

        db_path = str(tmp_path / "test.db")
        h = HealingHistory(db_path)
        h.record(drift=0.05, level="medium", actions=["inject_memories"], memories_injected=3)
        h.record(drift=0.12, level="high", actions=["reset_context", "escalate_to_human"], memories_injected=0)

        events = h.recent(limit=10)
        assert len(events) == 2
        # Most recent first
        assert events[0]["level"] == "high"
        assert events[1]["level"] == "medium"
        assert events[1]["memories_injected"] == 3

    def test_empty_history(self, tmp_path):
        from src.services.healing_history import HealingHistory

        db_path = str(tmp_path / "empty.db")
        h = HealingHistory(db_path)
        assert h.recent() == []
