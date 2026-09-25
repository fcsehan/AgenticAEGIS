"""End-to-end test: IAMission domain — .meld files → Guard.check() → Verdict.

Loads the full aegis/domains/iamission domain (6 .meld files, 369 facts, 20 norms)
and verifies the four prototype demo scenarios translated to the MELD format.

Scenarios from the prototype (Implementation Architecture Concept/demo.py):
  1. Legitimate actions → PERMITTED
  2. Sub-agent breaks ethical boundaries → FORBIDDEN
  3. Helpful Deceiver → FORBIDDEN (formal check, not NL description)
  4. Cross-role / delete constraints → FORBIDDEN
"""

from __future__ import annotations

from pathlib import Path

from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.verdict import Decision, ReasonType

MELD_DIR = Path(__file__).parent.parent / "aegis" / "domains" / "iamission"


def _load_guard() -> Guard:
    """Load all 6 IAMission .meld files into a Guard."""
    meld_files = sorted(MELD_DIR.glob("*.meld"))
    assert len(meld_files) == 6, f"Expected 6 .meld files, found {len(meld_files)}"
    return Guard.from_meld_files(meld_files, code_prevalence=["IAMissionCode"])


class TestIAMissionDomainLoading:
    """Verify the domain loads completely and correctly."""

    def test_all_meld_files_load(self) -> None:
        guard = _load_guard()
        assert guard._kb.fact_count >= 360
        assert len(guard._kb.microtheories) == 6

    def test_norms_extracted(self) -> None:
        guard = _load_guard()
        assert len(guard._norms) == 20

    def test_action_types_registered(self) -> None:
        guard = _load_guard()
        assert guard._registry.is_known("shareIntelligence")
        assert guard._registry.is_known("sendDataExternal")
        assert guard._registry.is_known("deleteRecord")


class TestScenario1LegitimateActions:
    """Scenario 1: Legitimate actions → PERMITTED."""

    def test_intelligence_agent_shares_unclassified_with_commander(self) -> None:
        guard = _load_guard()
        verdict = guard.check(
            Action(
                action_type="shareIntelligence",
                agent_id="intelligenceAgentInMission",
                proposition={"classification": "unclassified", "recipient": "commanderInMission"},
                context={},
            )
        )
        assert verdict.decision == Decision.PERMITTED

    def test_intelligence_agent_shares_classified_with_commander(self) -> None:
        guard = _load_guard()
        verdict = guard.check(
            Action(
                action_type="shareIntelligence",
                agent_id="intelligenceAgentInMission",
                proposition={"classification": "classified", "recipient": "commanderInMission"},
                context={},
            )
        )
        assert verdict.decision == Decision.PERMITTED

    def test_operations_agent_directs_operations(self) -> None:
        guard = _load_guard()
        verdict = guard.check(
            Action(
                action_type="directOperations",
                agent_id="operationsAgentInMission",
                proposition={"type": "standard"},
                context={},
            )
        )
        assert verdict.decision == Decision.PERMITTED

    def test_public_data_internal_sharing(self) -> None:
        guard = _load_guard()
        verdict = guard.check(
            Action(
                action_type="sendDataExternal",
                agent_id="intelligenceAgentInMission",
                proposition={"dataCategory": "public", "recipientType": "internalAgent"},
                context={},
            )
        )
        assert verdict.decision == Decision.PERMITTED

    def test_logistics_support(self) -> None:
        guard = _load_guard()
        verdict = guard.check(
            Action(
                action_type="provideLogisticsSupport",
                agent_id="logisticsAgentInMission",
                proposition={"type": "standard"},
                context={},
            )
        )
        assert verdict.decision == Decision.PERMITTED

    def test_c4_communicates_with_commander(self) -> None:
        guard = _load_guard()
        verdict = guard.check(
            Action(
                action_type="communicateWithCommander",
                agent_id="c4AgentInMission",
                proposition={"type": "standard"},
                context={},
            )
        )
        assert verdict.decision == Decision.PERMITTED


class TestScenario2SubAgentBreaksEthicalBoundaries:
    """Scenario 2: Sub-agent attempts to break ethical boundaries → FORBIDDEN.

    From the prototype blog: "Sub-Agents break ethical limits
    to achieve the goal of the parent agent."
    """

    def test_intelligence_agent_shares_secret_externally(self) -> None:
        """Intel agent tries to send secret data to external service."""
        guard = _load_guard()
        verdict = guard.check(
            Action(
                action_type="shareIntelligence",
                agent_id="intelligenceAgentInMission",
                proposition={"classification": "secret", "recipient": "externalService"},
                context={},
            )
        )
        assert verdict.decision == Decision.FORBIDDEN

    def test_intelligence_agent_shares_top_secret_with_allies(self) -> None:
        """Intel agent tries to share top-secret with allied nation."""
        guard = _load_guard()
        verdict = guard.check(
            Action(
                action_type="shareIntelligence",
                agent_id="intelligenceAgentInMission",
                proposition={"classification": "topSecret", "recipient": "alliedNation"},
                context={},
            )
        )
        assert verdict.decision == Decision.FORBIDDEN

    def test_operations_agent_shares_classified_externally(self) -> None:
        """Ops agent tries to share classified intel externally."""
        guard = _load_guard()
        verdict = guard.check(
            Action(
                action_type="shareIntelligence",
                agent_id="operationsAgentInMission",
                proposition={"classification": "classified", "recipient": "externalService"},
                context={},
            )
        )
        assert verdict.decision == Decision.FORBIDDEN


