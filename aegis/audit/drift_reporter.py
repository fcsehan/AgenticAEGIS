"""Intent-Action drift reporter (AEGIS-3005, Epic 30).

Heuristic post-hoc analysis: scan a JSONL audit trail and surface
records where the declared ``user_intent`` does not appear to match
the chosen ``action_type``. Pure regex/wordmatch — no LLM calls. The
report is intentionally noisy on the side of *too many* candidate
mismatches; the reviewer downgrades false positives.

The drift detection works in three steps per audit record:

1. Skip records that have no ``user_intent`` (no signal).
2. Build a token bag from the action's ``action_type`` and (when
   available) the action's declared synonyms from the registry.
3. If none of those tokens appear in the user_intent string (after
   simple normalisation), flag as suspected drift.

Output is pure data — JSON or a tab-separated table — so downstream
tools (CI gates, dashboards) can consume it.

The reporter is *not* a security control; it is a sampling/visibility
tool to spot patterns where the LLM systematically picks the wrong
action for a given intent. See AEGIS-3005 in Epic 30 and the
guarantee boundary § 5.3 for the conditional-mitigation context.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DriftFinding:
    """A single suspected intent-action drift."""

    entry_id: int
    timestamp: str
    action_type: str
    user_intent: str
    decision: str
    severity: str  # "high" | "medium" | "low"


def _tokenise(text: str) -> set[str]:
    """Lowercase, split on non-alphanumeric, drop empties."""
    return {tok for tok in re.split(r"[^a-z0-9]+", text.lower()) if tok}


def _camelcase_tokens(name: str) -> set[str]:
    """Split CamelCase / camelCase / snake_case / kebab-case identifiers
    into their constituent lowercase tokens.

    ``readDiagnosis`` → ``{"read", "diagnosis"}``
    ``read_patient_file`` → ``{"read", "patient", "file"}``
    ``shareIntelligence`` → ``{"share", "intelligence"}``
    """
    parts = re.findall(r"[A-Z][a-z0-9]*|[a-z0-9]+", name)
    return {p.lower() for p in parts if p}


def _signal_tokens(action_type: str, synonyms: Iterable[str] = ()) -> set[str]:
    """Build the token bag for drift comparison from an action type and
    its (optional) declared synonyms."""
    tokens = _camelcase_tokens(action_type)
    for syn in synonyms:
        tokens |= _tokenise(syn)
    return tokens


def _drift_severity(action_tokens: set[str], intent_tokens: set[str]) -> str | None:
    """Compute drift severity, or None if no drift detected.

    - high: zero overlap between tokens
    - medium: very small overlap (≤ 1 shared token, action has ≥ 2)
    - None: enough overlap that drift is unlikely
    """
    if not action_tokens or not intent_tokens:
        return None
    overlap = action_tokens & intent_tokens
    if not overlap:
        return "high"
    if len(overlap) == 1 and len(action_tokens) >= 2:
        return "medium"
    return None


def scan_audit_log(
    path: Path,
    *,
    synonyms_by_action: dict[str, list[str]] | None = None,
) -> list[DriftFinding]:
    """Scan a JSONL audit log and return suspected drift findings.

    Args:
        path: Path to the JSONL audit trail.
        synonyms_by_action: Optional mapping of ``action_type`` →
            list of synonym phrases. When provided (typically from
            ``ActionTypeRegistry.get_synonyms``), synonyms are added
            to the action's signal-token bag and reduce false
            positives substantially.

    Returns:
        A list of ``DriftFinding`` records, sorted by entry_id.
    """
    synonyms_map = synonyms_by_action or {}
    findings: list[DriftFinding] = []

    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            continue

        if record.get("event") != "ACTION_VERDICT":
            continue
        action = record.get("action") or {}
        intent = action.get("user_intent")
        if not intent:
            continue
        action_type = action.get("action_type") or ""
        if not action_type:
            continue

        synonyms = synonyms_map.get(action_type, [])
        action_tokens = _signal_tokens(action_type, synonyms)
        intent_tokens = _tokenise(intent)
        severity = _drift_severity(action_tokens, intent_tokens)
        if severity is None:
            continue

        verdict = record.get("verdict") or {}
        findings.append(
            DriftFinding(
                entry_id=record.get("entry_id", -1),
                timestamp=record.get("timestamp", ""),
                action_type=action_type,
                user_intent=intent,
                decision=verdict.get("decision", "?"),
                severity=severity,
            )
        )

    findings.sort(key=lambda f: f.entry_id)
    return findings


def render_text_report(findings: list[DriftFinding]) -> str:
    """Render findings as a human-readable tab-separated table."""
    if not findings:
        return "No drift findings."
    lines = ["entry_id\tseverity\taction_type\tdecision\tuser_intent"]
    for f in findings:
        intent_short = f.user_intent if len(f.user_intent) <= 60 else f.user_intent[:57] + "..."
        lines.append(
            f"{f.entry_id}\t{f.severity}\t{f.action_type}\t{f.decision}\t{intent_short}"
        )
    return "\n".join(lines)


def render_json_report(findings: list[DriftFinding]) -> str:
    """Render findings as a JSON array."""
    payload = [
        {
            "entry_id": f.entry_id,
            "timestamp": f.timestamp,
            "action_type": f.action_type,
            "user_intent": f.user_intent,
            "decision": f.decision,
            "severity": f.severity,
        }
        for f in findings
    ]
    return json.dumps(payload, indent=2)
