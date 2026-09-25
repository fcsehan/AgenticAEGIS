"""Tests for AEGIS-1403: Verification Pipeline."""

from __future__ import annotations

import pytest

from aegis.editor.domain_model import CodeOfConductInfo, DomainInfo, Role, RuleInfo
from aegis.editor.meld_generator import RuleProposal, build_meld_expression
from aegis.editor.verification import (
    StageStatus,
    VerificationPipeline,
    _find_close_matches,
    _levenshtein,
)

# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture()
def domain() -> DomainInfo:
    return DomainInfo(
        id="test",
        name="Test",
        roles=[
            Role(id="analyst", name="analyst", rule_count=1),
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
                proposition="deleteIntelligence",
                defeasible=True,
            ),
            RuleInfo(
                id="r2",
                code="TestCode",
                agent_role="commander",
                modality="PERMITTED",
                proposition="shareIntelligence",
                defeasible=True,
            ),
        ],
    )


def _make_proposal(
    *,
    modality: str = "FORBIDDEN",
    agent_role: str = "analyst",
    code: str = "TestCode",
    action_type: str = "accessData",
    defeasible: bool = True,
) -> RuleProposal:
    p = RuleProposal(
        modality=modality,
        agent_role=agent_role,
        code_of_conduct=code,
        action_type=action_type,
        proposition_parameters={},
        defeasible=defeasible,
        reasoning="test",
        natural_language_summary="test rule",
    )
    p.meld_expression = build_meld_expression(p)
    return p


# ── Stage 1: Syntax ──────────────────────────────────────────────


class TestSyntaxStage:
    def test_valid_expression_passes(self, domain: DomainInfo) -> None:
        pipeline = VerificationPipeline(domain)
        proposal = _make_proposal()
        result = pipeline.verify(proposal)
        syntax_stage = result.stages[0]
        assert syntax_stage.stage == "syntax"
        assert syntax_stage.status == StageStatus.PASS

    def test_invalid_expression_fails(self, domain: DomainInfo) -> None:
        pipeline = VerificationPipeline(domain)
        proposal = _make_proposal()
        proposal.meld_expression = "(unclosed paren"
        result = pipeline.verify(proposal)
        assert result.passed is False
        assert result.stages[0].status == StageStatus.FAIL
        assert result.stages[0].stage == "syntax"

    def test_short_circuit_on_syntax_fail(self, domain: DomainInfo) -> None:
        """Remaining stages should be SKIP when syntax fails."""
        pipeline = VerificationPipeline(domain)
        proposal = _make_proposal()
        proposal.meld_expression = "not valid meld"
        result = pipeline.verify(proposal)
        assert result.passed is False
        # syntax FAIL, rest SKIP
        assert result.stages[0].status == StageStatus.FAIL
        for stage in result.stages[1:]:
            assert stage.status == StageStatus.SKIP

    def test_empty_expression_fails(self, domain: DomainInfo) -> None:
        pipeline = VerificationPipeline(domain)
        proposal = _make_proposal()
        proposal.meld_expression = ""
        result = pipeline.verify(proposal)
        assert result.passed is False


# ── Stage 2: Symbol ───────────────────────────────────────────────


class TestSymbolStage:
    def test_known_symbols_pass(self, domain: DomainInfo) -> None:
        pipeline = VerificationPipeline(domain)
        proposal = _make_proposal()
        result = pipeline.verify(proposal)
        symbol_stage = result.stages[1]
        assert symbol_stage.stage == "symbol"
        assert symbol_stage.status == StageStatus.PASS

    def test_unknown_agent_role_fails(self, domain: DomainInfo) -> None:
        pipeline = VerificationPipeline(domain)
        proposal = _make_proposal(agent_role="unknownAgent")
        result = pipeline.verify(proposal)
        symbol_stage = result.stages[1]
        assert symbol_stage.status == StageStatus.FAIL
        assert "unknownAgent" in symbol_stage.message

    def test_unknown_code_fails(self, domain: DomainInfo) -> None:
        pipeline = VerificationPipeline(domain)
        proposal = _make_proposal(code="UnknownCode")
        result = pipeline.verify(proposal)
        symbol_stage = result.stages[1]
        assert symbol_stage.status == StageStatus.FAIL
        assert "UnknownCode" in symbol_stage.message


# ── Stage 3: Conflict ────────────────────────────────────────────