class TestScenario3HelpfulDeceiver:
    """Scenario 3: The "Helpful Deceiver" — harmless description, forbidden data.

    The prototype demo says: "The agent phrases it nicely — but the formal
    check looks at the structure, not the natural-language description."
    The NL description doesn't matter — the proposition fields do.
    """

    def test_personal_data_to_external_blocked(self) -> None:
        """Agent sends personal data externally (regardless of description)."""
        guard = _load_guard()
        verdict = guard.check(
            Action(
                action_type="sendDataExternal",
                agent_id="intelligenceAgentInMission",
                proposition={
                    "dataCategory": "personal",
                    "recipientType": "externalService",
                },
                context={},
            )
        )
        assert verdict.decision == Decision.FORBIDDEN

    def test_medical_data_to_external_blocked(self) -> None:
        """Agent sends medical data externally."""
        guard = _load_guard()
        verdict = guard.check(
            Action(
                action_type="sendDataExternal",
                agent_id="intelligenceAgentInMission",
                proposition={
                    "dataCategory": "medical",
                    "recipientType": "externalService",
                },
                context={},
            )
        )
        assert verdict.decision == Decision.FORBIDDEN

    def test_personal_data_blocked_for_all_roles(self) -> None:
        """Personal data prohibition applies to all mission roles."""
        guard = _load_guard()
        for role in [
            "personalStaffAgentInMission",
            "intelligenceAgentInMission",
            "operationsAgentInMission",
        ]:
            verdict = guard.check(
                Action(
                    action_type="sendDataExternal",
                    agent_id=role,
                    proposition={"dataCategory": "personal", "recipientType": "externalService"},
                    context={},
                )
            )
            assert verdict.decision == Decision.FORBIDDEN, (
                f"Expected FORBIDDEN for {role}, got {verdict.decision.value}"
            )


class TestScenario4DeleteAndCrossRoleConstraints:
    """Scenario 4: Delete actions and cross-role constraints."""

    def test_delete_forbidden_for_intelligence(self) -> None:
        guard = _load_guard()
        verdict = guard.check(
            Action(
                action_type="deleteRecord",
                agent_id="intelligenceAgentInMission",
                proposition={"recordType": "any"},
                context={},
            )
        )
        assert verdict.decision == Decision.FORBIDDEN

    def test_delete_forbidden_for_operations(self) -> None:
        guard = _load_guard()
        verdict = guard.check(
            Action(
                action_type="deleteRecord",
                agent_id="operationsAgentInMission",
                proposition={"recordType": "any"},
                context={},
            )
        )
        assert verdict.decision == Decision.FORBIDDEN

    def test_delete_forbidden_for_personal_staff(self) -> None:
        guard = _load_guard()
        verdict = guard.check(
            Action(
                action_type="deleteRecord",
                agent_id="personalStaffAgentInMission",
                proposition={"recordType": "any"},
                context={},
            )
        )
        assert verdict.decision == Decision.FORBIDDEN


class TestNoJurisdiction:
    """Actions outside any loaded domain → UNDECIDABLE."""

    def test_unknown_action_type(self) -> None:
        guard = _load_guard()
        verdict = guard.check(
            Action(
                action_type="launchMissile",
                agent_id="intelligenceAgentInMission",
            )
        )
        assert verdict.decision == Decision.UNDECIDABLE
        assert verdict.reason_type == ReasonType.NO_JURISDICTION


class TestDeterminismAndAudit:
    """Invariant I1 (determinism) and I3 (justification chain)."""

    def test_determinism_100x(self) -> None:
        """Same input → same output, 100 times."""
        guard = _load_guard()
        action = Action(
            action_type="shareIntelligence",
            agent_id="intelligenceAgentInMission",
            proposition={"classification": "secret", "recipient": "externalService"},
            context={},
        )
        verdicts = [guard.check(action) for _ in range(100)]
        assert all(v.decision == Decision.FORBIDDEN for v in verdicts)

    def test_every_verdict_has_justification(self) -> None:
        """Every verdict carries a justification chain for audit."""
        guard = _load_guard()
        actions = [
            Action(
                "shareIntelligence",
                "intelligenceAgentInMission",
                {"classification": "unclassified", "recipient": "commanderInMission"},
                {"dataClassification": "unclassified"},
            ),
            Action(
                "shareIntelligence",
                "intelligenceAgentInMission",
                {"classification": "secret", "recipient": "externalService"},
                {"dataClassification": "secret"},
            ),
            Action("launchMissile", "unknownAgent"),
        ]
        for action in actions:
            verdict = guard.check(action)
            assert verdict.justification_chain, f"Missing justification for {action.action_type}"
