"""Tests for AEGIS-1701: Information Operation Taxonomy MELD files.

Verifies that the IFC domain MELD files load correctly and produce
the expected action types, norms, and classifications.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aegis.guard.guard import Guard

IFC_DOMAIN_DIR = Path(__file__).resolve().parents[2] / "aegis" / "domains" / "ifc"


@pytest.fixture
def ifc_guard() -> Guard:
    """Load the IFC domain into a Guard instance."""
    meld_files = sorted(IFC_DOMAIN_DIR.glob("*.meld"))
    assert len(meld_files) == 3, f"Expected 3 MELD files, got {len(meld_files)}"
    return Guard.from_meld_files(
        meld_files,
        code_prevalence=["InformationFlowCode"],
    )


class TestMeldLoading:
    def test_meld_files_exist(self) -> None:
        assert (IFC_DOMAIN_DIR / "InformationFlowOntologyMt.meld").exists()
        assert (IFC_DOMAIN_DIR / "InformationFlowActionVocabMt.meld").exists()
        assert (IFC_DOMAIN_DIR / "InformationFlowDeonticRulesMt.meld").exists()

    def test_guard_loads_without_error(self, ifc_guard: Guard) -> None:
        assert ifc_guard is not None

    def test_action_types_registered(self, ifc_guard: Guard) -> None:
        expected_types = {
            "discoverSources",
            "searchCorpus",
            "readDocument",
            "extractFacts",
            "summarizeInformation",
            "compareInformation",
            "classifyInformation",
            "discloseInformation",
            "exportInformation",
        }
        registered = set(ifc_guard._registry.action_types)
        assert expected_types.issubset(registered), (
            f"Missing action types: {expected_types - registered}"
        )


class TestReadDocumentNorms:
    def test_read_public_for_internal_permitted(self, ifc_guard: Guard) -> None:
        from aegis.guard.action import Action
        from aegis.guard.verdict import Decision

        verdict = ifc_guard.check(Action(
            action_type="readDocument",
            agent_id="agentInMission",
            proposition={"sourceClassification": "public", "purpose": "internalAnalysis"},
        ))
        assert verdict.decision == Decision.PERMITTED

    def test_read_secret_for_external_forbidden(self, ifc_guard: Guard) -> None:
        from aegis.guard.action import Action
        from aegis.guard.verdict import Decision

        verdict = ifc_guard.check(Action(
            action_type="readDocument",
            agent_id="agentInMission",
            proposition={"sourceClassification": "secret", "purpose": "externalBriefing"},
        ))
        assert verdict.decision == Decision.FORBIDDEN


class TestDisclosureNorms:
    def test_disclose_secret_to_external_forbidden(self, ifc_guard: Guard) -> None:
        from aegis.guard.action import Action
        from aegis.guard.verdict import Decision

        verdict = ifc_guard.check(Action(
            action_type="discloseInformation",
            agent_id="agentInMission",
            proposition={
                "sourceClassification": "secret",
                "recipient": "externalService",
                "purpose": "externalBriefing",
            },
        ))
        assert verdict.decision == Decision.FORBIDDEN

    def test_disclose_public_to_internal_permitted(self, ifc_guard: Guard) -> None:
        from aegis.guard.action import Action
        from aegis.guard.verdict import Decision

        verdict = ifc_guard.check(Action(
            action_type="discloseInformation",
            agent_id="agentInMission",
            proposition={
                "sourceClassification": "public",
                "recipient": "internalAgent",
                "purpose": "internalAnalysis",
            },
        ))
        assert verdict.decision == Decision.PERMITTED


class TestSummarizationNorms:
    def test_summarize_secret_to_public_forbidden(self, ifc_guard: Guard) -> None:
        from aegis.guard.action import Action
        from aegis.guard.verdict import Decision

        verdict = ifc_guard.check(Action(
            action_type="summarizeInformation",
            agent_id="agentInMission",
            proposition={
                "sourceClassification": "secret",
                "targetClassification": "public",
                "recipient": "externalService",
            },
        ))
        assert verdict.decision == Decision.FORBIDDEN

    def test_summarize_public_to_public_permitted(self, ifc_guard: Guard) -> None:
        from aegis.guard.action import Action
        from aegis.guard.verdict import Decision

        verdict = ifc_guard.check(Action(
            action_type="summarizeInformation",
            agent_id="agentInMission",
            proposition={
                "sourceClassification": "public",
                "targetClassification": "public",
                "recipient": "internalAgent",
            },
        ))
        assert verdict.decision == Decision.PERMITTED


class TestClassificationDowngrade:
    def test_downgrade_secret_to_public_forbidden(self, ifc_guard: Guard) -> None:
        from aegis.guard.action import Action
        from aegis.guard.verdict import Decision

        verdict = ifc_guard.check(Action(
            action_type="classifyInformation",
            agent_id="agentInMission",
            proposition={
                "sourceClassification": "secret",
                "targetClassification": "public",
            },
        ))
        assert verdict.decision == Decision.FORBIDDEN
