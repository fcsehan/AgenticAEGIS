"""Download and verify the pinned OpenCode release without changing global tools."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def download(item: dict[str, Any], destination: Path) -> None:
    if (
        not destination.exists()
        or hashlib.sha256(destination.read_bytes()).hexdigest() != item["sha256"]
    ):
        temporary = destination.with_suffix(".download")
        with (
            urllib.request.urlopen(item["url"], timeout=60) as source,
            temporary.open("wb") as target,
        ):
            shutil.copyfileobj(source, target)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != item["sha256"]:
            temporary.unlink()
            raise RuntimeError("Downloaded artifact checksum does not match upstream.lock.json")
        temporary.replace(destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        action="store_true",
        help="Also extract the verified upstream source for inspection/building",
    )
    args = parser.parse_args()
    lock = json.loads((ROOT / "upstream.lock.json").read_text())
    machine = {"aarch64": "arm64", "x86_64": "x64"}.get(platform.machine(), platform.machine())
    target = f"{platform.system().lower()}-{machine}"
    if target not in lock["artifacts"]:
        raise SystemExit(f"No pinned artifact for {target}")
    cache = ROOT / ".cache"
    cache.mkdir(exist_ok=True)
    item = lock["artifacts"][target]
    archive = cache / item["url"].rsplit("/", 1)[1]
    download(item, archive)
    binary = cache / "opencode"
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as content:
            member = next(n for n in content.namelist() if Path(n).name == "opencode")
            executable = content.read(member)
    else:
        with tarfile.open(archive) as content:
            tar_member = next(m for m in content if m.isfile() and Path(m.name).name == "opencode")
            stream = content.extractfile(tar_member)
            assert stream is not None
            executable = stream.read()
    # Never overwrite a running executable in place (also invalidates macOS
    # code-signing caches). Rename a fresh inode atomically instead.
    with tempfile.NamedTemporaryFile(dir=cache, prefix="opencode-", delete=False) as target_file:
        target_file.write(executable)
        staged = Path(target_file.name)
    staged.chmod(0o755)
    staged.replace(binary)
    version = subprocess.check_output([str(binary), "--version"], text=True).strip()
    if version != lock["release"].removeprefix("v"):
        raise RuntimeError(f"Unexpected OpenCode version: {version}")
    (cache / "installed.json").write_text(
        json.dumps(
            {
                "release": lock["release"],
                "commit": lock["commit"],
                "platform": target,
                "artifact_sha256": item["sha256"],
                "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
            },
            indent=2,
        )
        + "\n"
    )
    runtime = cache / "runtime"
    runtime.mkdir(exist_ok=True)
    for name in ("package.json", "package-lock.json"):
        shutil.copyfile(ROOT / "runtime" / name, runtime / name)
    subprocess.run(
        ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"], cwd=runtime, check=True
    )
    if args.source:
        archive = cache / "upstream.tar.gz"
        download(lock["source"], archive)
        source = cache / "source"
        if source.exists():
            raise SystemExit(
                "Source directory already exists; retained without overwriting local changes"
            )
        source.mkdir()
        with tarfile.open(archive) as content:
            content.extractall(source, filter="data")
        print(f"Verified source: {source}")
    print(f"Verified OpenCode {version}: {binary}")


if __name__ == "__main__":
    main()
