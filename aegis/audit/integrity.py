"""Hash-chain integrity verification for audit trails.

Reads a JSONL audit file line-by-line, recomputes each entry's hash,
and verifies the chain from GENESIS to the last entry.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_GENESIS_HASH = hashlib.sha256(b"GENESIS").hexdigest()


@dataclass(frozen=True, slots=True)
class IntegrityError:
    """A single integrity violation found during verification."""

    entry_id: int
    error_type: str
    message: str


@dataclass(slots=True)
class IntegrityResult:
    """Result of hash-chain verification."""

    valid: bool
    total_entries: int
    first_entry_id: int | None = None
    last_entry_id: int | None = None
    errors: list[IntegrityError] = field(default_factory=list)
    verification_time_ms: float = 0.0


def verify_integrity(path: Path) -> IntegrityResult:
    """Verify the hash-chain integrity of an audit trail JSONL file.

    Checks:
    - Each entry's entry_hash matches its recomputed hash
    - Each entry's prev_hash matches the previous entry's entry_hash
    - First entry's prev_hash is the GENESIS hash
    - Entry IDs are sequential (no gaps)
    - All lines are valid JSON

    Returns:
        IntegrityResult with details of any errors found.
    """
    start = time.monotonic()
    result = IntegrityResult(valid=True, total_entries=0)

    if not path.exists():
        result.valid = False
        result.errors.append(
            IntegrityError(
                entry_id=-1,
                error_type="FILE_NOT_FOUND",
                message=f"Audit file not found: {path}",
            )
        )
        result.verification_time_ms = (time.monotonic() - start) * 1000
        return result

    prev_hash = _GENESIS_HASH
    expected_id = 0

    with path.open("r") as f:
        for line_num, line in enumerate(f):
            line = line.strip()
            if not line:
                continue

            # Parse JSON
            try:
                data = json.loads(line)
            except json.JSONDecodeError as e:
                result.valid = False
                result.errors.append(
                    IntegrityError(
                        entry_id=expected_id,
                        error_type="CORRUPT_JSON",
                        message=f"Line {line_num + 1}: {e}",
                    )
                )
                # Cannot continue chain verification after corrupt entry
                break

            entry_id = data.get("entry_id", -1)
            result.total_entries += 1

            if result.first_entry_id is None:
                result.first_entry_id = entry_id
            result.last_entry_id = entry_id

            # Check sequence
            if entry_id != expected_id:
                result.valid = False
                result.errors.append(
                    IntegrityError(
                        entry_id=entry_id,
                        error_type="SEQUENCE_GAP",
                        message=(
                            f"Expected entry_id {expected_id}, got {entry_id}"
                        ),
                    )
                )

            # Check prev_hash
            if data.get("prev_hash") != prev_hash:
                result.valid = False
                error_type = (
                    "GENESIS_MISMATCH" if expected_id == 0 else "HASH_MISMATCH"
                )
                result.errors.append(
                    IntegrityError(
                        entry_id=entry_id,
                        error_type=error_type,
                        message=(
                            f"Entry {entry_id}: prev_hash mismatch "
                            f"(expected {prev_hash[:16]}..., "
                            f"got {data.get('prev_hash', '?')[:16]}...)"
                        ),
                    )
                )

            # Recompute and check entry_hash
            stored_hash = data.get("entry_hash", "")
            hashable = {k: v for k, v in data.items() if k != "entry_hash"}
            recomputed = _compute_hash(hashable)

            if recomputed != stored_hash:
                result.valid = False
                result.errors.append(
                    IntegrityError(
                        entry_id=entry_id,
                        error_type="HASH_MISMATCH",
                        message=(
                            f"Entry {entry_id}: entry_hash mismatch "
                            f"(computed {recomputed[:16]}..., "
                            f"stored {stored_hash[:16]}...)"
                        ),
                    )
                )

            prev_hash = stored_hash
            expected_id = entry_id + 1

    result.verification_time_ms = (time.monotonic() - start) * 1000
    return result


def _compute_hash(entry_dict: dict[str, Any]) -> str:
    """SHA-256 of canonical JSON (sorted keys, compact separators)."""
    canonical = json.dumps(entry_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
