"""AEGIS-1506 / AEGIS-1704: Sensitive Provenance (Taint Tracking).

Phase 1 (1506): exact substring matching.
Phase 2 (1704): session-level classification state, provenance ingestion,
and disclosure restriction tracking.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from aegis.hardening.output_guard import OutputFilter

if TYPE_CHECKING:
    from aegis.ifc.provenance import ProvenancedResult


class TaintLevel(Enum):
    """Classification level for tainted values."""

    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    SECRET = "SECRET"


# Ordering for highest-classification comparison
_TAINT_ORDERING: dict[TaintLevel, int] = {
    TaintLevel.PUBLIC: 0,
    TaintLevel.INTERNAL: 1,
    TaintLevel.CONFIDENTIAL: 2,
    TaintLevel.SECRET: 3,
}

# Map string classification labels to TaintLevel
_CLASSIFICATION_TO_LEVEL: dict[str, TaintLevel] = {
    "public": TaintLevel.PUBLIC,
    "internal": TaintLevel.INTERNAL,
    "confidential": TaintLevel.CONFIDENTIAL,
    "secret": TaintLevel.SECRET,
    "topsecret": TaintLevel.SECRET,
    "top_secret": TaintLevel.SECRET,
    "top-secret": TaintLevel.SECRET,
}


@dataclass(frozen=True, slots=True)
class TaintMarker:
    """A tracked sensitive value.

    Attributes:
        value: The exact string to watch for.
        source: Provenance description (e.g. tool name, file path).
        level: Classification level.
    """

    value: str
    source: str
    level: TaintLevel


class TaintTracker:
    """Tracks classified data fragments and session-level information flow state.

    Phase 1: exact substring matching for canary/marker detection.
    Phase 2 (AEGIS-1704): session-level taint memory — tracks which
    classifications have been touched, which sources accessed, and
    what disclosure restrictions apply.

    Usage::

        tracker = TaintTracker()
        tracker.mark(["CROWN-EMBER-7719"], source="mixed_briefing.txt", level=TaintLevel.SECRET)
        hits = tracker.check("The code is CROWN-EMBER-7719, do not share.")
        tracker.feed_to_output_guard(output_guard)

        # Phase 2: provenance ingestion
        tracker.ingest_provenance(provenanced_result)
        assert tracker.is_tainted()
        assert tracker.highest_classification == TaintLevel.SECRET
    """

    def __init__(self) -> None:
        self._markers: list[TaintMarker] = []
        # AEGIS-1704: Session-level state
        self._touched_classifications: set[str] = set()
        self._source_set: set[str] = set()
        self._disclosure_restrictions: list[
            tuple[str, tuple[str, ...], tuple[str, ...]]
        ] = []

    def mark(
        self,
        values: list[str],
        source: str,
        level: TaintLevel,
    ) -> None:
        """Register values as tainted with the given source and level."""
        for value in values:
            if not value:
                continue
            marker = TaintMarker(value=value, source=source, level=level)
            if marker not in self._markers:
                self._markers.append(marker)

    def check(self, text: str) -> list[TaintMarker]:
        """Return all markers whose values appear in *text* (exact substring)."""
        if not text:
            return []
        return [m for m in self._markers if m.value in text]

    def feed_to_output_guard(self, guard: OutputFilter) -> None:
        """Feed all tracked markers to an :class:`OutputFilter` as dynamic markers."""
        values = [m.value for m in self._markers if m.value]
        if values:
            guard.add_markers(values)

    @property
    def markers(self) -> list[TaintMarker]:
        """All registered taint markers."""
        return list(self._markers)

    # ── AEGIS-1704: Session-level taint state ─────────────────

    def ingest_provenance(self, result: ProvenancedResult) -> None:
        """Populate taint state from a :class:`ProvenancedResult`.

        Extracts canary tokens, classification levels, source paths,
        and recipient/purpose constraints from each provenance record.
        """
        for record in result.provenance:
            classification = record.classification.lower()
            self._touched_classifications.add(classification)
            self._source_set.add(record.source_path)

            # Register canary tokens as taint markers
            level = _CLASSIFICATION_TO_LEVEL.get(classification, TaintLevel.SECRET)
            if record.canary_tokens:
                self.mark(
                    list(record.canary_tokens),
                    source=record.source_path,
                    level=level,
                )

            # Track disclosure restrictions
            if record.allowed_recipients or record.allowed_purposes:
                self._disclosure_restrictions.append((
                    classification,
                    record.allowed_recipients,
                    record.allowed_purposes,
                ))

    @property
    def highest_classification(self) -> TaintLevel:
        """Return the highest classification level touched in this session."""
        if not self._touched_classifications:
            return TaintLevel.PUBLIC
        best = TaintLevel.PUBLIC
        for cls_str in self._touched_classifications:
            level = _CLASSIFICATION_TO_LEVEL.get(cls_str, TaintLevel.PUBLIC)
            if _TAINT_ORDERING[level] > _TAINT_ORDERING[best]:
                best = level
        return best

    def is_tainted(self) -> bool:
        """Return True if any non-PUBLIC classification has been touched."""
        return any(
            cls != "public" for cls in self._touched_classifications
        )

    def check_disclosure_allowed(self, recipient: str, purpose: str) -> bool:
        """Check whether disclosure is permitted given session restrictions.

        Returns True if no restrictions block the disclosure, or if
        the recipient and purpose match all active restrictions.
        Returns False if any restriction is violated.
        """
        if not self._disclosure_restrictions:
            return True

        for _classification, allowed_recipients, allowed_purposes in self._disclosure_restrictions:
            if allowed_recipients and recipient not in allowed_recipients:
                return False
            if allowed_purposes and purpose not in allowed_purposes:
                return False
        return True

    @property
    def touched_classifications(self) -> set[str]:
        """Classification levels touched in this session."""
        return set(self._touched_classifications)

    @property
    def source_set(self) -> set[str]:
        """File paths accessed in this session."""
        return set(self._source_set)

    def to_dict(self) -> dict[str, Any]:
        """Serializable state for audit/replay."""
        return {
            "markers": [
                {"value": m.value, "source": m.source, "level": m.level.value}
                for m in self._markers
            ],
            "touched_classifications": sorted(self._touched_classifications),
            "source_set": sorted(self._source_set),
            "highest_classification": self.highest_classification.value,
            "is_tainted": self.is_tainted(),
            "disclosure_restrictions": [
                {
                    "classification": cls,
                    "allowed_recipients": list(recipients),
                    "allowed_purposes": list(purposes),
                }
                for cls, recipients, purposes in self._disclosure_restrictions
            ],
        }
