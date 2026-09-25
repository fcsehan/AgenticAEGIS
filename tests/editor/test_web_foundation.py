"""Real editor API regression tests: persistence, revisions and request boundaries."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from aegis.editor.app import create_editor_app
from aegis.editor.llm_provider import LLMClient, LLMProviderInfo, open_provider_request
from aegis.editor.provider_config import InferenceProfile, ProviderSettings, ProviderStore

DOMAINS = Path(__file__).parents[2] / "aegis/domains"
HEADERS = {"X-Aegis-Editor": "1"}


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    target = tmp_path / "project"
    shutil.copytree(DOMAINS / "pharma", target / "pharma")
    return target


def client_for(project: Path, config: Path) -> TestClient:
    return TestClient(
        create_editor_app(project, config),
        headers={**HEADERS, "X-Aegis-Project": str(project.resolve())},
    )


def test_settings_persist_and_detect_lost_updates(project: Path, tmp_path: Path) -> None:
    config = tmp_path / "config"
    client = client_for(project, config)
    response = client.get("/api/llm/settings")
    assert response.status_code == 200, response.text
    settings = response.json()
    settings.pop("credentialStatus")
    settings["profiles"].append(
        {
            "id": "mine",
            "name": "LAN",
            "baseUrl": "http://localhost:12345/v1",
            "model": "local-model",
            "maxTokens": 123,
            "allowPrivate": True,
        }
    )
    saved = client.put("/api/llm/settings", json=settings)
    assert saved.status_code == 200, saved.text
    assert client.put("/api/llm/settings", json=settings).status_code == 409
    restarted = client_for(project, config)
    profile = restarted.get("/api/llm/settings").json()["profiles"][-1]
    assert profile["model"] == "local-model"
    assert profile["maxTokens"] == 123
    assert ProviderStore(config).path.stat().st_mode & 0o777 == 0o600


def test_sources_roundtrip_revision_and_restart(project: Path, tmp_path: Path) -> None:
    client = client_for(project, tmp_path / "config")
    opened = client.post("/api/project/open", json={"path": str(project)})
    assert opened.status_code == 200, opened.text
    assert opened.json()["name"] == "project"
    assert isinstance(opened.json()["meldFiles"][0], dict)
    endpoint = "/api/domains/pharma/sources"
    before = client.get(endpoint).json()
    old = dict(before)
    name = next(iter(before["sources"]))
    before["sources"][name] += "\n;; preserved draft comment\n"
    saved = client.put(endpoint, json=before)
    assert saved.status_code == 200, saved.text
    assert saved.json()["revision"] != before["revision"]
    assert client.put(endpoint, json=old).status_code == 409
    restarted = client_for(project, tmp_path / "config")
    restarted.post("/api/project/open", json={"path": str(project)})
    assert restarted.get(endpoint).json()["sources"] == before["sources"]
    verdict = restarted.post(
        "/api/domains/pharma/check",
        json={
            "agent": "prescribingAgent",
            "actionType": "reportAdverseEvent",
            "parameters": {"severity": "majorInteraction"},
        },
    )
    assert verdict.json()["revision"] == saved.json()["revision"]
    assert verdict.json()["decision"] == "PERMITTED"


def test_changed_rule_changes_guard_decision(project: Path, tmp_path: Path) -> None:
    client = client_for(project, tmp_path / "config")
    client.post("/api/project/open", json={"path": str(project)})
    endpoint = "/api/domains/pharma/sources"
    data = client.get(endpoint).json()
    for name, source in data["sources"].items():
        if "Deontic" in name:
            data["sources"][name] = source.replace(
                "(permittedToDo-WRT PharmaCompliance prescribingAgent (reportAdverseEvent",
                "(forbiddenToDo-WRT PharmaCompliance prescribingAgent (reportAdverseEvent",
            )
    saved = client.put(endpoint, json=data)
    assert saved.status_code == 200, saved.text
    result = client.post(
        "/api/domains/pharma/check",
        json={
            "agent": "prescribingAgent",
            "actionType": "reportAdverseEvent",
            "parameters": {"severity": "majorInteraction"},
        },
    ).json()
    assert result["decision"] == "FORBIDDEN"
    assert result["revision"] == saved.json()["revision"]


def test_request_and_workspace_boundaries(project: Path, tmp_path: Path) -> None:
    client = client_for(project, tmp_path / "config")
    assert client.post("/api/project/open", json={"path": str(tmp_path)}).status_code == 403
    assert (
        client.post(
            "/api/project/open",
            json={"path": str(project)},
            headers={"Origin": "https://attacker.example"},
        ).status_code
        == 403
    )
    bare = TestClient(create_editor_app(project, tmp_path / "config2"))
    assert bare.post("/api/project/open", json={"path": str(project)}).status_code == 403
    assert client.put("/api/domains/none", json={"status": "Published"}).status_code != 200
    assert client.post("/api/domains/none/release", json={"version": "1"}).status_code == 403


def test_app_instances_do_not_share_domains(project: Path, tmp_path: Path) -> None:
    first = client_for(project, tmp_path / "one")
    second = client_for(project, tmp_path / "two")
    first.post("/api/project/open", json={"path": str(project)})
    assert len(first.get("/api/domains").json()) == 1
    assert second.get("/api/domains").json() == []


def test_local_client_does_not_leak_global_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-leak")
    provider = LLMProviderInfo("local", "Local", "local", "http://localhost:1234/v1")
    response = MagicMock()
    response.__enter__.return_value.read.return_value = b'{"choices": []}'
    with patch("aegis.editor.llm_provider.open_provider_request", return_value=response) as send:
        LLMClient(provider, "m").chat([])
        assert send.call_args.args[0].get_header("Authorization") is None


def test_profile_credentials_are_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KEY_ONE", "one")
    monkeypatch.setenv("KEY_TWO", "two")
    response = MagicMock()
    response.__enter__.return_value.read.return_value = b'{"choices": []}'
    with patch("aegis.editor.llm_provider.open_provider_request", return_value=response) as send:
        for key, value in [("KEY_ONE", "one"), ("KEY_TWO", "two")]:
            provider = LLMProviderInfo(
                "custom", "Custom", "remote", "https://provider.example/v1", secret_env=key
            )
            LLMClient(provider, "m").chat([])
            assert send.call_args.args[0].get_header("Authorization") == f"Bearer {value}"


def test_private_destination_requires_opt_in() -> None:
    import urllib.request

    provider = LLMProviderInfo(
        "local", "Local", "local", "http://127.0.0.1:1234/v1", allow_private=False
    )
    with pytest.raises(ValueError, match="Private"):
        open_provider_request(urllib.request.Request(provider.base_url + "/models"), provider, 1)


def test_profile_rejects_secrets_in_urls_and_duplicate_ids() -> None:
    with pytest.raises(ValueError):
        InferenceProfile(id="bad", name="Bad", baseUrl="https://key@example.com/v1")
    profile = InferenceProfile(id="ok", name="OK", baseUrl="http://localhost:1234/v1")
    with pytest.raises(ValueError):
        ProviderSettings(profiles=[profile, profile])
    assert "apiKey" not in json.loads(profile.model_dump_json())


def test_invalid_source_does_not_replace_guard(project: Path, tmp_path: Path) -> None:
    client = client_for(project, tmp_path / "config")
    client.post("/api/project/open", json={"path": str(project)})
    endpoint = "/api/domains/pharma/sources"
    original = client.get(endpoint).json()
    broken = {"revision": original["revision"], "sources": {"bad.meld": "(unterminated"}}
    assert client.put(endpoint, json=broken).status_code != 200
    assert client.get(endpoint).json() == original


def test_profile_probe_redacts_upstream_errors(project: Path, tmp_path: Path) -> None:
    import urllib.error

    client = client_for(project, tmp_path / "config")
    error = urllib.error.HTTPError("http://localhost", 401, "secret-value", {}, None)
    with patch("aegis.editor.provider_api.open_provider_request", side_effect=error):
        result = client.post("/api/llm/profiles/lm-studio/probe")
    assert result.status_code == 200
    assert result.json()["errorType"] == "auth"
    assert "secret-value" not in result.text


def test_inference_blocked_before_network_for_remote_destination(
    project: Path, tmp_path: Path
) -> None:
    client = client_for(project, tmp_path / "config")
    settings = client.get("/api/llm/settings").json()
    settings.pop("credentialStatus")
    settings["profiles"].append(
        {
            "id": "external",
            "name": "External",
            "type": "remote",
            "baseUrl": "https://example.com/v1",
            "model": "model",
        }
    )
    client.put("/api/llm/settings", json=settings)
    with (
        patch(
            "aegis.editor.mediation.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("93.184.216.34", 443))],
        ),
        patch("aegis.editor.llm_provider.open_provider_request") as send,
    ):
        response = client.post("/api/llm/profiles/external/capability", json={"model": "model"})
    assert response.status_code == 403, response.text
    send.assert_not_called()


def test_source_path_traversal_rejected(project: Path, tmp_path: Path) -> None:
    client = client_for(project, tmp_path / "config")
    client.post("/api/project/open", json={"path": str(project)})
    endpoint = "/api/domains/pharma/sources"
    data = client.get(endpoint).json()
    data["sources"]["../escape.meld"] = "(case Escape)"
    assert client.put(endpoint, json=data).status_code == 409
    assert not (project / "escape.meld").exists()


def test_review_publish_activate_restart_and_stale_review(project: Path, tmp_path: Path) -> None:
    config = tmp_path / "config"
    client = client_for(project, config)
    client.post("/api/project/open", json={"path": str(project)})
    domain = client.get("/api/domains/pharma").json()
    revision = domain["revision"]
    scenarios = [
        {
            "id": "allow",
            "name": "Reporting allowed",
            "expected": "PERMITTED",
            "action": {
                "agent": "prescribingAgent",
                "actionType": "reportAdverseEvent",
                "parameters": {"severity": "majorInteraction"},
            },
        },
        {
            "id": "deny",
            "name": "Unsafe prescription blocked",
            "expected": "FORBIDDEN",
            "action": {
                "agent": "prescribingAgent",
                "actionType": "prescribeMedication",
                "parameters": {"drug": "controlledSubstance", "severity": "majorInteraction"},
            },
        },
    ]
    # Use the reference domain's actual declared parameter names.
    from aegis.guard.guard import Guard

    guard = Guard.from_meld_files(sorted((project / "pharma").glob("*.meld")))
    schema = guard._registry.get_schema("prescribeMedication")
    assert schema is not None
    # The fixture vocabulary explicitly defines drug + severity.
    saved = client.put(
        "/api/domains/pharma/scenarios", json={"revision": revision, "scenarios": scenarios}
    )
    assert saved.status_code == 200, saved.text
    tests = client.post("/api/domains/pharma/scenarios/run")
    assert tests.status_code == 200, tests.text
    assert tests.json()["passed"], tests.text
    endpoint = "/api/domains/pharma/governance"
    assert (
        client.post(
            endpoint + "/publish",
            json={"revision": revision, "version": "1.0.0", "message": "test"},
        ).status_code
        == 409
    )
    review = client.post(
        endpoint + "/review",
        json={
            "revision": revision,
            "message": "Reviewed reference scenarios",
            "acknowledgeLimits": True,
        },
    )
    assert review.status_code == 200, review.text
    assert review.json()["canPublish"]
    release = client.post(
        endpoint + "/publish",
        json={"revision": revision, "version": "1.0.0", "message": "Reference release"},
    )
    assert release.status_code == 200, release.text
    activation = client.post(endpoint + "/activate", json={"version": "1.0.0"})
    assert activation.status_code == 200, activation.text
    restarted = client_for(project, config)
    runtime = restarted.post("/api/domains/pharma/runtime/check", json=scenarios[0]["action"])
    assert runtime.status_code == 200, runtime.text
    assert runtime.json()["decision"] == "PERMITTED"
    data = restarted.get("/api/domains/pharma/sources").json()
    name = next(iter(data["sources"]))
    data["sources"][name] += "\n;; new draft\n"
    assert restarted.put("/api/domains/pharma/sources", json=data).status_code == 200
    status = restarted.get(endpoint).json()
    assert not status["reviewCurrent"]
    assert not status["canPublish"]
    assert status["activeVersion"] == "1.0.0"
    assert (
        restarted.post("/api/domains/pharma/runtime/check", json=scenarios[0]["action"]).json()[
            "revision"
        ]
        == revision
    )


def test_cancelled_job_never_adopts_late_result() -> None:
    import asyncio

    from aegis.editor.jobs import JobTracker

    async def exercise() -> None:
        gate = asyncio.Event()
        tracker = JobTracker()

        async def work() -> dict[str, str]:
            await gate.wait()
            return {"unexpected": "late result"}

        job = tracker.start("domain", work)
        await asyncio.sleep(0)
        tracker.cancel(job.id)
        gate.set()
        await asyncio.sleep(0)
        assert job.status == "cancelled"
        assert job.result is None

    asyncio.run(exercise())


def test_manual_rule_editor_preserves_sources_and_uses_current_guard(
    project: Path, tmp_path: Path
) -> None:
    client = client_for(project, tmp_path / "config")
    client.post("/api/project/open", json={"path": str(project)})
    domain = client.get("/api/domains/pharma").json()
    rule = next(
        r
        for r in domain["rules"]
        if r["agentRole"] == "prescribingAgent"
        and r["proposition"] == "reportAdverseEvent majorInteraction"
    )
    response = client.put(
        f"/api/domains/pharma/source-rules/{rule['id']}",
        json={**rule, "modality": "FORBIDDEN", "revision": domain["revision"]},
    )
    assert response.status_code == 200, response.text
    result = client.post(
        "/api/domains/pharma/check",
        json={
            "agent": "prescribingAgent",
            "actionType": "reportAdverseEvent",
            "parameters": {"severity": "majorInteraction"},
        },
    )
    assert result.json()["decision"] == "FORBIDDEN"
    rules = response.json()["rules"]
    assert any(r["id"] == rule["id"] and r["modality"] == "FORBIDDEN" for r in rules)
    exported = client.get("/api/domains/pharma/export").json()
    assert "PharmaDomainOntologyMt.meld" in exported["files"]
    assert ";;" in exported["files"]["PharmaDeonticRulesMt.meld"]


def test_proposal_parameters_use_domain_order_and_full_snapshot(
    project: Path, tmp_path: Path
) -> None:
    client = client_for(project, tmp_path / "config")
    client.post("/api/project/open", json={"path": str(project)})
    proposal = {
        "modality": "PERMITTED",
        "agentRole": "pharmacistAgent",
        "codeOfConduct": "PharmaCompliance",
        "actionType": "reportAdverseEvent",
        "propositionParameters": {"severity": "majorInteraction"},
        "defeasible": True,
        "meldExpression": (
            "(permittedToDo-WRT PharmaCompliance pharmacistAgent "
            "(reportAdverseEvent majorInteraction))"
        ),
    }
    result = client.post("/api/domains/pharma/verify", json=proposal)
    assert result.status_code == 200, result.text
    assert result.json()["passed"], result.text
    bad = {
        **proposal,
        "meldExpression": (
            "(permittedToDo-WRT PharmaCompliance pharmacistAgent "
            "(reportAdverseEvent severity majorInteraction))"
        ),
    }
    assert not client.post("/api/domains/pharma/verify", json=bad).json()["passed"]
    accepted = client.post(
        "/api/domains/pharma/proposals/accept",
        json={**proposal, "revision": result.json()["revision"]},
    )
    assert accepted.status_code == 200, accepted.text
    assert "EditorProposals.meld" in client.get("/api/domains/pharma/sources").json()["sources"]


def test_source_editor_handles_strings_and_comments() -> None:
    from aegis.editor.source_edit import replace_assertion

    original = (
        '; (comment)\n(case Test)\n(comment Role "text (with) ; punctuation")\n(isa Role Agent)\n'
    )
    changed = replace_assertion(original, 3, "(isa Role OtherAgent)")
    assert '(comment Role "text (with) ; punctuation")' in changed
    assert changed.endswith("(isa Role OtherAgent)\n")


def test_empty_project_structure_persists_and_rename_updates_rules(
    project: Path, tmp_path: Path
) -> None:
    client = client_for(project, tmp_path / "config")
    client.post("/api/project/open", json={"path": str(project)})
    created = client.post("/api/domains", json={"name": "Workshop"})
    assert created.status_code == 200, created.text
    domain = created.json()
    endpoint = "/api/domains/workshop/structure"
    for body in [
        {"kind": "role", "name": "operator", "description": "Local role"},
        {"kind": "code", "name": "WorkshopCode"},
        {"kind": "action", "name": "inspectArtifact", "parameters": []},
    ]:
        result = client.post(endpoint, json={**body, "revision": domain["revision"]})
        assert result.status_code == 200, result.text
        domain = result.json()
    assert domain["roles"][0]["name"] == "operator"
    rule = client.post(
        "/api/domains/workshop/source-rules",
        json={
            "revision": domain["revision"],
            "agentRole": "operator",
            "code": "WorkshopCode",
            "modality": "PERMITTED",
            "proposition": "inspectArtifact",
        },
    )
    assert rule.status_code == 200, rule.text
    domain = rule.json()
    assert (
        client.post(
            endpoint,
            json={
                "revision": domain["revision"],
                "kind": "role",
                "name": "operator",
                "operation": "delete",
            },
        ).status_code
        == 409
    )
    renamed = client.post(
        endpoint,
        json={
            "revision": domain["revision"],
            "kind": "role",
            "previous": "operator",
            "name": "reviewer",
            "operation": "update",
        },
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["rules"][0]["agentRole"] == "reviewer"
    result = client.post(
        "/api/domains/workshop/check", json={"agent": "reviewer", "actionType": "inspectArtifact"}
    )
    assert result.json()["decision"] == "PERMITTED"


def test_transport_pins_checked_dns_and_does_not_follow_redirects() -> None:
    import threading
    import urllib.error
    import urllib.request
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    seen: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            seen.append(self.path)
            if self.path == "/redirect":
                self.send_response(307)
                self.send_header("Location", "/credential-trap")
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"data": []}')

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        provider = LLMProviderInfo(
            "local", "Local", "local", f"http://localhost:{port}", loopback_only=True
        )
        with patch(
            "aegis.editor.llm_provider.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("127.0.0.1", port))],
        ) as resolve:
            with open_provider_request(
                urllib.request.Request(provider.base_url + "/models"), provider, 2
            ) as response:
                assert json.loads(response.read()) == {"data": []}
            assert resolve.call_count == 1
            with pytest.raises(urllib.error.HTTPError) as error:
                open_provider_request(
                    urllib.request.Request(provider.base_url + "/redirect"), provider, 2
                )
            assert error.value.code == 307
        assert "/credential-trap" not in seen
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_rebinding_cannot_change_local_mediation_to_external() -> None:
    import urllib.request

    provider = LLMProviderInfo(
        "local", "Local", "local", "http://localhost:1234/v1", loopback_only=True
    )
    with (
        patch(
            "aegis.editor.llm_provider.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("93.184.216.34", 1234))],
        ),
        patch("aegis.editor.llm_provider.socket.socket") as connect,
    ):
        with pytest.raises(ValueError, match="local mediation"):
            open_provider_request(
                urllib.request.Request(provider.base_url + "/models"), provider, 1
            )
        connect.assert_not_called()


def test_backup_restores_sources_profiles_and_session(project: Path, tmp_path: Path) -> None:
    from aegis.editor.backup import backup_project, restore_project

    config = tmp_path / "config"
    client = client_for(project, config)
    client.post("/api/project/open", json={"path": str(project)})
    data = client.get("/api/domains/pharma/sources").json()
    data["sources"][next(iter(data["sources"]))] += "\n;; backed up draft\n"
    saved = client.put("/api/domains/pharma/sources", json=data).json()
    archive = tmp_path / "backup.zip"
    backup_project(project, config, archive)
    assert archive.stat().st_mode & 0o777 == 0o600
    restored = tmp_path / "restored"
    restored_config = tmp_path / "restored-config"
    restore_project(archive, restored, restored_config)
    restarted = client_for(restored, restored_config)
    assert restarted.get("/api/project").json()["path"] == str(restored)
    assert restarted.get("/api/domains/pharma").json()["revision"] == saved["revision"]
    assert restarted.get("/api/domains/pharma/sources").json()["sources"] == data["sources"]
    with pytest.raises(ValueError, match="empty"):
        restore_project(archive, restored, restored_config)


def test_restore_rejects_traversal_and_checksum_before_writes(tmp_path: Path) -> None:
    import hashlib
    from zipfile import ZipFile

    from aegis.editor.backup import restore_project

    for name, checksum in [
        ("project/../../escape", hashlib.sha256(b"x").hexdigest()),
        ("project/a.meld", "incorrect"),
    ]:
        archive = tmp_path / "invalid.zip"
        with ZipFile(archive, "w") as output:
            output.writestr(name, "x")
            output.writestr(
                "manifest.json",
                json.dumps({"schemaVersion": 1, "projectRoot": "/old", "files": {name: checksum}}),
            )
        with pytest.raises(ValueError):
            restore_project(archive, tmp_path / "restored", tmp_path / "config")
        assert not (tmp_path / "restored").exists()
        assert not (tmp_path / "escape").exists()


def test_dip_job_adopts_only_reviewed_draft_without_overwrite(
    project: Path, tmp_path: Path
) -> None:
    import time

    app = create_editor_app(project, tmp_path / "config")
    app.state.capabilities.add((0, "lm-studio", "fixture-model"))

    def pipeline(
        source: str, name: str, client: object, output: Path, **kwargs: object
    ) -> MagicMock:
        assert Path(source).read_text() == "Operators may report adverse events."
        shutil.copytree(DOMAINS / "pharma", output)
        (output / "review.md").write_text("Fixture extraction: inspect rules before adoption")
        result = MagicMock()
        result.summary.return_value = "Deterministic fixture, no live model"
        return result

    with TestClient(app, headers={**HEADERS, "X-Aegis-Project": str(project.resolve())}) as client:
        client.post("/api/project/open", json={"path": str(project)})
        with patch("aegis.editor.dip_api.run_pipeline", side_effect=pipeline):
            response = client.post(
                "/api/dip/jobs",
                json={
                    "name": "trial",
                    "title": "Trial",
                    "content": "Operators may report adverse events.",
                    "providerId": "lm-studio",
                    "modelId": "fixture-model",
                },
            )
            assert response.status_code == 202, response.text
            job_id = response.json()["id"]
            for _ in range(100):
                job = client.get(f"/api/jobs/{job_id}").json()
                if job["status"] not in {"queued", "running"}:
                    break
                time.sleep(0.01)
            assert job["status"] == "succeeded", job
        assert not (project / "generated-trial").exists()
        adopted = client.post(f"/api/dip/jobs/{job_id}/adopt")
        assert adopted.status_code == 200, adopted.text
        domain = next(d for d in adopted.json()["domains"] if d["id"] == "generated-trial")
        assert domain["status"] == "Draft"
        assert client.post(f"/api/dip/jobs/{job_id}/adopt").status_code == 409
        assert (
            client.post(
                "/api/domains/generated-trial/runtime/check",
                json={
                    "agent": "prescribingAgent",
                    "actionType": "reportAdverseEvent",
                    "parameters": {"severity": "majorInteraction"},
                },
            ).status_code
            == 409
        )


def test_legacy_mutations_cannot_diverge_from_source_guard(project: Path, tmp_path: Path) -> None:
    client = client_for(project, tmp_path / "config")
    client.post("/api/project/open", json={"path": str(project)})
    rule = client.get("/api/domains/pharma").json()["rules"][0]
    assert client.delete(f"/api/domains/pharma/rules/{rule['id']}").status_code == 409
    assert client.post("/api/domains/pharma/rules", json=rule).status_code == 409


@pytest.mark.parametrize(
    "kind,action,argument",
    [
        ("obligateSequence", "reportAdverseEvent", "prescribeMedication"),
        ("forbidAggregate", "reportAdverseEvent", "3"),
        ("obligateWithin", "reportAdverseEvent", "60"),
        ("requirePrecondition", "reportAdverseEvent", "(reviewStatus approved)"),
    ],
)
def test_plan_constraint_roundtrip(
    project: Path, tmp_path: Path, kind: str, action: str, argument: str
) -> None:
    config = tmp_path / "config"
    client = client_for(project, config)
    client.post("/api/project/open", json={"path": str(project)})
    endpoint = "/api/domains/pharma/plan-constraints"
    revision = client.get(endpoint).json()["revision"]
    result = client.post(
        endpoint, json={"revision": revision, "kind": kind, "action": action, "argument": argument}
    )
    assert result.status_code == 200, result.text
    restarted = client_for(project, config)
    constraint = restarted.get(endpoint).json()["constraints"][0]
    assert constraint["kind"] == kind
    assert constraint["argument"] == argument
    deleted = restarted.post(
        endpoint, json={**constraint, "operation": "delete", "revision": result.json()["revision"]}
    )
    assert deleted.status_code == 200, deleted.text
    assert restarted.get(endpoint).json()["constraints"] == []


def test_metadata_and_package_import_persist(project: Path, tmp_path: Path) -> None:
    config = tmp_path / "config"
    client = client_for(project, config)
    client.post("/api/project/open", json={"path": str(project)})
    metadata = client.get("/api/domains/pharma/metadata").json()
    metadata.update(name="Reviewed Pharma", description="Persistent metadata", archived=True)
    result = client.put("/api/domains/pharma/metadata", json=metadata)
    assert result.status_code == 200, result.text
    assert client.put("/api/domains/pharma/metadata", json=metadata).status_code == 409
    restarted = client_for(project, config)
    domain = restarted.get("/api/domains/pharma").json()
    assert domain["name"] == "Reviewed Pharma"
    assert domain["status"] == "Archived"
    exported = restarted.get("/api/domains/pharma/export").json()
    body = {"name": "copy", "files": exported["files"]}
    preview = restarted.post("/api/project/import/preview", json=body)
    assert preview.status_code == 200, preview.text
    assert not preview.json()["collision"]
    assert restarted.post("/api/project/import", json=body).status_code == 409
    adopted = restarted.post(
        "/api/project/import", json={**body, "previewRevision": preview.json()["revision"]}
    )
    assert adopted.status_code == 200, adopted.text
    assert restarted.get("/api/domains/copy/sources").json()["sources"] == body["files"]
    assert restarted.post("/api/project/import/preview", json=body).json()["collision"]


def test_invalid_settings_never_echo_secret_values(project: Path, tmp_path: Path) -> None:
    client = client_for(project, tmp_path / "config")
    response = client.put("/api/llm/settings", json={"apiKey": "secret-that-must-not-echo"})
    assert response.status_code == 422
    assert "secret-that-must-not-echo" not in response.text


def test_configured_parameters_and_capability_are_revision_bound(
    project: Path, tmp_path: Path
) -> None:
    app = create_editor_app(project, tmp_path / "config")
    client = TestClient(app, headers=HEADERS)
    settings = client.get("/api/llm/settings").json()
    settings.pop("credentialStatus")
    settings["profiles"][0].update(model="test-model", temperature=0.3, maxTokens=321, timeout=17)
    revision = client.put("/api/llm/settings", json=settings).json()["revision"]
    response = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "report_capability",
                                "arguments": '{"supported":true}',
                            }
                        }
                    ]
                }
            }
        ]
    }
    calls = []

    def chat(self: LLMClient, *args: object) -> dict:
        calls.append((self.model_id, self._temperature, self._max_tokens, self._timeout))
        return response

    with patch.object(LLMClient, "chat", chat):
        tested = client.post("/api/llm/profiles/lm-studio/capability", json={"model": "test-model"})
    assert tested.json()["passed"]
    assert calls == [("test-model", 0.3, 321, 17)]
    assert (revision, "lm-studio", "test-model") in app.state.capabilities
    with patch.object(LLMClient, "chat", return_value={"choices": []}):
        failed = client.post("/api/llm/profiles/lm-studio/capability", json={"model": "test-model"})
    assert not failed.json()["passed"]
    assert not app.state.capabilities
    settings["revision"] = revision
    client.put("/api/llm/settings", json=settings)
    assert not app.state.capabilities


def test_meld_code_prevalence_changes_actual_guard_and_cannot_be_overridden(tmp_path: Path) -> None:
    from aegis.guard.action import Action
    from aegis.guard.guard import Guard

    path = tmp_path / "rules.meld"
    source = """(aegis-schema-version 1)
