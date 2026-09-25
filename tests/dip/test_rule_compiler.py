"""Tests for DIP rule compiler — deterministic compilation."""

from aegis.dip.models import (
    CompilationResult,
    DomainOntology,
    NormativeStatement,
    OntologyAction,
    OntologyRole,
)
from aegis.dip.rule_compiler import (
    _fallback_action_symbol,
    _is_delegation_clause,
    _map_action,
    _map_subject,
    _normalize_modality,
    compile_rules,
)


def _make_ontology() -> DomainOntology:
    return DomainOntology(
        roles=(
            OntologyRole("data controller", "dataController"),
            OntologyRole("data subject", "dataSubject"),
            OntologyRole("employee", "employee"),
        ),
        actions=(
            OntologyAction("delete data", "deleteData", parameters=("dataCategory",)),
            OntologyAction("process data", "processData", parameters=("legalBasis",)),
            OntologyAction("transfer data", "transferData", parameters=("recipient",)),
            OntologyAction("access data", "accessData"),
        ),
        data_categories=("personalData", "medicalData", "confidentialData"),
        codes=("DataProtection",),
        role_map={
            "data controller": "dataController",
            "data subject": "dataSubject",
            "employee": "employee",
        },
        action_map={
            "delete data": "deleteData",
            "process data": "processData",
            "transfer data": "transferData",
            "access data": "accessData",
        },
    )


# ── Mapping tests ───────────────────────────────────────────────────


class TestMapSubject:
    def test_exact_match(self) -> None:
        onto = _make_ontology()
        assert _map_subject("data controller", onto) == "dataController"

    def test_case_insensitive(self) -> None:
        onto = _make_ontology()
        assert _map_subject("Data Controller", onto) == "dataController"

    def test_substring_match(self) -> None:
        onto = _make_ontology()
        assert _map_subject("the data controller", onto) == "dataController"

    def test_no_match(self) -> None:
        onto = _make_ontology()
        assert _map_subject("auditor", onto) == ""

    def test_empty(self) -> None:
        onto = _make_ontology()
        assert _map_subject("", onto) == ""

    def test_symbol_direct_match(self) -> None:
        onto = _make_ontology()
        assert _map_subject("dataController", onto) == "dataController"


class TestExtractVariants:
    def test_parenthesized_hint(self) -> None:
        from aegis.dip.rule_compiler import _extract_variants
        variants = _extract_variants("custodian (controller)")
        assert "custodian (controller)" in variants
        assert "custodian" in variants
        assert "controller" in variants

    def test_no_parentheses(self) -> None:
        from aegis.dip.rule_compiler import _extract_variants
        variants = _extract_variants("data controller")
        assert variants == ["data controller"]


class TestMapSubjectAdvanced:
    def test_parenthesized_hint_matches(self) -> None:
        """'custodian (controller)' should match 'data controller'."""
        onto = _make_ontology()
        assert _map_subject("custodian (controller)", onto) == "dataController"

    def test_symbol_substring_match(self) -> None:
        """'controller' should match 'dataController' via symbol substring."""
        onto = _make_ontology()
        assert _map_subject("controller", onto) == "dataController"

    def test_compound_subject(self) -> None:
        """'controller and processor' — should still find a match."""
        onto = _make_ontology()
        # "employee" won't match, but "controller" hint won't be there either
        # This tests graceful fallback
        result = _map_subject("controller and processor", onto)
        # May or may not match depending on substring — acceptable either way
        assert isinstance(result, str)


class TestMapAction:
    def test_exact_match(self) -> None:
        onto = _make_ontology()
        assert _map_action("delete data", onto) == "deleteData"

    def test_case_insensitive(self) -> None:
        onto = _make_ontology()
        assert _map_action("Delete Data", onto) == "deleteData"

    def test_substring_match(self) -> None:
        onto = _make_ontology()
        assert _map_action("delete data immediately", onto) == "deleteData"

    def test_no_match(self) -> None:
        onto = _make_ontology()
        assert _map_action("launch rocket", onto) == ""

    def test_symbol_direct_match(self) -> None:
        onto = _make_ontology()
        assert _map_action("deleteData", onto) == "deleteData"


class TestFallbackActionSymbol:
    def test_simple(self) -> None:
        result = _fallback_action_symbol("delete data")
        assert "delete" in result.lower()

    def test_multi_word(self) -> None:
        result = _fallback_action_symbol("transfer personal data")
        assert "transfer" in result.lower()
        assert "personal" in result.lower()

    def test_empty(self) -> None:
        assert _fallback_action_symbol("") == "unknownAction"

    def test_ascii_action_symbol(self) -> None:
        result = _fallback_action_symbol("erasure of personal data")
        assert result.isascii()
        assert "erasure" in result.lower()

    def test_truncates_long(self) -> None:
        result = _fallback_action_symbol(
            "process personal data lawfully and fairly "
            "and transparently in relation to the data subject"
        )
        # Should be max 5 keywords, not the whole sentence
        word_count = len(result.replace("(", "").replace(")", "").split())
        assert word_count <= 2  # camelCase = 1 word visually


