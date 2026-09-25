"""End-to-end tests for the `aegis generate` CLI command.

Tests the full pipeline: CLI parsing → domain loading → MeldGenerator →
MELD expression building → optional verification → output.

Uses a mock LLM client that returns deterministic tool_call responses,
so no real API key is needed.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from aegis.cli import main
from aegis.editor.llm_provider import LLMClient, LLMProviderInfo
from aegis.editor.meld_generator import MeldGenerator, build_meld_expression, RuleProposal
from aegis.editor.domain_model import domain_from_meld
from aegis.guard.guard import Guard
from aegis.kb.meld_loader import extract_norm, parse_meld


# ── Test Domain (DevOps — smallest, always available) ───────────────

DEVOPS_DIR = Path(__file__).parent.parent / "aegis" / "domains" / "devops"


# ── Mock LLM Response ───────────────────────────────────────────────

def _mock_llm_response(*proposals: dict[str, Any]) -> dict[str, Any]:
    """Build a mock OpenAI-format response with tool_calls."""
    tool_calls = []
    for i, p in enumerate(proposals):
        tool_calls.append({
            "id": f"call_{i}",
            "type": "function",
            "function": {
                "name": "propose_rule",
                "arguments": json.dumps(p),
            },
        })
    return {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": tool_calls,
            },
            "finish_reason": "tool_calls",
        }],
    }


MOCK_SINGLE_FORBIDDEN = _mock_llm_response({
    "modality": "FORBIDDEN",
    "agent_role": "opencodeAgent",
    "code_of_conduct": "DevSecOps",
    "action_type": "deleteFile",
    "proposition_parameters": {"path": "productionData"},
    "defeasible": True,
    "reasoning": "Production data must not be deleted by automated agents.",
    "natural_language_summary": "Agents must not delete production data.",
})

MOCK_TWO_RULES = _mock_llm_response(
    {
        "modality": "PERMITTED",
        "agent_role": "developerAgent",
        "code_of_conduct": "DevSecOps",
        "action_type": "readFile",
        "proposition_parameters": {"path": "sourceFile"},
        "defeasible": True,
        "reasoning": "Developers need to read source files.",
        "natural_language_summary": "Developers may read source code.",
    },
    {
        "modality": "FORBIDDEN",
        "agent_role": "developerAgent",
        "code_of_conduct": "DevSecOps",
        "action_type": "readFile",
        "proposition_parameters": {"path": "sensitiveConfig"},
        "defeasible": True,
        "reasoning": "Sensitive config must not be read directly.",
        "natural_language_summary": "Developers must not read sensitive configuration.",
    },
)

MOCK_EMPTY = {"choices": [{"message": {"role": "assistant", "content": "No rules needed.", "tool_calls": []}, "finish_reason": "stop"}]}


class MockLLMClient:
    """LLMClient replacement that returns pre-built responses."""

    def __init__(self, response: dict[str, Any]) -> None:
        self._response = response
        self.call_count = 0

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self.call_count += 1
        return self._response

    @property
    def provider_id(self) -> str:
        return "mock"

    @property
    def model_id(self) -> str:
        return "mock-model"


# ── Unit Tests: build_meld_expression roundtrip ─────────────────────


class TestBuildMeldExpressionRoundtrip:
    """Generated MELD expressions must parse back to valid NormFrames."""

    @pytest.mark.parametrize("modality", ["OBLIGATORY", "FORBIDDEN", "PERMITTED"])
    def test_wrt_rule_roundtrip(self, modality: str) -> None:
        proposal = RuleProposal(
            modality=modality,
            agent_role="testAgent",
            code_of_conduct="TestCode",
            action_type="doAction",
            proposition_parameters={"target": "something"},
            defeasible=True,
            reasoning="test",
            natural_language_summary="test",
        )
        expr = build_meld_expression(proposal)
        assertions = parse_meld(expr)
        assert len(assertions) == 1
        norm = extract_norm(assertions[0], "gen", "gen:1")
        assert norm is not None
        assert norm.modality.value == modality
        assert norm.agent_pattern == "testAgent"
        assert norm.code == "TestCode"

    @pytest.mark.parametrize("modality", ["OBLIGATORY", "FORBIDDEN", "PERMITTED"])
    def test_axiom_roundtrip(self, modality: str) -> None:
        proposal = RuleProposal(
            modality=modality,
            agent_role="*",
            code_of_conduct="",
            action_type="neverDoThis",
            proposition_parameters={},
            defeasible=False,
            reasoning="moral axiom",
            natural_language_summary="test",
        )
        expr = build_meld_expression(proposal)
        assertions = parse_meld(expr)
        norm = extract_norm(assertions[0], "gen", "gen:1")
        assert norm is not None
        assert norm.code == ""
        assert norm.agent_pattern == "*"


# ── Integration: MeldGenerator with Mock LLM ───────────────────────


class TestMeldGeneratorMocked:
    """MeldGenerator.generate() with a mock LLM client."""

    def test_single_proposal(self) -> None:
        guard = Guard.from_meld_files(sorted(DEVOPS_DIR.glob("*.meld")))
        domain = domain_from_meld("devops", "DevOps", sorted(DEVOPS_DIR.glob("*.meld")), guard, guard._norms, guard._kb)

        client = MockLLMClient(MOCK_SINGLE_FORBIDDEN)
        gen = MeldGenerator(client, domain)
        proposals = gen.generate("Agents must not delete production data.")

        assert len(proposals) == 1
        assert proposals[0].modality == "FORBIDDEN"
        assert proposals[0].agent_role == "opencodeAgent"
        assert proposals[0].meld_expression != ""
        assert client.call_count == 1

    def test_multiple_proposals(self) -> None:
        guard = Guard.from_meld_files(sorted(DEVOPS_DIR.glob("*.meld")))
        domain = domain_from_meld("devops", "DevOps", sorted(DEVOPS_DIR.glob("*.meld")), guard, guard._norms, guard._kb)

        client = MockLLMClient(MOCK_TWO_RULES)
        gen = MeldGenerator(client, domain)
        proposals = gen.generate("Developers may read code but must not read secrets.")

        assert len(proposals) == 2
        modalities = {p.modality for p in proposals}
        assert modalities == {"PERMITTED", "FORBIDDEN"}

    def test_empty_response(self) -> None:
        guard = Guard.from_meld_files(sorted(DEVOPS_DIR.glob("*.meld")))
        domain = domain_from_meld("devops", "DevOps", sorted(DEVOPS_DIR.glob("*.meld")), guard, guard._norms, guard._kb)

        client = MockLLMClient(MOCK_EMPTY)
        gen = MeldGenerator(client, domain)
        proposals = gen.generate("Nichts zu tun.")

        assert proposals == []

    def test_generated_meld_is_valid(self) -> None:
        """Every generated MELD expression must parse and extract a NormFrame."""
        guard = Guard.from_meld_files(sorted(DEVOPS_DIR.glob("*.meld")))
        domain = domain_from_meld("devops", "DevOps", sorted(DEVOPS_DIR.glob("*.meld")), guard, guard._norms, guard._kb)

        client = MockLLMClient(MOCK_TWO_RULES)
        gen = MeldGenerator(client, domain)
        proposals = gen.generate("test")

        for p in proposals:
            assertions = parse_meld(p.meld_expression)
            assert len(assertions) == 1, f"Failed to parse: {p.meld_expression}"
            norm = extract_norm(assertions[0], "gen", "gen")
            assert norm is not None, f"Failed to extract: {p.meld_expression}"


# ── End-to-End: Generated rules load into Guard ─────────────────────


class TestGenerateToGuardE2E:
    """Full cycle: generate → build MELD → load into Guard → check action."""

    def test_generated_rule_affects_verdict(self) -> None:
        """A generated FORBIDDEN rule must cause the Guard to return FORBIDDEN."""
        # 1. Generate a proposal
        proposal = RuleProposal(
            modality="FORBIDDEN",
            agent_role="opencodeAgent",
            code_of_conduct="DevSecOps",
            action_type="deleteFile",
            proposition_parameters={"path": "productionData"},
            defeasible=True,
            reasoning="test",
            natural_language_summary="test",
        )
        meld_expr = build_meld_expression(proposal)

        # 2. Build a complete MELD file with the new rule
        existing_files = sorted(DEVOPS_DIR.glob("*.meld"))
        all_meld_content: list[str] = []
        for f in existing_files:
            all_meld_content.append(f.read_text(encoding="utf-8"))

        # Add the generated rule to the rules file content
        generated_mt = textwrap.dedent(f"""\
            (aegis-schema-version 1)
            (case GeneratedRulesMt)
            {meld_expr}
        """)

        # 3. Load everything into a Guard via temp files
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            # Copy existing domain files
            for f in existing_files:
                (Path(tmpdir) / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            # Add generated rules
            (Path(tmpdir) / "GeneratedRulesMt.meld").write_text(generated_mt, encoding="utf-8")

            guard = Guard.from_meld_files(
                sorted(Path(tmpdir).glob("*.meld")),
                code_prevalence=["DevSecOps"],
            )

        # 4. Check that the new rule is active
        from aegis.guard.action import Action

        verdict = guard.check(Action(
            action_type="deleteFile",
            agent_id="opencodeAgent",
            proposition={"path": "productionData"},
        ))
        assert verdict.decision.value == "FORBIDDEN", (
            f"Expected FORBIDDEN, got {verdict.decision.value}: {verdict.justification_chain}"
        )

    def test_generated_permitted_rule_works(self) -> None:
        """A generated PERMITTED rule must enable the action."""
        proposal = RuleProposal(
            modality="PERMITTED",
            agent_role="opencodeAgent",
            code_of_conduct="DevSecOps",
            action_type="readFile",
            proposition_parameters={"path": "documentFile"},
            defeasible=True,
            reasoning="test",
            natural_language_summary="test",
        )
        meld_expr = build_meld_expression(proposal)

        existing_files = sorted(DEVOPS_DIR.glob("*.meld"))
        generated_mt = f"(aegis-schema-version 1)\n(case GeneratedRulesMt)\n{meld_expr}\n"

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            for f in existing_files:
                (Path(tmpdir) / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            (Path(tmpdir) / "GeneratedRulesMt.meld").write_text(generated_mt, encoding="utf-8")

            guard = Guard.from_meld_files(
                sorted(Path(tmpdir).glob("*.meld")),
                code_prevalence=["DevSecOps"],
            )

        from aegis.guard.action import Action

        verdict = guard.check(Action(
            action_type="readFile",
            agent_id="opencodeAgent",
            proposition={"path": "documentFile"},
        ))
        assert verdict.decision.value == "PERMITTED"


# ── CLI Argument Parsing ────────────────────────────────────────────


class TestCLIArgParsing:
    """Test that the CLI subcommand parses correctly."""

    def test_generate_help_exits_zero(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["generate", "--help"])
        assert exc_info.value.code == 0

    def test_generate_missing_description_fails(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["generate", str(DEVOPS_DIR)])
        assert exc_info.value.code == 2  # argparse error

    def test_generate_missing_domain_fails(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["generate", "/nonexistent/path", "-d", "test"])
        assert exc_info.value.code != 0