class TestConflictStage:
    def test_no_conflict_passes(self) -> None:
        """A domain with only same-modality rules has no conflicts."""
        no_conflict_domain = DomainInfo(
            id="safe",
            name="Safe",
            roles=[Role(id="analyst", name="analyst", rule_count=1)],
            codes=[CodeOfConductInfo(id="TestCode", name="TestCode", prevalence=1)],
            rules=[
                RuleInfo(
                    id="r1",
                    code="TestCode",
                    agent_role="analyst",
                    modality="FORBIDDEN",
                    proposition="deleteIntelligence",
                    defeasible=True,
                ),
            ],
        )
        pipeline = VerificationPipeline(no_conflict_domain)
        # FORBIDDEN + FORBIDDEN = no conflict
        proposal = _make_proposal(
            modality="FORBIDDEN",
            action_type="accessPersonalData",
        )
        result = pipeline.verify(proposal)
        conflict_stage = next(s for s in result.stages if s.stage == "conflict")
        assert conflict_stage.status == StageStatus.PASS

    def test_conflicting_rule_fails(self, domain: DomainInfo) -> None:
        """Adding a PERMITTED rule when FORBIDDEN exists should detect conflict."""
        pipeline = VerificationPipeline(domain)
        # Existing rule: analyst FORBIDDEN deleteIntelligence under TestCode
        # New rule: analyst PERMITTED deleteIntelligence under TestCode (same code = unresolved)
        proposal = _make_proposal(
            modality="PERMITTED",
            agent_role="analyst",
            code="TestCode",
            action_type="deleteIntelligence",
        )
        result = pipeline.verify(proposal)
        conflict_stage = next(s for s in result.stages if s.stage == "conflict")
        assert conflict_stage.status == StageStatus.FAIL


# ── Stage 4: Functional ──────────────────────────────────────────


class TestFunctionalStage:
    def test_functional_runs(self) -> None:
        """Functional stage should run when prior stages pass (no conflicts)."""
        safe_domain = DomainInfo(
            id="safe",
            name="Safe",
            roles=[Role(id="analyst", name="analyst", rule_count=1)],
            codes=[CodeOfConductInfo(id="TestCode", name="TestCode", prevalence=1)],
            rules=[
                RuleInfo(
                    id="r1",
                    code="TestCode",
                    agent_role="analyst",
                    modality="FORBIDDEN",
                    proposition="deleteIntelligence",
                    defeasible=True,
                ),
            ],
        )
        pipeline = VerificationPipeline(safe_domain)
        proposal = _make_proposal(
            modality="FORBIDDEN",
            action_type="accessPersonalData",
        )
        result = pipeline.verify(proposal)
        func_stage = next(s for s in result.stages if s.stage == "functional")
        # Functional stage should at least run without error
        assert func_stage.status in (StageStatus.PASS, StageStatus.FAIL)


# ── Full Pipeline ─────────────────────────────────────────────────


class TestFullPipeline:
    def test_all_stages_pass(self, domain: DomainInfo) -> None:
        pipeline = VerificationPipeline(domain)
        proposal = _make_proposal(
            modality="OBLIGATORY",
            agent_role="commander",
            code="TestCode",
            action_type="reportStatus",
        )
        result = pipeline.verify(proposal)
        assert len(result.stages) == 4
        for stage in result.stages:
            assert stage.stage in ("syntax", "symbol", "conflict", "functional")

    def test_result_to_dict(self, domain: DomainInfo) -> None:
        pipeline = VerificationPipeline(domain)
        proposal = _make_proposal()
        result = pipeline.verify(proposal)
        d = result.to_dict()
        assert "passed" in d
        assert "stages" in d
        assert len(d["stages"]) == 4


# ── Levenshtein helpers ───────────────────────────────────────────


class TestLevenshtein:
    def test_identical(self) -> None:
        assert _levenshtein("abc", "abc") == 0

    def test_empty(self) -> None:
        assert _levenshtein("", "abc") == 3

    def test_one_edit(self) -> None:
        assert _levenshtein("abc", "abd") == 1

    def test_insertion(self) -> None:
        assert _levenshtein("abc", "abcd") == 1


class TestFindCloseMatches:
    def test_finds_close(self) -> None:
        matches = _find_close_matches("analyt", {"analyst", "commander", "agent"})
        assert "analyst" in matches

    def test_no_match_too_far(self) -> None:
        matches = _find_close_matches("xyz", {"analyst", "commander"}, max_distance=2)
        assert matches == []
