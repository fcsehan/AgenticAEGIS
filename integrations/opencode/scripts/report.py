"""Create a compact evidence manifest from completed integration test reports."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def counts(path: Path) -> dict[str, int]:
    cases = list(ET.parse(path).getroot().iter("testcase"))
    result = {"passed": 0, "failed": 0, "skipped": 0}
    for case in cases:
        if case.find("failure") is not None or case.find("error") is not None:
            result["failed"] += 1
        elif case.find("skipped") is not None:
            result["skipped"] += 1
        else:
            result["passed"] += 1
    if not cases:
        raise RuntimeError(f"No test cases in {path.name}")
    return result


def main() -> None:
    directory = Path(sys.argv[1])
    lock = json.loads((ROOT / "upstream.lock.json").read_text())
    inputs = [ROOT / "upstream.lock.json", ROOT / "runtime/package-lock.json"]
    for folder in ("plugin", "tests", "fixtures", "scripts"):
        inputs.extend(
            p for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts
        )
    results: dict[str, Any] = {
        "created_at": datetime.now(UTC).isoformat(),
        "opencode_release": lock["release"],
        "opencode_commit": lock["commit"],
        "installed": json.loads((ROOT / ".cache/installed.json").read_text()),
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "node": subprocess.check_output(["node", "--version"], text=True).strip(),
        },
        "suites": {
            "plugin": counts(directory / "plugin.xml"),
            "process": counts(directory / "process.xml"),
        },
        "inputs_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(inputs)
        },
        "cases": {
            p.stem: json.loads(p.read_text()) for p in sorted((directory / "cases").glob("*.json"))
        },
    }
    (directory / "report.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results["suites"], indent=2))
    if any(s["failed"] for s in results["suites"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