(case TestMt)
(isa actor IntelligentAgent)
(isa inspect ActionType)
(isa CodeA CodeOfConduct)
(isa CodeB CodeOfConduct)
(permittedToDo-WRT CodeA actor (inspect))
(forbiddenToDo-WRT CodeB actor (inspect))
"""
    action = Action(action_type="inspect", agent_id="actor")
    path.write_text(source + "(codePrevalence CodeA CodeB)\n")
    assert Guard.from_meld_files([path]).check(action).decision.value == "PERMITTED"
    with pytest.raises(ValueError, match="overridden"):
        Guard.from_meld_files([path], code_prevalence=["CodeB", "CodeA"])
    path.write_text(source + "(codePrevalence CodeB CodeA)\n")
    assert Guard.from_meld_files([path]).check(action).decision.value == "FORBIDDEN"
    path.write_text(source + "(codePrevalence MissingCode)\n")
    with pytest.raises(ValueError, match="undeclared"):
        Guard.from_meld_files([path])
    path.write_text(source + "(codePrevalence CodeA CodeA)\n")
    from aegis.errors import MeldSyntaxError

    with pytest.raises(MeldSyntaxError):
        Guard.from_meld_files([path])


def test_code_prevalence_editor_persists_to_export(project: Path, tmp_path: Path) -> None:
    client = client_for(project, tmp_path / "config")
    client.post("/api/project/open", json={"path": str(project)})
    domain = client.get("/api/domains/pharma").json()
    codes = [c["name"] for c in domain["codes"]]
    result = client.post(
        "/api/domains/pharma/code-prevalence", json={"revision": domain["revision"], "codes": codes}
    )
    assert result.status_code == 200, result.text
    assert result.json()["codePrevalence"] == codes
    restarted = client_for(project, tmp_path / "config")
    assert restarted.get("/api/domains/pharma").json()["codePrevalence"] == codes
    assert (
        "codePrevalence"
        in restarted.get("/api/domains/pharma/export").json()["files"]["EditorCodePrevalence.meld"]
    )


def test_editor_policy_covers_inference_channels_and_fails_closed() -> None:
    from aegis.guard.action import Action
    from aegis.guard.guard import Guard

    policy = Path(__file__).parents[2] / "aegis/editor/policy"
    guard = Guard.from_meld_files(sorted(policy.glob("*.meld")))
    for channel in ("metadataChannel", "capabilityChannel", "authoringChannel", "documentChannel"):
        for classification in ("publicData", "internalData", "confidentialData"):
            fields = {
                "destination": "localEndpoint",
                "classification": classification,
                "channel": channel,
            }
            assert (
                guard.check(
                    Action(
                        action_type="sendEditorInference",
                        agent_id="localOperator",
                        proposition=fields,
                    )
                ).decision.value
                == "PERMITTED"
            )
            fields["destination"] = "remoteEndpoint"
            assert (
                guard.check(
                    Action(
                        action_type="sendEditorInference",
                        agent_id="localOperator",
                        proposition=fields,
                    )
                ).decision.value
                == "FORBIDDEN"
            )
    for fields in (
        {},
        {
            "destination": "localEndpoint",
            "classification": "unknown",
            "channel": "authoringChannel",
        },
        {
            "destination": "localEndpoint",
            "classification": "confidentialData",
            "channel": "unmodeledChannel",
        },
    ):
        assert (
            guard.check(
                Action(
                    action_type="sendEditorInference", agent_id="localOperator", proposition=fields
                )
            ).decision.value
            != "PERMITTED"
        )


def test_stale_browser_project_cannot_write_identical_domain_in_other_project(
    project: Path, tmp_path: Path
) -> None:
    client = client_for(project.parent, tmp_path / "config")
    first = project
    second = project.parent / "second"
    shutil.copytree(first, second)
    client.headers["X-Aegis-Project"] = str(first)
    client.post("/api/project/open", json={"path": str(first)})
    draft = client.get("/api/domains/pharma/sources").json()
    assert client.post("/api/project/open", json={"path": str(second)}).status_code == 200
    assert client.put("/api/domains/pharma/sources", json=draft).status_code == 409
    assert client.get("/api/domains/pharma/sources").status_code == 409
