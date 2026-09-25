"""AEGIS-901/902/903: Domain loading and verdict tests.

Tests the three additional domains: Pharma, Sanctions, Legal.
Each domain is loaded from .meld files and verified against expected verdicts.
"""

from __future__ import annotations

from pathlib import Path

from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.verdict import Decision

DOMAINS_DIR = Path(__file__).parent.parent / "aegis" / "domains"


# ── Pharma Domain ────────────────────────────────────────────────


def _load_pharma() -> Guard:
    pharma_dir = DOMAINS_DIR / "pharma"
    return Guard.from_meld_files(
        sorted(pharma_dir.glob("*.meld")),
        code_prevalence=["PharmaEmergencyCode", "PharmaCompliance"],
    )


class TestPharmaDomain:
    def test_loads_successfully(self) -> None:
        guard = _load_pharma()
        assert guard._kb.fact_count > 0
        assert len(guard._norms) > 0

    def test_report_adverse_event_permitted(self) -> None:
        guard = _load_pharma()
        verdict = guard.check(
            Action(
                action_type="reportAdverseEvent",
                agent_id="prescribingAgent",
                proposition={"severity": "majorInteraction"},
            )
        )
        assert verdict.decision == Decision.PERMITTED

    def test_prescribe_with_major_interaction_forbidden(self) -> None:
        guard = _load_pharma()
        verdict = guard.check(
            Action(
                action_type="prescribeMedication",
                agent_id="prescribingAgent",
                proposition={
                    "medicationClass": "controlledSubstance",
                    "interactionSeverity": "majorInteraction",
                },
            )
        )
        assert verdict.decision == Decision.FORBIDDEN

    def test_distribute_experimental_forbidden(self) -> None:
        guard = _load_pharma()
        verdict = guard.check(
            Action(
                action_type="approveDistribution",
                agent_id="prescribingAgent",
                proposition={
                    "approvalStatus": "experimental",
                    "trialPhase": "phase1",
                },
            )
        )
        assert verdict.decision == Decision.FORBIDDEN

    def test_distribute_approved_permitted(self) -> None:
        guard = _load_pharma()
        verdict = guard.check(
            Action(
                action_type="approveDistribution",
                agent_id="prescribingAgent",
                proposition={
                    "approvalStatus": "approved",
                    "trialPhase": "postMarket",
                },
            )
        )
        assert verdict.decision == Decision.PERMITTED

    def test_assistant_cannot_recommend_controlled(self) -> None:
        guard = _load_pharma()
        verdict = guard.check(
            Action(
                action_type="recommendDosage",
                agent_id="assistantAgent",
                proposition={"medicationClass": "controlledSubstance"},
            )
        )
        assert verdict.decision == Decision.FORBIDDEN

    def test_withdrawn_medication_moral_axiom(self) -> None:
        """Withdrawn meds are FORBIDDEN even with emergency code."""
        guard = _load_pharma()
        verdict = guard.check(
            Action(
                action_type="approveDistribution",
                agent_id="prescribingAgent",
                proposition={
                    "approvalStatus": "withdrawn",
                    "trialPhase": "postMarket",
                },
            )
        )
        assert verdict.decision == Decision.FORBIDDEN


# ── Sanctions Domain ─────────────────────────────────────────────


def _load_sanctions() -> Guard:
    sanctions_dir = DOMAINS_DIR / "sanctions"
    return Guard.from_meld_files(
        sorted(sanctions_dir.glob("*.meld")),
        code_prevalence=["SanctionsHumanitarianCode", "SanctionsCompliance"],
    )


