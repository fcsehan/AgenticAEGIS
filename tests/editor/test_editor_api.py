"""Tests for AEGIS-1201: Domain Editor Backend API."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aegis.editor.api import router

DOMAINS_DIR = Path(__file__).parent.parent.parent / "aegis" / "domains"


@pytest.fixture()
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


class TestProjectOpen:
    def test_open_domain_directory(self, client: TestClient) -> None:
        resp = client.post(
            "/api/project/open",
            json={"path": str(DOMAINS_DIR / "pharma")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["meldFiles"]) == 3
        assert len(data["domains"]) >= 1

    def test_open_nonexistent_directory(self, client: TestClient) -> None:
        resp = client.post(
            "/api/project/open",
            json={"path": "/nonexistent/path"},
        )
        assert resp.status_code == 400


class TestDomainCRUD:
    def test_create_domain(self, client: TestClient) -> None:
        resp = client.post(
            "/api/domains",
            json={"name": "TestDomain", "description": "A test domain"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "TestDomain"

    def test_list_domains(self, client: TestClient) -> None:
        client.post("/api/domains", json={"name": "D1"})
        client.post("/api/domains", json={"name": "D2"})
        resp = client.get("/api/domains")
        assert resp.status_code == 200
        assert len(resp.json()) >= 2

    def test_get_domain(self, client: TestClient) -> None:
        create_resp = client.post("/api/domains", json={"id": "test1", "name": "Test1"})
        domain_id = create_resp.json()["id"]
        resp = client.get(f"/api/domains/{domain_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Test1"

    def test_get_nonexistent_domain(self, client: TestClient) -> None:
        resp = client.get("/api/domains/nonexistent")
        assert resp.status_code == 404

    def test_update_domain(self, client: TestClient) -> None:
        client.post("/api/domains", json={"id": "upd", "name": "Before"})
        resp = client.put("/api/domains/upd", json={"name": "After"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "After"


class TestRules:
    def test_add_rule(self, client: TestClient) -> None:
        client.post("/api/domains", json={"id": "rules1", "name": "Rules"})
        resp = client.post(
            "/api/domains/rules1/rules",
            json={
                "code": "TestCode",
                "agentRole": "testAgent",
                "modality": "FORBIDDEN",
                "proposition": "share classified",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["modality"] == "FORBIDDEN"

    def test_delete_rule(self, client: TestClient) -> None:
        client.post("/api/domains", json={"id": "del1", "name": "Del"})
        rule_resp = client.post(
            "/api/domains/del1/rules",
            json={"code": "C", "agentRole": "a", "modality": "PERMITTED", "proposition": "test"},
        )
        rule_id = rule_resp.json()["id"]
        resp = client.delete(f"/api/domains/del1/rules/{rule_id}")
        assert resp.status_code == 200


class TestGuardCheck:
    def test_check_action_on_loaded_domain(self, client: TestClient) -> None:
        client.post(
            "/api/project/open",
            json={"path": str(DOMAINS_DIR / "pharma")},
        )
        resp = client.post(
            "/api/domains/~root/check",
            json={
                "agent": "prescribingAgent",
                "actionType": "reportAdverseEvent",
                "parameters": {"severity": "majorInteraction"},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["decision"] == "PERMITTED"

    def test_check_on_unloaded_domain(self, client: TestClient) -> None:
        client.post("/api/domains", json={"id": "empty", "name": "Empty"})
        resp = client.post(
            "/api/domains/empty/check",
            json={"agent": "a", "actionType": "test"},
        )
        assert resp.status_code == 400


class TestValidation:
    def test_validate_domain(self, client: TestClient) -> None:
        client.post(
            "/api/project/open",
            json={"path": str(DOMAINS_DIR / "pharma")},
        )
        resp = client.get("/api/domains/~root/validate")
        assert resp.status_code == 200
        assert "ruleCount" in resp.json()


class TestConflictsAndHierarchy:
    def test_get_conflicts(self, client: TestClient) -> None:
        client.post(
            "/api/project/open",
            json={"path": str(DOMAINS_DIR / "pharma")},
        )
        resp = client.get("/api/domains/~root/conflicts")
        assert resp.status_code == 200
        assert "conflicts" in resp.json()

    def test_get_hierarchy(self, client: TestClient) -> None:
        client.post(
            "/api/project/open",
            json={"path": str(DOMAINS_DIR / "pharma")},
        )
        resp = client.get("/api/domains/~root/hierarchy")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data
