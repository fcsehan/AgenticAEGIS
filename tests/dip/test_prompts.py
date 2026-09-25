"""Tests for DIP prompts and tool schemas."""

from aegis.dip.prompts import (
    DEFINE_ONTOLOGY_TOOL,
    EXTRACT_STATEMENT_TOOL,
    build_extractor_system_prompt,
    build_extractor_user_message,
    build_ontology_system_prompt,
    build_ontology_user_message,
)


class TestExtractStatementTool:
    def test_has_required_fields(self) -> None:
        params = EXTRACT_STATEMENT_TOOL["function"]["parameters"]
        required = params["required"]
        assert "source_ref" in required
        assert "modality" in required
        assert "subject" in required
        assert "action" in required
        assert "confidence" in required

    def test_modality_enum(self) -> None:
        props = EXTRACT_STATEMENT_TOOL["function"]["parameters"]["properties"]
        assert set(props["modality"]["enum"]) == {"OBLIGATORY", "FORBIDDEN", "PERMITTED"}

    def test_optional_fields_present(self) -> None:
        props = EXTRACT_STATEMENT_TOOL["function"]["parameters"]["properties"]
        assert "conditions" in props
        assert "exceptions" in props
        assert "vague_terms" in props
        assert "object_description" in props


class TestDefineOntologyTool:
    def test_has_required_fields(self) -> None:
        params = DEFINE_ONTOLOGY_TOOL["function"]["parameters"]
        required = params["required"]
        assert "roles" in required
        assert "actions" in required
        assert "codes" in required

    def test_role_structure(self) -> None:
        props = DEFINE_ONTOLOGY_TOOL["function"]["parameters"]["properties"]
        role_item = props["roles"]["items"]
        assert "natural_name" in role_item["properties"]
        assert "meld_symbol" in role_item["properties"]

    def test_action_has_parameters(self) -> None:
        props = DEFINE_ONTOLOGY_TOOL["function"]["parameters"]["properties"]
        action_item = props["actions"]["items"]
        assert "parameters" in action_item["properties"]


class TestExtractorPrompt:
    def test_includes_modalities(self) -> None:
        prompt = build_extractor_system_prompt()
        assert "OBLIGATORY" in prompt
        assert "FORBIDDEN" in prompt
        assert "PERMITTED" in prompt

    def test_domain_context_included(self) -> None:
        prompt = build_extractor_system_prompt(
            domain_context="Military engagement rules"
        )
        assert "Military engagement rules" in prompt

    def test_no_domain_context(self) -> None:
        prompt = build_extractor_system_prompt()
        assert "Domain Context" not in prompt

    def test_user_message_format(self) -> None:
        chunks = [
            {"article_ref": "Art. 5(1)", "text": "Data must be processed.", "chunk_type": "obligation"},
            {"article_ref": "Art. 6(1)", "text": "Processing is lawful.", "chunk_type": "permission"},
        ]
        msg = build_extractor_user_message(chunks)
        assert "2 text chunks" in msg
        assert "Art. 5(1)" in msg
        assert "Art. 6(1)" in msg
        assert "Chunk 1" in msg
        assert "Chunk 2" in msg


class TestOntologyPrompt:
    def test_includes_conventions(self) -> None:
        prompt = build_ontology_system_prompt()
        assert "camelCase" in prompt
        assert "ASCII" in prompt

    def test_domain_context_included(self) -> None:
        prompt = build_ontology_system_prompt(
            domain_context="ISO 27001 information security"
        )
        assert "ISO 27001" in prompt

    def test_includes_examples(self) -> None:
        prompt = build_ontology_system_prompt()
        assert "dataController" in prompt
        assert "deleteData" in prompt

    def test_user_message_format(self) -> None:
        stmts = [
            {"source_article": "Art. 17(1)", "modality": "OBLIGATORY", "subject": "controller", "action": "delete data"},
        ]
        msg = build_ontology_user_message(stmts)
        assert "1 normative statements" in msg
        assert "OBLIGATORY" in msg
        assert "controller" in msg