class TestSanctionsDomain:
    def test_loads_successfully(self) -> None:
        guard = _load_sanctions()
        assert guard._kb.fact_count > 0
        assert len(guard._norms) > 0

    def test_clear_transaction_permitted(self) -> None:
        guard = _load_sanctions()
        verdict = guard.check(
            Action(
                action_type="approveTransaction",
                agent_id="tradeComplianceAgent",
                proposition={
                    "sanctionStatus": "clear",
                    "destination": "unrestricted",
                },
            )
        )
        assert verdict.decision == Decision.PERMITTED

    def test_sdn_transaction_forbidden(self) -> None:
        guard = _load_sanctions()
        verdict = guard.check(
            Action(
                action_type="approveTransaction",
                agent_id="tradeComplianceAgent",
                proposition={
                    "sanctionStatus": "SDN_listed",
                    "destination": "unrestricted",
                },
            )
        )
        assert verdict.decision == Decision.FORBIDDEN

    def test_dual_use_to_restricted_forbidden(self) -> None:
        guard = _load_sanctions()
        verdict = guard.check(
            Action(
                action_type="releaseShipment",
                agent_id="tradeComplianceAgent",
                proposition={
                    "goodsType": "dualUse",
                    "destination": "restricted",
                },
            )
        )
        assert verdict.decision == Decision.FORBIDDEN

    def test_civilian_to_allied_permitted(self) -> None:
        guard = _load_sanctions()
        verdict = guard.check(
            Action(
                action_type="releaseShipment",
                agent_id="tradeComplianceAgent",
                proposition={
                    "goodsType": "civilian",
                    "destination": "allied",
                },
            )
        )
        assert verdict.decision == Decision.PERMITTED

    def test_humanitarian_aid_to_sanctioned_permitted(self) -> None:
        """Humanitarian exception overrides sanctions."""
        guard = _load_sanctions()
        verdict = guard.check(
            Action(
                action_type="supplyHumanitarianAid",
                agent_id="tradeComplianceAgent",
                proposition={"destination": "sanctioned"},
            )
        )
        assert verdict.decision == Decision.PERMITTED

    def test_flag_entity_permitted(self) -> None:
        guard = _load_sanctions()
        verdict = guard.check(
            Action(
                action_type="flagEntity",
                agent_id="tradeComplianceAgent",
                proposition={"sanctionStatus": "SDN_listed"},
            )
        )
        assert verdict.decision == Decision.PERMITTED

    def test_military_to_sanctioned_moral_axiom(self) -> None:
        """Military goods to sanctioned territory: absolute prohibition."""
        guard = _load_sanctions()
        verdict = guard.check(
            Action(
                action_type="releaseShipment",
                agent_id="tradeComplianceAgent",
                proposition={
                    "goodsType": "military",
                    "destination": "sanctioned",
                },
            )
        )
        assert verdict.decision == Decision.FORBIDDEN


# ── Legal Domain ─────────────────────────────────────────────────


def _load_legal() -> Guard:
    legal_dir = DOMAINS_DIR / "legal"
    return Guard.from_meld_files(
        sorted(legal_dir.glob("*.meld")),
        code_prevalence=["DataProtection"],
    )


class TestLegalDomain:
    def test_loads_successfully(self) -> None:
        guard = _load_legal()
        assert guard._kb.fact_count > 0
        assert len(guard._norms) > 0

    def test_personal_data_to_external_forbidden(self) -> None:
        guard = _load_legal()
        verdict = guard.check(
            Action(
                action_type="sendPersonalData",
                agent_id="dataProcessorAgent",
                proposition={
                    "dataCategory": "personalData",
                    "recipient": "externalService",
                },
            )
        )
        assert verdict.decision == Decision.FORBIDDEN

    def test_medical_data_to_third_party_forbidden(self) -> None:
        guard = _load_legal()
        verdict = guard.check(
            Action(
                action_type="sendPersonalData",
                agent_id="dataProcessorAgent",
                proposition={
                    "dataCategory": "medicalData",
                    "recipient": "thirdParty",
                },
            )
        )
        assert verdict.decision == Decision.FORBIDDEN

    def test_public_data_sharing_permitted(self) -> None:
        guard = _load_legal()
        verdict = guard.check(
            Action(
                action_type="sendPersonalData",
                agent_id="dataProcessorAgent",
                proposition={
                    "dataCategory": "publicData",
                    "recipient": "externalService",
                },
            )
        )
        assert verdict.decision == Decision.PERMITTED

    def test_approve_nda_permitted(self) -> None:
        guard = _load_legal()
        verdict = guard.check(
            Action(
                action_type="approveContract",
                agent_id="legalReviewAgent",
                proposition={"contractType": "NDA"},
            )
        )
        assert verdict.decision == Decision.PERMITTED

    def test_privileged_doc_to_external_forbidden(self) -> None:
        guard = _load_legal()
        verdict = guard.check(
            Action(
                action_type="shareDocument",
                agent_id="legalReviewAgent",
                proposition={
                    "privilegeStatus": "attorney_client",
                    "recipient": "externalService",
                },
            )
        )
        assert verdict.decision == Decision.FORBIDDEN

    def test_public_record_internal_permitted(self) -> None:
        guard = _load_legal()
        verdict = guard.check(
            Action(
                action_type="shareDocument",
                agent_id="legalReviewAgent",
                proposition={
                    "privilegeStatus": "public_record",
                    "recipient": "internalDepartment",
                },
            )
        )
        assert verdict.decision == Decision.PERMITTED

    def test_medical_data_external_moral_axiom(self) -> None:
        """Medical data to external: absolute prohibition."""
        guard = _load_legal()
        verdict = guard.check(
            Action(
                action_type="sendPersonalData",
                agent_id="dataProcessorAgent",
                proposition={
                    "dataCategory": "medicalData",
                    "recipient": "externalService",
                },
            )
        )
        assert verdict.decision == Decision.FORBIDDEN
