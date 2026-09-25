"""Tests for AEGIS-1001: REST API (FastAPI)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aegis.api.server import GuardState, create_app
from aegis.audit.trail import AuditTrail
from aegis.guard.guard import Guard

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "domains"


def _meld_paths() -> list[Path]:
    return [
        FIXTURE_DIR / "test_ontology.meld",
        FIXTURE_DIR / "test_action_vocab.meld",
        FIXTURE_DIR / "test_deontic_rules.meld",
    ]


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    audit_path = tmp_path / "audit.jsonl"
    trail = AuditTrail(audit_path)
    guard = Guard.from_meld_files(_meld_paths(), audit_trail=trail)
    state = GuardState(guard=guard, audit_trail=trail, audit_path=audit_path)
    app = create_app(state)
    return TestClient(app)


@pytest.fixture()
def client_no_audit() -> TestClient:
    guard = Guard.from_meld_files(_meld_paths())
    state = GuardState(guard=guard)
    app = create_app(state)
    return TestClient(app)


class TestCheckEndpoint:
    def test_permitted_action(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/check",
            json={
                "action_type": "shareIntelligence",
                "agent_id": "intelligenceAgent",
                "proposition": {"dataClassification": "unclassified"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["decision"] == "PERMITTED"

    def test_forbidden_action(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/check",
            json={
                "action_type": "shareIntelligence",
                "agent_id": "intelligenceAgent",
                "proposition": {"dataClassification": "secret"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["decision"] == "FORBIDDEN"

    def test_undecidable_unknown_action(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/check",
            json={
                "action_type": "unknownAction",
                "agent_id": "someAgent",
                "proposition": {},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["decision"] == "UNDECIDABLE"

    def test_response_has_explanation(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/check",
            json={
                "action_type": "shareIntelligence",
                "agent_id": "intelligenceAgent",
                "proposition": {"dataClassification": "unclassified"},
            },
        )
        data = resp.json()
        assert "explanation" in data
        assert len(data["explanation"]) > 0

    def test_response_headers(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/check",
            json={
                "action_type": "shareIntelligence",
                "agent_id": "intelligenceAgent",
                "proposition": {},
            },
        )
        assert "X-Request-Id" in resp.headers
        assert "X-Guard-Duration-Ms" in resp.headers
        assert float(resp.headers["X-Guard-Duration-Ms"]) >= 0

    def test_custom_request_id_echoed(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/check",
            json={
                "action_type": "shareIntelligence",
                "agent_id": "intelligenceAgent",
                "proposition": {},
            },
            headers={"X-Request-Id": "test-123"},
        )
        assert resp.headers["X-Request-Id"] == "test-123"


class TestHealthEndpoint:
    def test_health_ok(self, client: TestClient) -> None:
        resp = client.get("/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["kb_fact_count"] > 0
        assert len(data["microtheories"]) > 0
        assert data["norm_count"] > 0
        assert data["audit_trail_active"] is True

    def test_health_no_audit(self, client_no_audit: TestClient) -> None:
        resp = client_no_audit.get("/v1/health")
        assert resp.json()["audit_trail_active"] is False


class TestStatsEndpoint:
    def test_stats_initial(self, client: TestClient) -> None:
        resp = client.get("/v1/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_checks"] == 0
        assert data["permitted"] == 0
        assert data["forbidden"] == 0
        assert data["undecidable"] == 0

    def test_stats_after_checks(self, client: TestClient) -> None:
        # Make a permitted check
        client.post(
            "/v1/check",
            json={
                "action_type": "shareIntelligence",
                "agent_id": "intelligenceAgent",
                "proposition": {"dataClassification": "unclassified"},
            },
        )
        # Make a forbidden check
        client.post(
            "/v1/check",
            json={
                "action_type": "shareIntelligence",
                "agent_id": "intelligenceAgent",
                "proposition": {"dataClassification": "secret"},
            },
        )
        resp = client.get("/v1/stats")
        data = resp.json()
        assert data["total_checks"] == 2
        assert data["permitted"] == 1
        assert data["forbidden"] == 1


class TestAuditVerifyEndpoint:
    def test_verify_fresh_trail(self, client: TestClient) -> None:
        # Make one check so the audit file exists
        client.post(
            "/v1/check",
            json={
                "action_type": "shareIntelligence",
                "agent_id": "intelligenceAgent",
                "proposition": {"dataClassification": "unclassified"},
            },
        )
        resp = client.post("/v1/audit/verify", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["total_entries"] == 1

    def test_verify_after_checks(self, client: TestClient) -> None:
        # Make some checks to populate audit trail
        for _ in range(3):
            client.post(
                "/v1/check",
                json={
                    "action_type": "shareIntelligence",
                    "agent_id": "intelligenceAgent",
                    "proposition": {"dataClassification": "unclassified"},
                },
            )
        resp = client.post("/v1/audit/verify", json={})
        data = resp.json()
        assert data["valid"] is True
        assert data["total_entries"] == 3

    def test_verify_no_audit_path(self, client_no_audit: TestClient) -> None:
        resp = client_no_audit.post("/v1/audit/verify", json={})
        assert resp.status_code == 400


class TestToolSchemaEndpoint:
    def test_tool_schema_returned(self, client: TestClient) -> None:
        resp = client.get("/v1/tool-schema")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "aegis_check"
        assert "input_schema" in data
