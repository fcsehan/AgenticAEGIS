"""Restore the archived fork patch against its exact upstream source."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tarfile

from setup import ROOT, download


def main() -> None:
    lock = json.loads((ROOT / "legacy.lock.json").read_text())
    patch = ROOT / lock["patch"]
    if hashlib.sha256(patch.read_bytes()).hexdigest() != lock["patch_sha256"]:
        raise SystemExit("Legacy patch checksum mismatch")
    cache = ROOT / ".cache"
    cache.mkdir(exist_ok=True)
    destination = cache / "legacy"
    if destination.exists():
        raise SystemExit("Legacy checkout already exists; retained without overwriting changes")
    archive = cache / "legacy.tar.gz"
    download(lock["source"], archive)
    destination.mkdir()
    with tarfile.open(archive) as content:
        content.extractall(destination, filter="data")
    source = destination / f"opencode-{lock['commit']}"
    # Prevent Git from finding the enclosing AgenticAEGIS repository and
    # silently skipping paths outside the current prefix.
    subprocess.run(["git", "init", "--quiet", str(source)], check=True)
    subprocess.run(["git", "apply", "--check", str(patch)], cwd=source, check=True)
    subprocess.run(["git", "apply", str(patch)], cwd=source, check=True)
    for name, expected in lock["result_sha256"].items():
        if hashlib.sha256((source / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"Restored source differs from the archived fork: {name}")
    print(f"Legacy patch verified and applied: {source}")


if __name__ == "__main__":
    main()
