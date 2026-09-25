"""Tests for AEGIS-1005: System Prompts & Domain-Prompt-Templates."""

from __future__ import annotations

from pathlib import Path

from aegis.guard.registry import ActionTypeRegistry
from aegis.kb.knowledge_base import KnowledgeBase
from aegis.kb.meld_loader import MeldLoader
from aegis.orchestrator.prompts import (
    CANDIDATE_LIST_INSTRUCTIONS,
    DOMAIN_TEMPLATES,
    IA_MISSION_TEMPLATE,
    PromptTemplate,
    format_disambiguation_hints,
)


class TestPromptTemplate:
    def test_render_with_template(self) -> None:
        prompt = IA_MISSION_TEMPLATE.render({"agent_role": "Intelligence Officer"})
        assert "Intelligence Officer" in prompt
        assert "aegis_check" in prompt
        assert "FORBIDDEN" in prompt

    def test_render_without_context(self) -> None:
        prompt = IA_MISSION_TEMPLATE.render()
        # Unsubstituted placeholder stays as-is (safe format)
        assert "{agent_role}" in prompt
        assert "aegis_check" in prompt

    def test_assemble_without_template(self) -> None:
        pt = PromptTemplate(
            domain="test",
            role_description="You are a test agent.",
            available_actions=["testAction"],
        )
        prompt = pt.render()
        assert "test agent" in prompt
        assert "testAction" in prompt
        assert "aegis_check" in prompt
        assert "FORBIDDEN" in prompt
        assert "UNDECIDABLE" in prompt

    def test_from_file(self, tmp_path: Path) -> None:
        template_file = tmp_path / "test_prompt.txt"
        template_file.write_text(
            "You are {agent_role} in the {domain} domain.\n"
            "Available: {available_actions}"
        )
        pt = PromptTemplate.from_file(template_file, domain="test_domain")
        prompt = pt.render({"agent_role": "tester"})
        assert "tester" in prompt
        assert "test_domain" in prompt

    def test_all_domain_templates_exist(self) -> None:
        expected = {"ia_mission", "pharma", "sanctions", "legal"}
        assert set(DOMAIN_TEMPLATES.keys()) == expected

    def test_all_templates_render(self) -> None:
        for domain, template in DOMAIN_TEMPLATES.items():
            prompt = template.render({"agent_role": "TestAgent"})
            assert len(prompt) > 50, f"{domain} template too short"
            assert "aegis_check" in prompt, f"{domain} missing aegis_check"

    def test_ia_mission_critical_rules(self) -> None:
        prompt = IA_MISSION_TEMPLATE.render({"agent_role": "intel officer"})
        assert "NEVER" in prompt
        assert "classified" in prompt.lower()

    def test_frozen(self) -> None:
        try:
            IA_MISSION_TEMPLATE.domain = "changed"  # type: ignore[misc]
            raise AssertionError("Should raise")
        except AttributeError:
            pass


def _registry_with_disambiguation() -> ActionTypeRegistry:
    """Build a registry with a small disambiguation set used by the
    AEGIS-2904 tests below."""
    kb = KnowledgeBase()
    loader = MeldLoader(kb)
    loader.load_string(
        """
        (case TestVocabMt)
        (isa readDiagnosis ActionType)
        (isa readPatientRecord ActionType)
        (isa share ActionType)
        (actionDescription readDiagnosis "Reads only the diagnostic conclusion section.")
        (actionDescription readPatientRecord "Reads the entire patient record.")
        (actionSynonym readDiagnosis "view diagnosis")
        (actionSynonym readDiagnosis "view diagnostic findings")
        (notToBeConfusedWith readDiagnosis readPatientRecord)
        (narrowerThan readDiagnosis readPatientRecord)
        (broaderThan readPatientRecord readDiagnosis)
        """,
        file="test.meld",
    )
    loader.validate_disambiguation_graph()
    kb.freeze()
    return ActionTypeRegistry.from_kb(kb)


class TestFormatDisambiguationHints:
    def test_empty_input_returns_empty_string(self) -> None:
        registry = _registry_with_disambiguation()
        assert format_disambiguation_hints(registry, []) == ""

    def test_action_without_metadata_renders_plain(self) -> None:
        registry = _registry_with_disambiguation()
        result = format_disambiguation_hints(registry, ["share"])
        # `share` has no description/synonyms/confusables.
        assert result == "- share"

    def test_action_with_full_metadata(self) -> None:
        registry = _registry_with_disambiguation()
        result = format_disambiguation_hints(registry, ["readDiagnosis"])
        assert "- readDiagnosis" in result
        assert "Reads only the diagnostic conclusion section." in result
        assert 'Synonyms: "view diagnosis", "view diagnostic findings"' in result
        assert "Do not confuse with: readPatientRecord" in result

    def test_listing_preserves_input_order(self) -> None:
        registry = _registry_with_disambiguation()
        result = format_disambiguation_hints(
            registry, ["readPatientRecord", "readDiagnosis"]
        )
        idx_pat = result.index("readPatientRecord")
        idx_diag = result.index("- readDiagnosis")
        assert idx_pat < idx_diag


