"""Check public source and built wheels without inspecting local credentials."""

from __future__ import annotations

import subprocess
import tarfile
import zipfile
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    tracked = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=root
    ).decode().split("\0")
    forbidden = {"node_modules", ".venv", "venv", "__pycache__", ".aegis-editor", ".cache", ".runs"}
    for name in filter(None, tracked):
        path = Path(name)
        assert not forbidden.intersection(path.parts), name
        assert path.suffix not in {".pyc", ".pdf", ".pem", ".key"}, name
        assert not path.name.startswith(".env"), name
        assert (root / path).stat().st_size < 5_000_000, name
    wheels = list((root / "dist").glob("*.whl"))
    assert wheels, "Build the wheel before running this check"
    for wheel in wheels:
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            for expected in (
                "aegis/editor/frontend/dist/index.html",
                "aegis/editor/frontend/dist/THIRD_PARTY_NOTICES.txt",
                "aegis/domains/devops/DevOpsPlanNormsMt.meld",
            ):
                assert expected in names, expected
            assert any(n.startswith("aegis/editor/policy/") and n.endswith(".meld") for n in names)
            assert any(n.endswith("/licenses/LICENSE") for n in names)
            assert any(n.endswith("/licenses/NOTICE") for n in names)
            assert any(n.endswith("/licenses/licenses/BPS.txt") for n in names)
            assert not any("node_modules/" in n or "frontend/src/" in n for n in names)
            metadata = archive.read(next(n for n in names if n.endswith(".dist-info/METADATA"))).decode()
            assert "Name: agentic-aegis" in metadata
            assert "License-Expression: Apache-2.0" in metadata
    for source in (root / "dist").glob("*.tar.gz"):
        with tarfile.open(source) as archive:
            names = [Path(member.name) for member in archive]
            assert not any(forbidden.intersection(name.parts) for name in names)
            assert any(str(name).endswith("integrations/opencode/plugin/index.mjs") for name in names)
            assert any(str(name).endswith("integrations/opencode/upstream.lock.json") for name in names)
            assert any(str(name).endswith("integrations/opencode/patches/OPENCODE_LICENSE") for name in names)
    print(f"Release surface checked: {len(list(filter(None, tracked)))} tracked files, {len(wheels)} wheel(s).")


if __name__ == "__main__":
    main()
