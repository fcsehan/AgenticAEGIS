"""Tests for AEGIS-1402: MELD Generation Engine."""

from __future__ import annotations

import pytest

from aegis.editor.domain_model import CodeOfConductInfo, DomainInfo, Role, RuleInfo
from aegis.editor.meld_generator import (
    RuleProposal,
    build_meld_expression,
)
from aegis.kb.meld_loader import extract_norm, parse_meld

# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture()
def sample_domain() -> DomainInfo:
    return DomainInfo(
        id="test_domain",
        name="TestDomain",
        description="A test domain for unit tests.",
        roles=[
            Role(id="analyst", name="analyst", rule_count=2),
            Role(id="commander", name="commander", rule_count=1),
        ],
        codes=[
            CodeOfConductInfo(id="TestCode", name="TestCode", prevalence=1),
        ],
        rules=[
            RuleInfo(
                id="r1",
                code="TestCode",
                agent_role="analyst",
                modality="FORBIDDEN",
                proposition="deleteIntelligence classified",
            ),
        ],
    )


@pytest.fixture()
def sample_proposal() -> RuleProposal:
    return RuleProposal(
        modality="FORBIDDEN",
        agent_role="analyst",
        code_of_conduct="TestCode",
        action_type="shareIntelligence",
        proposition_parameters={"classification": "classified"},
        defeasible=True,
        reasoning="Classified intelligence must not be shared by analysts.",
        natural_language_summary="Analysts are forbidden from sharing classified intelligence.",
    )


@pytest.fixture()
def axiom_proposal() -> RuleProposal:
    return RuleProposal(
        modality="FORBIDDEN",
        agent_role="*",
        code_of_conduct="",
        action_type="deleteIntelligence",
        proposition_parameters={},
        defeasible=False,
        reasoning="Intelligence deletion is universally prohibited.",
        natural_language_summary="No agent may delete intelligence records.",
    )


# ── build_meld_expression tests ──────────────────────────────────


class TestBuildMeldExpression:
    def test_wrt_rule(self, sample_proposal: RuleProposal) -> None:
        expr = build_meld_expression(sample_proposal)
        assert expr.startswith("(forbiddenToDo-WRT")
        assert "TestCode" in expr
        assert "analyst" in expr
        assert "shareIntelligence" in expr

    def test_axiom_rule(self, axiom_proposal: RuleProposal) -> None:
        expr = build_meld_expression(axiom_proposal)
        assert expr.startswith("(forbiddenToDo")
        assert "-WRT" not in expr
        assert "*" in expr
        assert "deleteIntelligence" in expr

    def test_obligatory_wrt(self) -> None:
        p = RuleProposal(
            modality="OBLIGATORY",
            agent_role="commander",
            code_of_conduct="MilitaryCode",
            action_type="reportStatus",
            proposition_parameters={},
            defeasible=True,
            reasoning="",
            natural_language_summary="Commanders must report status.",
        )
        expr = build_meld_expression(p)
        assert expr.startswith("(oughtToDo-WRT")
        assert "MilitaryCode" in expr

    def test_permitted_wrt(self) -> None:
        p = RuleProposal(
            modality="PERMITTED",
            agent_role="analyst",
            code_of_conduct="IntelCode",
            action_type="accessData",
            proposition_parameters={"level": "unclassified"},
            defeasible=True,
            reasoning="",
            natural_language_summary="Analysts may access unclassified data.",
        )
        expr = build_meld_expression(p)
        assert expr.startswith("(permittedToDo-WRT")

    def test_expression_is_parseable(self, sample_proposal: RuleProposal) -> None:
        """Every generated expression must be valid MELD."""
        expr = build_meld_expression(sample_proposal)
        assertions = parse_meld(expr)
        assert len(assertions) == 1

    def test_expression_extracts_norm(self, sample_proposal: RuleProposal) -> None:
        """Every generated expression must produce a NormFrame."""
        expr = build_meld_expression(sample_proposal)
        assertions = parse_meld(expr)
        norm = extract_norm(assertions[0], "test", "test")
        assert norm is not None
        assert norm.modality.value == "FORBIDDEN"
        assert norm.agent_pattern == "analyst"
        assert norm.code == "TestCode"

    def test_axiom_expression_extracts_norm(self, axiom_proposal: RuleProposal) -> None:
        expr = build_meld_expression(axiom_proposal)
        assertions = parse_meld(expr)
        norm = extract_norm(assertions[0], "test", "test")
        assert norm is not None
        assert norm.code == ""
        assert norm.agent_pattern == "*"


class TestRuleProposal:
    def test_to_dict(self, sample_proposal: RuleProposal) -> None:
        d = sample_proposal.to_dict()
        assert d["modality"] == "FORBIDDEN"
        assert d["agentRole"] == "analyst"
        assert d["codeOfConduct"] == "TestCode"
        assert d["actionType"] == "shareIntelligence"
        assert d["defeasible"] is True
        assert "naturalLanguageSummary" in d

    def test_all_modalities_produce_valid_meld(self) -> None:
        """Test that all three modalities produce parseable MELD."""
        for modality in ("OBLIGATORY", "FORBIDDEN", "PERMITTED"):
            p = RuleProposal(
                modality=modality,
                agent_role="agent",
                code_of_conduct="Code",
                action_type="doSomething",
                proposition_parameters={},
                defeasible=True,
                reasoning="",
                natural_language_summary="test",
            )
            expr = build_meld_expression(p)
            assertions = parse_meld(expr)
            assert len(assertions) == 1
            norm = extract_norm(assertions[0], "test", "test")
            assert norm is not None
            assert norm.modality.value == modality
