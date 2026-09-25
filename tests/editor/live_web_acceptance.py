"""Opt-in local inference acceptance including a real editor process restart."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:1234/v1")
    parser.add_argument("--port", type=int, default=18102)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="aegis-live-web-") as temporary:
        root = Path(temporary).resolve()
        workspace = root / "workspace"
        shutil.copytree(Path(__file__).parents[2] / "aegis/domains/pharma", workspace / "pharma")
        command = [
            sys.executable,
            "-m",
            "aegis.editor.app",
            "--workspace",
            str(workspace),
            "--config-dir",
            str(root / "config"),
            "--port",
            str(args.port),
        ]
        process = None
        with httpx.Client(
            base_url=f"http://127.0.0.1:{args.port}",
            timeout=180,
            headers={"X-Aegis-Editor": "1", "X-Aegis-Project": str(workspace)},
        ) as client:

            def start() -> subprocess.Popen:
                child = subprocess.Popen(
                    command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                for _ in range(100):
                    if child.poll() is not None:
                        raise RuntimeError("Editor process failed to start")
                    try:
                        if client.get("/api/health").is_success:
                            return child
                    except httpx.TransportError:
                        pass
                    time.sleep(0.05)
                child.terminate()
                child.wait(timeout=10)
                raise RuntimeError("Editor readiness timed out")

            def call(method: str, path: str, **kwargs: object) -> dict:
                response = client.request(method, path, **kwargs)
                response.raise_for_status()
                return response.json()

            try:
                process = start()
                call("POST", "/api/project/open", json={"path": str(workspace)})
                settings = call("GET", "/api/llm/settings")
                settings.pop("credentialStatus")
                settings["profiles"].append(
                    {
                        "id": "acceptance-local",
                        "name": "Acceptance local",
                        "type": "local",
                        "baseUrl": args.endpoint,
                        "model": args.model,
                        "temperature": 0,
                        "maxTokens": 4000,
                        "timeout": 120,
                        "allowPrivate": True,
                    }
                )
                settings["defaultProfile"] = "acceptance-local"
                saved = call("PUT", "/api/llm/settings", json=settings)
                revision = call("GET", "/api/domains/pharma")["revision"]
                process.terminate()
                process.wait(timeout=10)
                process = start()
                restored = call("GET", "/api/llm/settings")
                assert restored == saved
                assert call("GET", "/api/domains/pharma")["revision"] == revision
                assert client.get("/domain/pharma").status_code == 200
                probe = call("POST", "/api/llm/profiles/acceptance-local/probe")
                assert probe["available"], probe
                capability = call(
                    "POST",
                    "/api/llm/profiles/acceptance-local/capability",
                    json={"model": args.model},
                )
                assert capability["passed"], capability
                job = call(
                    "POST",
                    "/api/domains/pharma/jobs/generate",
                    json={
                        "providerId": "acceptance-local",
                        "modelId": args.model,
                        "description": "Generate exactly one permission: "
                        "pharmacistAgent is permitted "
                        "under PharmaCompliance to reportAdverseEvent "
                        "with severity majorInteraction. "
                        "Use existing vocabulary only.",
                    },
                )
                for _ in range(150):
                    job = call("GET", f"/api/jobs/{job['id']}")
                    if job["status"] not in {"queued", "running"}:
                        break
                    time.sleep(1)
                assert job["status"] == "succeeded", job
                result = job["result"]
                assert len(result["proposals"]) == 1, result
                verification = call(
                    "POST", "/api/domains/pharma/verify", json=result["proposals"][0]
                )
                assert verification["passed"], verification
                print(
                    json.dumps(
                        {
                            "processRestart": True,
                            "profilesRestored": True,
                            "domainRevisionRestored": True,
                            "deepLink": True,
                            "inference": result["inference"],
                            "proposalCount": result["count"],
                            "verification": [
                                {"stage": s["stage"], "status": s["status"]}
                                for s in verification["stages"]
                            ],
                        },
                        indent=2,
                    )
                )
            finally:
                if process is not None and process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)


if __name__ == "__main__":
    main()