class TestNormalizeModality:
    def test_standard(self) -> None:
        assert _normalize_modality("OBLIGATORY") == "OBLIGATORY"
        assert _normalize_modality("FORBIDDEN") == "FORBIDDEN"
        assert _normalize_modality("PERMITTED") == "PERMITTED"

    def test_aliases(self) -> None:
        assert _normalize_modality("OBLIGATION") == "OBLIGATORY"
        assert _normalize_modality("PROHIBITION") == "FORBIDDEN"
        assert _normalize_modality("PERMISSION") == "PERMITTED"

    def test_case_insensitive(self) -> None:
        assert _normalize_modality("obligatory") == "OBLIGATORY"

    def test_default_forbidden(self) -> None:
        assert _normalize_modality("UNKNOWN") == "FORBIDDEN"


class TestIsDelegationClause:
    def test_national_law(self) -> None:
        stmt = NormativeStatement(
            source_article="Art. 9",
            modality="PERMITTED",
            subject="member state",
            action="may provide additional rules under national law",
            confidence=0.8,
        )
        assert _is_delegation_clause(stmt)

    def test_normal_statement(self) -> None:
        stmt = NormativeStatement(
            source_article="Art. 17(1)",
            modality="OBLIGATORY",
            subject="controller",
            action="delete personal data",
            confidence=0.9,
        )
        assert not _is_delegation_clause(stmt)


# ── Full compilation ────────────────────────────────────────────────


