"""AEGIS-1702: Guarded Retrieval Broker.

Interposes Guard checks on every information retrieval operation before
content reaches the LLM.  The broker translates file reads and searches
into ``readDocument`` / ``searchCorpus`` actions, evaluates them against
the loaded MELD norms, and returns provenance-carrying results.

This is the critical fix for the canary-leak gap: the LLM never sees
raw classified content unless the Guard explicitly permits it.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from aegis.guard.action import Action
from aegis.guard.verdict import Decision
from aegis.ifc.provenance import ProvenancedResult, ProvenanceRecord

if TYPE_CHECKING:
    from aegis.guard.guard import Guard
    from aegis.hardening.taint import TaintTracker
    from aegis.redteam.tools import WorkspaceFileRuntime

logger = logging.getLogger(__name__)

# Classification strings that map to TaintLevel for taint ingestion
_TAINT_LEVEL_MAP: dict[str, str] = {
    "public": "PUBLIC",
    "internal": "INTERNAL",
    "confidential": "CONFIDENTIAL",
    "secret": "SECRET",
    "topsecret": "SECRET",
    "top_secret": "SECRET",
    "top-secret": "SECRET",
}


class RetrievalBroker:
    """Policy-checked retrieval layer for workspace files.

    For every file access, the broker:
    1. Builds an ``Action(action_type="readDocument", ...)``
    2. Calls ``guard.check(action)`` → verdict
    3. FORBIDDEN  → ``ProvenancedResult(content="", response_mode="deny")``
    4. UNDECIDABLE → ``ProvenancedResult(content="", response_mode="metadata-only")``
    5. PERMITTED → full content with provenance attached
    6. Feeds canary tokens and protected strings to the taint tracker

    Usage::

        broker = RetrievalBroker(guard, taint_tracker=tracker)
        result = broker.broker_read(
            "intel/mixed_briefing.txt", file_entry,
            agent_id="agent-007", purpose="internalAnalysis",
        )
        if result.response_mode == "deny":
            # content is empty, file was classified
            ...
    """

    def __init__(
        self,
        guard: Guard,
        taint_tracker: TaintTracker | None = None,
    ) -> None:
        self._guard = guard
        self._taint_tracker = taint_tracker

    def broker_read(
        self,
        path: str,
        file_entry: WorkspaceFileRuntime,
        agent_id: str,
        purpose: str = "internalAnalysis",
    ) -> ProvenancedResult:
        """Broker a single file read through the Guard.

        Returns a :class:`ProvenancedResult` with the appropriate
        response mode based on the Guard verdict.
        """
        classification = file_entry.classification.lower()

        action = Action(
            action_type="readDocument",
            agent_id=agent_id,
            proposition={
                "sourceClassification": classification,
                "purpose": purpose,
            },
        )
        verdict = self._guard.check(action)

        provenance = ProvenanceRecord(
            source_path=path,
            classification=classification,
            canary_tokens=file_entry.canary_tokens,
        )

        if verdict.decision == Decision.FORBIDDEN:
            logger.info(
                "Broker DENIED read of %r (classification=%s, reason=%s)",
                path, classification, verdict.reason_type.value,
            )
            result = ProvenancedResult(
                content="",
                provenance=(provenance,),
                redacted=True,
                response_mode="deny",
            )
            self._ingest_taint(result)
            return result

        if verdict.decision == Decision.UNDECIDABLE:
            logger.info(
                "Broker UNDECIDABLE for %r — returning metadata-only",
                path,
            )
            result = ProvenancedResult(
                content="",
                provenance=(provenance,),
                redacted=True,
                response_mode="metadata-only",
            )
            self._ingest_taint(result)
            return result

        # PERMITTED — read the file and return full content
        content = file_entry.absolute_path.read_text(encoding="utf-8")
        result = ProvenancedResult(
            content=content,
            provenance=(provenance,),
            redacted=False,
            response_mode="full-content",
        )
        self._ingest_taint(result)
        return result

    def broker_search(
        self,
        query: str,
        files: dict[str, WorkspaceFileRuntime],
        agent_id: str,
        purpose: str = "internalAnalysis",
    ) -> ProvenancedResult:
        """Broker a search across workspace files.

        Each file is individually checked via ``readDocument``.
        Files that are FORBIDDEN are excluded from search results.
        Files that are UNDECIDABLE return metadata only.
        """
        if not query:
            return ProvenancedResult(content="", provenance=())

        query_lower = query.lower()
        all_matches: list[dict[str, Any]] = []
        all_provenance: list[ProvenanceRecord] = []
        any_redacted = False

        for entry in sorted(files.values(), key=lambda f: f.relative_path):
            classification = entry.classification.lower()

            action = Action(
                action_type="readDocument",
                agent_id=agent_id,
                proposition={
                    "sourceClassification": classification,
                    "purpose": purpose,
                },
            )
            verdict = self._guard.check(action)

            provenance = ProvenanceRecord(
                source_path=entry.relative_path,
                classification=classification,
                canary_tokens=entry.canary_tokens,
            )
            all_provenance.append(provenance)

            if verdict.decision == Decision.FORBIDDEN:
                any_redacted = True
                logger.info(
                    "Broker excluded %r from search (FORBIDDEN)",
                    entry.relative_path,
                )
                continue

            if verdict.decision == Decision.UNDECIDABLE:
                any_redacted = True
                continue

            # PERMITTED — search the file
            content = entry.absolute_path.read_text(encoding="utf-8")
            for lineno, line in enumerate(content.splitlines(), start=1):
                if query_lower in line.lower():
                    all_matches.append({
                        "path": entry.relative_path,
                        "classification": classification,
                        "line": lineno,
                        "content": line,
                    })

        import json
        result = ProvenancedResult(
            content=json.dumps({"matches": all_matches}),
            provenance=tuple(all_provenance),
            redacted=any_redacted,
            response_mode="redacted-snippet" if any_redacted else "full-content",
        )
        self._ingest_taint(result)
        return result

    def _ingest_taint(self, result: ProvenancedResult) -> None:
        """Feed provenance records into the taint tracker."""
        if self._taint_tracker is None:
            return
        self._taint_tracker.ingest_provenance(result)
