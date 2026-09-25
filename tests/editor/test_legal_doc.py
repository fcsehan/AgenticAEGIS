"""Tests for AEGIS-1405: Legal Documentation Generator."""

from __future__ import annotations

import pytest

from aegis.editor.domain_model import CodeOfConductInfo, DomainInfo, Role, RuleInfo
from aegis.editor.legal_doc import LegalDocGenerator


@pytest.fixture()
def domain() -> DomainInfo:
    return DomainInfo(
        id="test",
        name="TestDomain",
        description="A domain for testing legal doc generation.",
        status="Draft",
        roles=[
            Role(id="analyst", name="analyst", description="Intelligence analyst", rule_count=2),
            Role(id="commander", name="commander", description="Mission commander", rule_count=1),
        ],
        codes=[
            CodeOfConductInfo(
                id="IntelCode", name="IntelCode",
                prevalence=2, description="Intelligence code",
            ),
            CodeOfConductInfo(id="MilitaryCode", name="MilitaryCode", prevalence=1),
        ],
        rules=[
            RuleInfo(id="r1", code="IntelCode", agent_role="analyst", modality="FORBIDDEN",
                     proposition="shareIntelligence classified", defeasible=True),
            RuleInfo(id="r2", code="IntelCode", agent_role="analyst", modality="OBLIGATORY",
                     proposition="reportAdverseEvent", defeasible=True),
            RuleInfo(id="r3", code="MilitaryCode", agent_role="commander", modality="PERMITTED",
                     proposition="shareIntelligence unclassified", defeasible=True),
            RuleInfo(id="r4", code="", agent_role="*", modality="FORBIDDEN",
                     proposition="deleteIntelligence", defeasible=False),
        ],
    )


class TestLegalDocStructure:
    def test_generates_markdown(self, domain: DomainInfo) -> None:
        gen = LegalDocGenerator(domain, locale="en")
        doc = gen.generate()
        assert isinstance(doc, str)
        assert len(doc) > 100

    def test_contains_domain_name(self, domain: DomainInfo) -> None:
        doc = LegalDocGenerator(domain).generate()
        assert "TestDomain" in doc

    def test_contains_overview(self, domain: DomainInfo) -> None:
        doc = LegalDocGenerator(domain).generate()
        assert "Domain Overview" in doc
        assert "Draft" in doc

    def test_contains_roles(self, domain: DomainInfo) -> None:
        doc = LegalDocGenerator(domain).generate()
        assert "Roles & Responsibilities" in doc
        assert "analyst" in doc
        assert "commander" in doc

    def test_contains_codes(self, domain: DomainInfo) -> None:
        doc = LegalDocGenerator(domain).generate()
        assert "Codes of Conduct" in doc
        assert "IntelCode" in doc
        assert "MilitaryCode" in doc

    def test_contains_obligations(self, domain: DomainInfo) -> None:
        doc = LegalDocGenerator(domain).generate()
        assert "Obligations" in doc
        assert "reportAdverseEvent" in doc

    def test_contains_prohibitions(self, domain: DomainInfo) -> None:
        doc = LegalDocGenerator(domain).generate()
        assert "Prohibitions" in doc
        assert "shareIntelligence" in doc

    def test_contains_permissions(self, domain: DomainInfo) -> None:
        doc = LegalDocGenerator(domain).generate()
        assert "Permissions" in doc

    def test_contains_axioms(self, domain: DomainInfo) -> None:
        doc = LegalDocGenerator(domain).generate()
        assert "Moral Axioms" in doc
        assert "deleteIntelligence" in doc
        assert "cannot be overridden" in doc

    def test_no_sexpressions_in_main_body(self, domain: DomainInfo) -> None:
        doc = LegalDocGenerator(domain).generate()
        # Main body should not contain S-expressions
        before_appendix = doc.split("Appendix")[0] if "Appendix" in doc else doc
        assert "oughtToDo-WRT" not in before_appendix
        assert "forbiddenToDo-WRT" not in before_appendix


class TestLocale:
    def test_english(self, domain: DomainInfo) -> None:
        doc = LegalDocGenerator(domain, locale="en").generate()
        assert "Domain Overview" in doc
        assert "Obligations" in doc

    def test_legacy_locale_uses_english(self, domain: DomainInfo) -> None:
        doc = LegalDocGenerator(domain, locale="de").generate()
        assert "Domain Overview" in doc
        assert "Obligations" in doc
        assert "Prohibitions" in doc

    def test_unknown_locale_falls_back_to_english(self, domain: DomainInfo) -> None:
        doc = LegalDocGenerator(domain, locale="fr").generate()
        assert "Domain Overview" in doc


class TestOptionalSections:
    def test_with_meld_source(self, domain: DomainInfo) -> None:
        doc = LegalDocGenerator(domain).generate(
            meld_source="(forbiddenToDo-WRT IntelCode analyst (shareIntelligence classified))"
        )
        assert "Appendix: MELD Source" in doc
        assert "forbiddenToDo-WRT" in doc

    def test_without_meld_source_no_appendix(self, domain: DomainInfo) -> None:
        doc = LegalDocGenerator(domain).generate()
        assert "Appendix" not in doc

    def test_with_test_results(self, domain: DomainInfo) -> None:
        doc = LegalDocGenerator(domain).generate(
            test_results=[
                {
                    "rule": "r1", "action": "shareIntelligence",
                    "expected": "FORBIDDEN", "actual": "FORBIDDEN",
                },
                {
                    "rule": "r2", "action": "reportAdverseEvent",
                    "expected": "PERMITTED", "actual": "PERMITTED",
                },
            ]
        )
        assert "Test Results" in doc
        assert "FORBIDDEN" in doc

    def test_without_test_results(self, domain: DomainInfo) -> None:
        doc = LegalDocGenerator(domain).generate()
        assert "No test results available" in doc

    def test_with_conflicts(self, domain: DomainInfo) -> None:
        doc = LegalDocGenerator(domain).generate(
            conflicts=[{
                "normA": {"modality": "FORBIDDEN", "proposition": "shareIntelligence"},
                "normB": {"modality": "PERMITTED", "proposition": "shareIntelligence"},
                "resolved": True,
                "resolution": "Specificity",
            }]
        )
        assert "Conflict" in doc
        assert "Specificity" in doc


class TestEmptyDomain:
    def test_empty_domain(self) -> None:
        domain = DomainInfo(id="empty", name="Empty")
        doc = LegalDocGenerator(domain).generate()
        assert "Empty" in doc
        # Should not crash on empty rules/roles/codes
        assert "—" in doc  # em dash for empty sections
