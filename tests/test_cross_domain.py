"""AEGIS-904: Cross-Domain Conflict Tests.

Tests that load multiple domains simultaneously and verify
prevalence resolution when norms from different codes conflict.
"""

from __future__ import annotations

from pathlib import Path

from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.verdict import Decision

DOMAINS_DIR = Path(__file__).parent.parent / "aegis" / "domains"


def _load_multi_domain(*domain_names: str, prevalence: list[str] | None = None) -> Guard:
    """Load multiple domains into a single Guard."""
    meld_files: list[Path] = []
    for name in domain_names:
        domain_dir = DOMAINS_DIR / name
        meld_files.extend(sorted(domain_dir.glob("*.meld")))
    return Guard.from_meld_files(meld_files, code_prevalence=prevalence)


class TestPharmaPlusLegal:
    """Pharma + Legal: Medical data sharing constraints."""

    def test_medical_data_external_forbidden_by_both(self) -> None:
        """Both domains forbid sending medical data externally."""
        guard = _load_multi_domain(
            "pharma", "legal",
            prevalence=["DataProtection", "PharmaCompliance"],
        )
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

    def test_pharma_adverse_event_permitted_despite_legal(self) -> None:
        """Reporting adverse events is permitted even with legal domain loaded."""
        guard = _load_multi_domain(
            "pharma", "legal",
            prevalence=["PharmaCompliance", "DataProtection"],
        )
        verdict = guard.check(
            Action(
                action_type="reportAdverseEvent",
                agent_id="prescribingAgent",
                proposition={"severity": "majorInteraction"},
            )
        )
        assert verdict.decision == Decision.PERMITTED


class TestSanctionsPlusLegal:
    """Sanctions + Legal: Trade compliance + data protection."""

    def test_clear_transaction_permitted(self) -> None:
        """Non-sanctioned transaction stays permitted with legal domain."""
        guard = _load_multi_domain(
            "sanctions", "legal",
            prevalence=["SanctionsCompliance", "DataProtection"],
        )
        verdict = guard.check(
            Action(
                action_type="approveTransaction",
                agent_id="tradeComplianceAgent",
                proposition={
                    "sanctionStatus": "clear",
                    "destination": "allied",
                },
            )
        )
        assert verdict.decision == Decision.PERMITTED

    def test_public_data_permitted_with_sanctions(self) -> None:
        """Public data sharing stays permitted even with sanctions loaded."""
        guard = _load_multi_domain(
            "sanctions", "legal",
            prevalence=["DataProtection", "SanctionsCompliance"],
        )
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


class TestAllThreeDomains:
    """All three domains loaded simultaneously."""

    def test_three_domains_load(self) -> None:
        """Loading all three domains doesn't crash or conflict."""
        guard = _load_multi_domain(
            "pharma", "sanctions", "legal",
            prevalence=[
                "DataProtection",
                "SanctionsCompliance",
                "PharmaCompliance",
                "SanctionsHumanitarianCode",
                "PharmaEmergencyCode",
            ],
        )
        assert guard._kb.fact_count > 0
        assert len(guard._norms) > 0

    def test_each_domain_actions_still_work(self) -> None:
        """Actions from each domain produce correct verdicts."""
        guard = _load_multi_domain(
            "pharma", "sanctions", "legal",
            prevalence=[
                "DataProtection",
                "SanctionsCompliance",
                "PharmaCompliance",
            ],
        )
        # Pharma: adverse event reporting → PERMITTED
        v1 = guard.check(
            Action(
                action_type="reportAdverseEvent",
                agent_id="prescribingAgent",
                proposition={"severity": "majorInteraction"},
            )
        )
        assert v1.decision == Decision.PERMITTED

        # Sanctions: SDN transaction → FORBIDDEN
        v2 = guard.check(
            Action(
                action_type="approveTransaction",
                agent_id="tradeComplianceAgent",
                proposition={
                    "sanctionStatus": "SDN_listed",
                    "destination": "unrestricted",
                },
            )
        )
        assert v2.decision == Decision.FORBIDDEN

        # Legal: approve NDA → PERMITTED
        v3 = guard.check(
            Action(
                action_type="approveContract",
                agent_id="legalReviewAgent",
                proposition={"contractType": "NDA"},
            )
        )
        assert v3.decision == Decision.PERMITTED

    def test_moral_axioms_survive_multi_domain(self) -> None:
        """Moral axioms from each domain remain FORBIDDEN regardless of other domains."""
        guard = _load_multi_domain(
            "pharma", "sanctions", "legal",
            prevalence=[
                "SanctionsHumanitarianCode",
                "PharmaEmergencyCode",
                "DataProtection",
                "SanctionsCompliance",
                "PharmaCompliance",
            ],
        )
        # Military to sanctioned: moral axiom
        v1 = guard.check(
            Action(
                action_type="releaseShipment",
                agent_id="tradeComplianceAgent",
                proposition={"goodsType": "military", "destination": "sanctioned"},
            )
        )
        assert v1.decision == Decision.FORBIDDEN

        # Withdrawn medication: moral axiom
        v2 = guard.check(
            Action(
                action_type="approveDistribution",
                agent_id="prescribingAgent",
                proposition={"approvalStatus": "withdrawn", "trialPhase": "postMarket"},
            )
        )
        assert v2.decision == Decision.FORBIDDEN

        # Attorney-client to third party: moral axiom
        v3 = guard.check(
            Action(
                action_type="shareDocument",
                agent_id="legalReviewAgent",
                proposition={
                    "privilegeStatus": "attorney_client",
                    "recipient": "thirdParty",
                },
            )
        )
        assert v3.decision == Decision.FORBIDDEN