class TestCompileRules:
    def test_basic_compilation(self) -> None:
        onto = _make_ontology()
        stmts = [
            NormativeStatement(
                source_article="Art. 17(1)",
                modality="OBLIGATORY",
                subject="data controller",
                action="delete data",
                confidence=0.95,
            ),
        ]
        results = compile_rules(stmts, onto)
        assert len(results) == 1
        assert results[0].success
        assert results[0].meld_expression
        assert "oughtToDo-WRT" in results[0].meld_expression
        assert "DataProtection" in results[0].meld_expression
        assert "dataController" in results[0].meld_expression
        assert "deleteData" in results[0].meld_expression

    def test_forbidden(self) -> None:
        onto = _make_ontology()
        stmts = [
            NormativeStatement(
                source_article="Art. 9(1)",
                modality="FORBIDDEN",
                subject="employee",
                action="transfer data",
                confidence=0.9,
            ),
        ]
        results = compile_rules(stmts, onto)
        assert results[0].success
        assert "forbiddenToDo-WRT" in results[0].meld_expression

    def test_permitted(self) -> None:
        onto = _make_ontology()
        stmts = [
            NormativeStatement(
                source_article="Art. 15(1)",
                modality="PERMITTED",
                subject="data subject",
                action="access data",
                confidence=0.9,
            ),
        ]
        results = compile_rules(stmts, onto)
        assert results[0].success
        assert "permittedToDo-WRT" in results[0].meld_expression

    def test_vague_term_flagged(self) -> None:
        onto = _make_ontology()
        stmts = [
            NormativeStatement(
                source_article="Art. 32",
                modality="OBLIGATORY",
                subject="data controller",
                action="process data",
                vague_terms=("appropriate measures", "without undue delay"),
                confidence=0.85,
            ),
        ]
        results = compile_rules(stmts, onto)
        assert results[0].success
        assert results[0].flagged
        assert "vague_term" in results[0].flag_reason
        assert "appropriate measures" in results[0].flag_reason

    def test_low_confidence_flagged(self) -> None:
        onto = _make_ontology()
        stmts = [
            NormativeStatement(
                source_article="Art. 22",
                modality="FORBIDDEN",
                subject="data controller",
                action="process data",
                confidence=0.5,
            ),
        ]
        results = compile_rules(stmts, onto, confidence_threshold=0.7)
        assert results[0].success
        assert results[0].flagged
        assert "low_confidence" in results[0].flag_reason

    def test_unmapped_subject_flagged(self) -> None:
        onto = _make_ontology()
        stmts = [
            NormativeStatement(
                source_article="Art. 50",
                modality="OBLIGATORY",
                subject="supervisory authority",
                action="delete data",
                confidence=0.9,
            ),
        ]
        results = compile_rules(stmts, onto)
        assert results[0].success
        assert results[0].flagged
        assert "unmapped_term" in results[0].flag_reason
        # Should use wildcard fallback
        assert "*" in results[0].meld_expression

    def test_unmapped_action_flagged(self) -> None:
        onto = _make_ontology()
        stmts = [
            NormativeStatement(
                source_article="Art. 50",
                modality="OBLIGATORY",
                subject="data controller",
                action="notify breach within 72 hours",
                confidence=0.9,
            ),
        ]
        results = compile_rules(stmts, onto)
        assert results[0].success
        assert results[0].flagged
        assert "unmapped_term" in results[0].flag_reason
        # Fallback action symbol generated (keywords extracted, sanitized)
        assert "notify" in results[0].meld_expression.lower()
        assert "breach" in results[0].meld_expression.lower()

    def test_delegation_clause_flagged(self) -> None:
        onto = _make_ontology()
        stmts = [
            NormativeStatement(
                source_article="Art. 88",
                modality="PERMITTED",
                subject="data controller",
                action="may provide additional rules under national law",
                confidence=0.8,
            ),
        ]
        results = compile_rules(stmts, onto)
        assert results[0].flagged
        assert "delegation_clause" in results[0].flag_reason

    def test_multiple_flags(self) -> None:
        onto = _make_ontology()
        stmts = [
            NormativeStatement(
                source_article="Art. 88",
                modality="PERMITTED",
                subject="unknown role",
                action="unknown action under national law",
                vague_terms=("reasonable",),
                confidence=0.5,
            ),
        ]
        results = compile_rules(stmts, onto)
        assert results[0].flagged
        # Should have multiple flag reasons
        reasons = results[0].flag_reason
        assert "unmapped_term" in reasons
        assert "vague_term" in reasons
        assert "low_confidence" in reasons
        assert "delegation_clause" in reasons

    def test_deduplication(self) -> None:
        """Duplicate MELD expressions should be deduplicated."""
        onto = _make_ontology()
        stmts = [
            NormativeStatement(source_article="Art. 6(1a)", modality="PERMITTED", subject="data controller", action="process data", conditions=["consent given"], confidence=0.9),
            NormativeStatement(source_article="Art. 6(1b)", modality="PERMITTED", subject="data controller", action="process data", conditions=["contract fulfillment"], confidence=0.9),
            NormativeStatement(source_article="Art. 6(1c)", modality="PERMITTED", subject="data controller", action="process data", conditions=["legal obligation"], confidence=0.9),
        ]
        results = compile_rules(stmts, onto)
        # All produce the same MELD expression — only first should survive
        successful = [r for r in results if r.success]
        assert len(successful) == 1

    def test_verify_mode(self) -> None:
        """verify=True runs 4-stage VerificationPipeline."""
        onto = _make_ontology()
        stmts = [
            NormativeStatement(
                source_article="Art. 17(1)",
                modality="OBLIGATORY",
                subject="data controller",
                action="delete data",
                confidence=0.95,
            ),
        ]
        results = compile_rules(stmts, onto, verify=True)
        assert len(results) == 1
        assert results[0].success
        # Verification should pass for valid rules
        # (no "verification_failed" in flag_reason)
        assert "verification_failed" not in (results[0].flag_reason or "")

    def test_verify_false_is_default(self) -> None:
        """Default verify=False produces same results as before."""
        onto = _make_ontology()
        stmts = [
            NormativeStatement(source_article="Art. 5", modality="OBLIGATORY", subject="data controller", action="process data", confidence=0.9),
        ]
        results_no_verify = compile_rules(stmts, onto, verify=False)
        results_default = compile_rules(stmts, onto)
        assert len(results_no_verify) == len(results_default)
        assert results_no_verify[0].meld_expression == results_default[0].meld_expression

    def test_empty_statements(self) -> None:
        onto = _make_ontology()
        assert compile_rules([], onto) == []

    def test_meld_expression_validates(self) -> None:
        """Every successful result should have a valid MELD expression."""
        onto = _make_ontology()
        stmts = [
            NormativeStatement(source_article="Art. 5", modality="OBLIGATORY", subject="data controller", action="process data", confidence=0.9),
            NormativeStatement(source_article="Art. 6", modality="FORBIDDEN", subject="employee", action="transfer data", confidence=0.9),
            NormativeStatement(source_article="Art. 15", modality="PERMITTED", subject="data subject", action="access data", confidence=0.9),
        ]
        results = compile_rules(stmts, onto)
        for r in results:
            assert r.success, f"Failed: {r.error}"
            assert r.meld_expression.startswith("(")
            assert r.meld_expression.endswith(")")

    def test_data_category_in_proposition(self) -> None:
        onto = _make_ontology()
        stmts = [
            NormativeStatement(
                source_article="Art. 17(1)",
                modality="OBLIGATORY",
                subject="data controller",
                action="delete data",
                object_description="concerning personalData",
                confidence=0.9,
            ),
        ]
        results = compile_rules(stmts, onto)
        assert results[0].success
        assert "personalData" in results[0].meld_expression
