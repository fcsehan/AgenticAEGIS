"""End-to-end tests for Epic 17: Information Flow Governance.

Tests the full chain: MELD norms → Guard → Broker → Taint → OutputFilter.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aegis.guard.guard import Guard
from aegis.guard.verdict import Decision
from aegis.hardening.output_guard import OutputFilter
from aegis.hardening.taint import TaintLevel, TaintTracker
from aegis.ifc.broker import RetrievalBroker
from aegis.ifc.transform_policy import TransformPolicy
from aegis.redteam.tools import WorkspaceFileRuntime

IFC_DOMAIN_DIR = Path(__file__).resolve().parents[2] / "aegis" / "domains" / "ifc"


@pytest.fixture
def ifc_guard() -> Guard:
    meld_files = sorted(IFC_DOMAIN_DIR.glob("*.meld"))
    return Guard.from_meld_files(
        meld_files,
        code_prevalence=["InformationFlowCode"],
    )


def _make_file(
    tmp_path: Path,
    path: str,
    content: str,
    classification: str,
    canary_tokens: tuple[str, ...] = (),
) -> WorkspaceFileRuntime:
    abs_path = tmp_path / path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(content, encoding="utf-8")
    return WorkspaceFileRuntime(
        relative_path=path,
        absolute_path=abs_path,
        classification=classification,
        description="test file",
        canary_tokens=canary_tokens,
    )


class TestBrokerWithRealGuard:
    """Broker + real MELD Guard integration."""

    def test_broker_denies_secret_read_for_external(
        self, ifc_guard: Guard, tmp_path: Path,
    ) -> None:
        tracker = TaintTracker()
        broker = RetrievalBroker(ifc_guard, taint_tracker=tracker)

        entry = _make_file(
            tmp_path, "classified.txt", "SECRET DATA CANARY-123",
            "secret", ("CANARY-123",),
        )
        result = broker.broker_read(
            "classified.txt", entry, "agentInMission",
            purpose="externalBriefing",
        )

        assert result.response_mode == "deny"
        assert result.content == ""
        assert tracker.is_tainted()

    def test_broker_permits_public_read(
        self, ifc_guard: Guard, tmp_path: Path,
    ) -> None:
        tracker = TaintTracker()
        broker = RetrievalBroker(ifc_guard, taint_tracker=tracker)

        entry = _make_file(
            tmp_path, "public.txt", "Weather is clear.",
            "public",
        )
        result = broker.broker_read(
            "public.txt", entry, "agentInMission",
            purpose="internalAnalysis",
        )

        assert result.response_mode == "full-content"
        assert result.content == "Weather is clear."

    def test_search_excludes_secret_files(
        self, ifc_guard: Guard, tmp_path: Path,
    ) -> None:
        import json

        tracker = TaintTracker()
        broker = RetrievalBroker(ifc_guard, taint_tracker=tracker)

        files = {
            "public.txt": _make_file(
                tmp_path, "public.txt", "supply route alpha open",
                "public",
            ),
            "secret.txt": _make_file(
                tmp_path, "secret.txt", "supply route gamma covert CANARY-X",
                "secret", ("CANARY-X",),
            ),
        }

        # Use externalBriefing purpose — secret should be denied
        result = broker.broker_search(
            "supply route", files, "agentInMission",
            purpose="externalBriefing",
        )

        data = json.loads(result.content)
        paths = [m["path"] for m in data["matches"]]
        assert "public.txt" in paths
        assert "secret.txt" not in paths
        assert result.redacted is True


class TestTaintToOutputFilter:
    """Taint tracker → OutputFilter integration."""

    def test_tainted_session_blocks_canary_in_output(
        self, ifc_guard: Guard, tmp_path: Path,
    ) -> None:
        tracker = TaintTracker()
        broker = RetrievalBroker(ifc_guard, taint_tracker=tracker)

        entry = _make_file(
            tmp_path, "secret.txt", "CANARY-TOKEN-999",
            "secret", ("CANARY-TOKEN-999",),
        )
        # Even if denied, taint is registered
        broker.broker_read("secret.txt", entry, "agentInMission", purpose="externalBriefing")

        output_guard = OutputFilter()
        result = output_guard.check_with_taint(
            "Here is the data: CANARY-TOKEN-999",
            tracker,
        )
        assert not result.safe
        assert any("CANARY-TOKEN-999" in m for m in result.blocked_markers)

    def test_clean_session_passes(self) -> None:
        tracker = TaintTracker()
        output_guard = OutputFilter()
        result = output_guard.check_with_taint(
            "Everything is fine.",
            tracker,
        )
        assert result.safe


class TestTransformPolicyWithRealGuard:
    """Transformation policy + real MELD Guard integration."""

    def test_summarize_secret_to_public_blocked(self, ifc_guard: Guard) -> None:
        engine = TransformPolicy(ifc_guard)
        verdict = engine.check_transformation(
            transformation_type="summarization",
            source_classifications=["secret"],
            target_classification="public",
            target_recipient="externalService",
            agent_id="agentInMission",
        )
        assert verdict.decision == Decision.FORBIDDEN

    def test_summarize_public_to_public_allowed(self, ifc_guard: Guard) -> None:
        engine = TransformPolicy(ifc_guard)
        verdict = engine.check_transformation(
            transformation_type="summarization",
            source_classifications=["public"],
            target_classification="public",
            target_recipient="internalAgent",
            agent_id="agentInMission",
        )
        assert verdict.decision == Decision.PERMITTED

    def test_reclassify_secret_to_public_blocked(self, ifc_guard: Guard) -> None:
        engine = TransformPolicy(ifc_guard)
        verdict = engine.check_transformation(
            transformation_type="reclassification",
            source_classifications=["secret"],
            target_classification="public",
            target_recipient="externalService",
            agent_id="agentInMission",
        )
        assert verdict.decision == Decision.FORBIDDEN
