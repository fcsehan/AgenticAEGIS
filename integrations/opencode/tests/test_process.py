"""Real OpenCode process + real AEGIS HTTP sidecar + deterministic model transport."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
BINARY = ROOT / ".cache/opencode"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request(url: str, data: dict[str, Any] | None = None) -> Any:
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.load(response)


@pytest.fixture(scope="session", autouse=True)
def verified_binary() -> None:
    assert BINARY.is_file(), "Run integrations/opencode/scripts/setup.sh first"
    installed = json.loads((ROOT / ".cache/installed.json").read_text())
    lock = json.loads((ROOT / "upstream.lock.json").read_text())
    assert installed["commit"] == lock["commit"]
    assert installed["artifact_sha256"] == lock["artifacts"][installed["platform"]]["sha256"]
    assert hashlib.sha256(BINARY.read_bytes()).hexdigest() == installed["binary_sha256"]


@contextmanager
def model_server(calls: list[dict[str, Any]]) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    received: list[dict[str, Any]] = []
    emitted: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append(body)
            available = {t["function"]["name"] for t in body.get("tools", [])}
            call = calls[len(emitted)] if available and len(emitted) < len(calls) else None
            if call:
                assert call["tool"] in available, f"Missing real OpenCode tool: {call['tool']}"
                emitted.append(call)
                delta = {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": f"call_{len(emitted)}",
                            "type": "function",
                            "function": {
                                "name": call["tool"],
                                "arguments": json.dumps(call["args"]),
                            },
                        }
                    ],
                }
                finish = "tool_calls"
            else:
                delta, finish = {"role": "assistant", "content": "Evidence run complete."}, "stop"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for payload in [
                {
                    "id": "fixture",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "aegis-fixture",
                    "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
                },
                {
                    "id": "fixture",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "aegis-fixture",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
                },
            ]:
                self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", received
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def sidecar(tmp_path: Path) -> Iterator[tuple[str, Path]]:
    port = free_port()
    audit = tmp_path / "guard-audit.jsonl"
    env = {**os.environ, "AEGIS_AUDIT_PATH": str(audit)}
    with (tmp_path / "sidecar.log").open("w") as log:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "from aegis.cli import main; main()",
                "serve",
                "--domains",
                str(ROOT / "fixtures/domain"),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=REPO,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        url = f"http://127.0.0.1:{port}"
        try:
            for _ in range(100):
                if proc.poll() is not None:
                    pytest.fail((tmp_path / "sidecar.log").read_text())
                try:
                    request(f"{url}/v1/health")
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                pytest.fail("Sidecar did not become ready")
            yield url, audit
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


def run_case(
    tmp_path: Path,
    calls: list[dict[str, Any]],
    guard_url: str,
    *,
    plan: dict[str, Any] | None = None,
    live: bool = False,
) -> list[dict[str, Any]]:
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    audit = tmp_path / "plugin-audit.jsonl"
    private = tmp_path / "private"
    private.mkdir()
    config_dir = private / "opencode"
    config_dir.mkdir()
    for name in ("package.json", "package-lock.json"):
        shutil.copyfile(ROOT / "runtime" / name, config_dir / name)
    (config_dir / "node_modules").symlink_to(
        ROOT / ".cache/runtime/node_modules", target_is_directory=True
    )
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("OPENCODE_", "AEGIS_", "OPENAI_", "ANTHROPIC_"))
    }
    env.update(
        {
            "PWD": str(workspace),
            "XDG_CONFIG_HOME": str(private / "config"),
            "XDG_DATA_HOME": str(private / "data"),
            "XDG_CACHE_HOME": str(private / "cache"),
            "XDG_STATE_HOME": str(private / "state"),
            "OPENCODE_CONFIG_DIR": str(private / "opencode"),
            "OPENCODE_DISABLE_PROJECT_CONFIG": "true",
            "OPENCODE_DISABLE_DEFAULT_PLUGINS": "true",
            "OPENCODE_DISABLE_EXTERNAL_SKILLS": "true",
            "OPENCODE_DISABLE_CLAUDE_CODE": "true",
            "OPENCODE_DISABLE_MODELS_FETCH": "true",
            "OPENCODE_DISABLE_AUTOUPDATE": "true",
            "OPENCODE_DISABLE_LSP_DOWNLOAD": "true",
            "AEGIS_OPENCODE_GUARD_URL": guard_url,
            "AEGIS_OPENCODE_AUDIT_PATH": str(audit),
            "AEGIS_OPENCODE_TIMEOUT_MS": "250",
        }
    )
    if plan:
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))
        env["AEGIS_OPENCODE_PLAN"] = str(plan_file)
    live_model = os.environ.get("AEGIS_OPENCODE_LIVE_MODEL", "")
    live_url = os.environ.get("AEGIS_OPENCODE_LIVE_URL", "")
    if live:
        assert live_model and live_url, "Set AEGIS_OPENCODE_LIVE_MODEL and AEGIS_OPENCODE_LIVE_URL"
        from urllib.parse import urlparse

        assert urlparse(live_url).hostname in {"127.0.0.1", "localhost", "::1"}, (
            "Live evidence uses a local model endpoint"
        )
    transport: AbstractContextManager[tuple[str, list[dict[str, Any]]]] = (
        nullcontext((live_url, [])) if live else model_server(calls)
    )
    with transport as (base_url, received):
        model_id = live_model if live else "aegis-fixture"
        config = {
            "$schema": "https://opencode.ai/config.json",
            "plugin": [(ROOT / "plugin/index.mjs").as_uri()],
            "model": f"fixture/{model_id}",
            "small_model": f"fixture/{model_id}",
            "share": "disabled",
            "permission": "allow",
            "lsp": False,
            "formatter": False,
            "provider": {
                "fixture": {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "Local evidence fixture",
                    "options": {"baseURL": base_url, "apiKey": "fixture-local-only"},
                    "models": {
                        model_id: {
                            "name": "Evidence fixture",
                            "limit": {"context": 32768, "output": 2048},
                        }
                    },
                }
            },
        }
        env["OPENCODE_CONFIG_CONTENT"] = json.dumps(config)
        prompt = (
            (
                "Use the write tool directly, exactly once, with these arguments: "
                + json.dumps(calls[0]["args"])
                + ". Do not use read, bash, edit or apply_patch. "
                "If the tool is blocked, report the block and stop without retrying."
            )
            if live
            else "Perform the requested evidence fixture actions."
        )
        proc = subprocess.run(
            [str(BINARY), "run", "--format", "json", prompt],
            cwd=workspace,
            env=env,
            capture_output=True,
            text=True,
            timeout=300 if live else 90,
        )
        (tmp_path / "opencode.stdout").write_text(proc.stdout)
        (tmp_path / "opencode.stderr").write_text(proc.stderr)
        assert proc.returncode == 0, proc.stderr[-5000:]
        assert live or received, (
            f"OpenCode never contacted the model: {proc.stderr[-5000:]} {proc.stdout[-5000:]}"
        )
    assert audit.exists(), (
        f"AEGIS plugin did not initialize: {proc.stderr[-5000:]} {proc.stdout[-5000:]}"
    )
    records = [json.loads(line) for line in audit.read_text().splitlines()]
    assert any(r["event"] in {"decision", "plan_decision", "blocked"} for r in records), (
        records,
        proc.stdout,
    )
    results = os.environ.get("AEGIS_OPENCODE_RESULTS")
    if results:
        target = Path(results) / "cases"
        target.mkdir(parents=True, exist_ok=True)
        evidence = {
            "model": model_id,
            "transport": "local-live-model" if live else "deterministic-model-fixture",
            "events": records,
            "effects": [
                {
                    "tool": c["tool"],
                    "path": c["args"].get("filePath"),
                    "exists": Path(c["args"]["filePath"]).exists(),
                }
                for c in calls
                if "filePath" in c["args"]
            ],
        }
        serialized = (
            json.dumps(evidence, indent=2)
            .replace(str(tmp_path), "<case>")
            .replace(str(REPO), "<repository>")
        )
        (target / f"{tmp_path.name}.json").write_text(serialized + "\n")
    return records


def write_call(tmp_path: Path, name: str = "allowed.txt") -> dict[str, Any]:
    return {
        "tool": "write",
        "args": {
            "filePath": str(tmp_path / "workspace" / name),
            "content": "AEGIS process evidence\n",
        },
    }


def test_permitted_execution_and_audit(tmp_path: Path, sidecar: tuple[str, Path]) -> None:
    url, audit = sidecar
    call = write_call(tmp_path)
    records = run_case(tmp_path, [call], url)
    assert Path(call["args"]["filePath"]).read_text() == call["args"]["content"]
    decision = next(r for r in records if r["event"] == "decision")
    executed = next(r for r in records if r["event"] == "executed")
    assert decision["verdict"]["decision"] == "PERMITTED"
    assert decision["arguments_sha256"] == executed["arguments_sha256"]
    assert decision["call_id"] == executed["call_id"]
    assert request(url + "/v1/audit/verify", {})["valid"]
    assert audit.exists()


def test_read_then_edit(tmp_path: Path, sidecar: tuple[str, Path]) -> None:
    target = tmp_path / "workspace" / "allowed.txt"
    target.parent.mkdir()
    target.write_text("Original text\n")
    calls = [
        {"tool": "read", "args": {"filePath": str(target)}},
        {
            "tool": "edit",
            "args": {"filePath": str(target), "oldString": "Original", "newString": "Updated"},
        },
    ]
    records = run_case(tmp_path, calls, sidecar[0])
    assert target.read_text() == "Updated text\n"
    assert [r["tool"] for r in records if r["event"] == "executed"] == ["read", "edit"]


def test_forbidden_has_no_effect(tmp_path: Path, sidecar: tuple[str, Path]) -> None:
    call = write_call(tmp_path, "protected.txt")
    target = Path(call["args"]["filePath"])
    target.parent.mkdir()
    target.write_text("Original protected content\n")
    records = run_case(tmp_path, [call], sidecar[0])
    assert target.read_text() == "Original protected content\n"
    assert any(r.get("verdict", {}).get("decision") == "FORBIDDEN" for r in records)
    assert not any(r["event"] == "executed" for r in records)


def test_outage_has_no_effect(tmp_path: Path) -> None:
    call = write_call(tmp_path)
    records = run_case(tmp_path, [call], f"http://127.0.0.1:{free_port()}")
    assert not Path(call["args"]["filePath"]).exists()
    assert any(r.get("verdict", {}).get("reason_type") == "GUARD_ERROR" for r in records)


def test_rejected_plan_stops_before_first_effect(tmp_path: Path, sidecar: tuple[str, Path]) -> None:
    calls = [write_call(tmp_path), write_call(tmp_path, "second.txt")]
    records = run_case(tmp_path, calls, sidecar[0], plan={"steps": calls})
    assert all(not Path(c["args"]["filePath"]).exists() for c in calls)
    assert any(r.get("verdict", {}).get("plan_decision") == "FORBIDDEN" for r in records)
    assert not any(r["event"] == "executed" for r in records)


def test_permitted_plan_executes(tmp_path: Path, sidecar: tuple[str, Path]) -> None:
    call = write_call(tmp_path)
    records = run_case(tmp_path, [call], sidecar[0], plan={"steps": [call]})
    assert Path(call["args"]["filePath"]).exists()
    assert any(r.get("verdict", {}).get("plan_decision") == "PERMITTED" for r in records)


def test_undecidable_has_no_effect(tmp_path: Path, sidecar: tuple[str, Path]) -> None:
    call = write_call(tmp_path, "uncertain.txt")
    records = run_case(tmp_path, [call], sidecar[0])
    assert not Path(call["args"]["filePath"]).exists()
    assert any(r.get("verdict", {}).get("decision") == "UNDECIDABLE" for r in records)
    assert not any(r["event"] == "executed" for r in records)


def test_unmodeled_shell_cannot_create_file(tmp_path: Path, sidecar: tuple[str, Path]) -> None:
    target = tmp_path / "workspace" / "shell-marker.txt"
    call = {
        "tool": "bash",
        "args": {
            "command": "printf bypass > shell-marker.txt",
            "description": "Attempt unmodeled shell write",
        },
    }
    records = run_case(tmp_path, [call], sidecar[0])
    assert not target.exists()
    assert any(r.get("verdict", {}).get("decision") == "UNDECIDABLE" for r in records)


def test_changed_plan_arguments_have_no_effect(tmp_path: Path, sidecar: tuple[str, Path]) -> None:
    declared = write_call(tmp_path)
    substituted = write_call(tmp_path, "second.txt")
    records = run_case(tmp_path, [substituted], sidecar[0], plan={"steps": [declared]})
    assert not Path(substituted["args"]["filePath"]).exists()
    assert any("differs from the declared plan" in r.get("reason", "") for r in records)
    assert not any(r["event"] == "executed" for r in records)


def test_timeout_has_no_effect(tmp_path: Path, sidecar: tuple[str, Path]) -> None:
    class SlowProxy(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            verdict = request(sidecar[0] + self.path, body)
            time.sleep(0.7)
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(verdict).encode())
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), SlowProxy)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        call = write_call(tmp_path)
        records = run_case(tmp_path, [call], f"http://127.0.0.1:{server.server_port}")
        assert not Path(call["args"]["filePath"]).exists()
        assert any(r.get("verdict", {}).get("reason_type") == "GUARD_ERROR" for r in records)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.skipif(
    os.environ.get("AEGIS_OPENCODE_LIVE") != "1", reason="Local live-model evidence is opt-in"
)
@pytest.mark.parametrize(
    "name,expected", [("allowed.txt", "PERMITTED"), ("protected.txt", "FORBIDDEN")]
)
def test_local_live_model(
    tmp_path: Path, sidecar: tuple[str, Path], name: str, expected: str
) -> None:
    call = write_call(tmp_path, name)
    records = run_case(tmp_path, [call], sidecar[0], live=True)
    assert any(r.get("verdict", {}).get("decision") == expected for r in records)
    assert Path(call["args"]["filePath"]).exists() == (expected == "PERMITTED")