class TestWithDisambiguationHints:
    def test_returns_template_with_detailed_field_set(self) -> None:
        registry = _registry_with_disambiguation()
        base = PromptTemplate(
            domain="test",
            role_description="Test agent.",
            available_actions=["readDiagnosis", "share"],
            template="Actions: {available_actions_detailed}",
        )
        enriched = base.with_disambiguation_hints(registry)
        assert enriched.available_actions_detailed
        rendered = enriched.render()
        assert "readDiagnosis" in rendered
        assert "Reads only the diagnostic conclusion section." in rendered

    def test_falls_back_to_flat_listing_when_unset(self) -> None:
        """Templates that reference {available_actions_detailed} but
        are never enriched should fall back to the flat listing rather
        than rendering an empty section."""
        base = PromptTemplate(
            domain="test",
            role_description="Test agent.",
            available_actions=["readDiagnosis", "share"],
            template="Actions: {available_actions_detailed}",
        )
        rendered = base.render()
        assert "readDiagnosis" in rendered
        assert "share" in rendered

    def test_empty_registry_returns_self(self) -> None:
        kb = KnowledgeBase()
        kb.create_mt("Empty")
        kb.freeze()
        empty_reg = ActionTypeRegistry.from_kb(kb)
        base = PromptTemplate(
            domain="test",
            role_description="Test agent.",
        )
        result = base.with_disambiguation_hints(empty_reg)
        # No actions in registry, no available_actions on the template:
        # method returns self unchanged.
        assert result is base or result == base

    def test_existing_templates_still_render_unchanged(self) -> None:
        """The existing IA_MISSION_TEMPLATE uses {available_actions} —
        adding the new {available_actions_detailed} support must not
        break it."""
        prompt = IA_MISSION_TEMPLATE.render({"agent_role": "Intelligence Officer"})
        assert "shareIntelligence" in prompt or "deleteIntelligence" in prompt


class TestCandidateListInstructions:
    """AEGIS-3206: prompt-side instruction telling the LLM to enumerate
    all plausible action candidates instead of picking one."""

    def test_module_constant_exists(self) -> None:
        assert CANDIDATE_LIST_INSTRUCTIONS
        assert "aegis_check_candidates" in CANDIDATE_LIST_INSTRUCTIONS
        assert "narrower" in CANDIDATE_LIST_INSTRUCTIONS

    def test_template_can_embed_candidate_instructions(self) -> None:
        """A template referencing {candidate_list_instructions} renders
        the constant string in place."""
        pt = PromptTemplate(
            domain="test",
            role_description="Test agent.",
            template="Role: test\n\n{candidate_list_instructions}",
        )
        rendered = pt.render(
            {"candidate_list_instructions": CANDIDATE_LIST_INSTRUCTIONS},
        )
        assert "aegis_check_candidates" in rendered

    def test_constant_warns_against_brainstorming(self) -> None:
        """The instruction must explicitly forbid using the candidate
        list as a brainstorming aid — that subtlety matters because a
        permissive interpretation breaks B2 (caller provides complete
        candidate set) from Epic 32."""
        assert "brainstorming" in CANDIDATE_LIST_INSTRUCTIONS.lower()


class TestPromptYAMLFiles:
    """Verify the YAML test prompt files are loadable and well-structured."""

    def test_ia_mission_prompts_loadable(self) -> None:
        import yaml

        path = Path(__file__).parent.parent / "prompts" / "ia_mission_prompts.yaml"
        with path.open() as f:
            data = yaml.safe_load(f)
        assert data["domain"] == "ia_mission"
        assert len(data["scenarios"]) >= 5

    def test_all_prompt_files_valid(self) -> None:
        import yaml

        prompts_dir = Path(__file__).parent.parent / "prompts"
        yaml_files = list(prompts_dir.glob("*.yaml"))
        assert len(yaml_files) >= 4

        for yf in yaml_files:
            with yf.open() as f:
                data = yaml.safe_load(f)
            assert "domain" in data, f"{yf.name} missing 'domain'"
            assert "scenarios" in data, f"{yf.name} missing 'scenarios'"
            for scenario in data["scenarios"]:
                assert "id" in scenario, f"{yf.name} scenario missing 'id'"
                assert "user_prompt" in scenario, f"{yf.name} scenario missing prompt"
                assert "expected_verdict" in scenario or "expected_actions" in scenario, (
                    f"{yf.name} scenario {scenario['id']} missing expected verdict"
                )
