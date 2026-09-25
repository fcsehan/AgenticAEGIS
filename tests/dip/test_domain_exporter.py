"""Tests for DIP domain exporter — 3 MELD files + review report."""

import json
from pathlib import Path

from aegis.dip.domain_exporter import export_domain
from aegis.dip.models import (
    CompilationResult,
    DomainOntology,
    OntologyAction,
    OntologyRole,
)


def _make_ontology() -> DomainOntology:
    return DomainOntology(
        roles=(
            OntologyRole("data controller", "dataController"),
            OntologyRole("data subject", "dataSubject"),
        ),
        actions=(
            OntologyAction("delete data", "deleteData", parameters=("dataCategory",)),
            OntologyAction("process data", "processData", parameters=("legalBasis",)),
        ),
        data_categories=("personalData", "medicalData"),
        role_hierarchy=(("dataProtectionOfficer", "dataController"),),
        codes=("DataProtection",),
        role_map={"data controller": "dataController", "data subject": "dataSubject"},
        action_map={"delete data": "deleteData", "process data": "processData"},
    )


def _make_results() -> list[CompilationResult]:
    return [
        CompilationResult(
            source_article="Art. 17(1)",
            success=True,
            meld_expression="(oughtToDo-WRT DataProtection dataController (deleteData))",
        ),
        CompilationResult(
            source_article="Art. 6(1)",
            success=True,
            meld_expression="(forbiddenToDo-WRT DataProtection dataController (processData))",
        ),
        CompilationResult(
            source_article="Art. 15(1)",
            success=True,
            meld_expression="(permittedToDo-WRT DataProtection dataSubject (accessData))",
        ),
        CompilationResult(
            source_article="Art. 32",
            success=True,
            meld_expression="(oughtToDo-WRT DataProtection dataController (processData))",
            flagged=True,
            flag_reason="vague_term: appropriate measures",
        ),
        CompilationResult(
            source_article="Art. 88",
            success=False,
            error="Unmapped action",
        ),
    ]


class TestExportDomain:
    def test_creates_three_meld_files(self, tmp_path: Path) -> None:
        onto = _make_ontology()
        results = _make_results()
        export = export_domain("test_domain", onto, results, tmp_path)

        assert (tmp_path / "TestDomainDomainOntologyMt.meld").exists()
        assert (tmp_path / "TestDomainActionVocabMt.meld").exists()
        assert (tmp_path / "TestDomainDeonticRulesMt.meld").exists()

    def test_creates_review_report(self, tmp_path: Path) -> None:
        onto = _make_ontology()
        results = _make_results()
        export_domain("test_domain", onto, results, tmp_path)

        review_path = tmp_path / "test_domain-review.json"
        assert review_path.exists()
        report = json.loads(review_path.read_text())
        assert report["domain"] == "test_domain"
        assert report["total_rules"] == 4  # 4 successful
        assert report["flagged_for_review"] == 1
        assert report["flagged_reasons"]["vague_term"] == 1

    def test_ontology_content(self, tmp_path: Path) -> None:
        onto = _make_ontology()
        results = _make_results()
        export_domain("test_domain", onto, results, tmp_path)

        content = (tmp_path / "TestDomainDomainOntologyMt.meld").read_text()
        assert "(aegis-schema-version 1)" in content
        assert "(case TestDomainDomainOntologyMt)" in content
        assert "(isa dataController TestDomainRole)" in content
        assert "(isa dataSubject TestDomainRole)" in content
        assert "(genls TestDomainRole IntelligentAgent)" in content
        assert "(genls dataProtectionOfficer dataController)" in content
        assert "(isa personalData DataCategory)" in content
        assert "(negationPreds oughtToDo forbiddenToDo)" in content

    def test_action_vocab_content(self, tmp_path: Path) -> None:
        onto = _make_ontology()
        results = _make_results()
        export_domain("test_domain", onto, results, tmp_path)

        content = (tmp_path / "TestDomainActionVocabMt.meld").read_text()
        assert "(aegis-schema-version 1)" in content
        assert "(case TestDomainActionVocabMt)" in content
        assert "(isa deleteData ActionType)" in content
        assert "(isa processData ActionType)" in content
        assert "(actionParameter deleteData dataCategory Thing)" in content

    def test_deontic_rules_content(self, tmp_path: Path) -> None:
        onto = _make_ontology()
        results = _make_results()
        export_domain("test_domain", onto, results, tmp_path)

        content = (tmp_path / "TestDomainDeonticRulesMt.meld").read_text()
        assert "(aegis-schema-version 1)" in content
        assert "(case TestDomainDeonticRulesMt)" in content
        assert "(oughtToDo-WRT DataProtection dataController (deleteData))" in content
        assert "(forbiddenToDo-WRT DataProtection dataController (processData))" in content
        # Flagged rules should have a comment
        assert "[FLAGGED:" in content

    def test_export_statistics(self, tmp_path: Path) -> None:
        onto = _make_ontology()
        results = _make_results()
        export = export_domain("test_domain", onto, results, tmp_path)

        assert export.domain_name == "test_domain"
        assert export.total_rules == 4
        assert export.auto_generated == 3  # 4 successful - 1 flagged
        assert export.flagged_for_review == 1
        assert export.obligations == 2  # Art 17 + Art 32
        assert export.prohibitions == 1  # Art 6
        assert export.permissions == 1  # Art 15
        assert export.articles_processed == 5  # 5 unique articles

    def test_summary(self, tmp_path: Path) -> None:
        onto = _make_ontology()
        results = _make_results()
        export = export_domain("test_domain", onto, results, tmp_path)

        s = export.summary()
        assert "4 rules" in s
        assert "3 auto-generated" in s
        assert "1 flagged" in s

    def test_empty_results(self, tmp_path: Path) -> None:
        onto = _make_ontology()
        export = export_domain("empty", onto, [], tmp_path)

        assert export.total_rules == 0
        assert (tmp_path / "EmptyDomainOntologyMt.meld").exists()
        assert (tmp_path / "EmptyActionVocabMt.meld").exists()
        assert (tmp_path / "EmptyDeonticRulesMt.meld").exists()

    def test_guard_loadable(self, tmp_path: Path) -> None:
        """Generated MELD files should load via Guard.from_meld_files()."""
        onto = _make_ontology()
        results = [
            CompilationResult(
                source_article="Art. 17(1)",
                success=True,
                meld_expression="(oughtToDo-WRT DataProtection dataController (deleteData))",
            ),
            CompilationResult(
                source_article="Art. 6(1)",
                success=True,
                meld_expression="(forbiddenToDo-WRT DataProtection dataController (processData))",
            ),
        ]
        export = export_domain("loadtest", onto, results, tmp_path)

        from aegis.guard.guard import Guard
        paths = [
            Path(export.ontology_path),
            Path(export.vocab_path),
            Path(export.rules_path),
        ]
        guard = Guard.from_meld_files(paths, code_prevalence=["DataProtection"])
        assert guard is not None

    def test_review_flags_detail(self, tmp_path: Path) -> None:
        onto = _make_ontology()
        results = [
            CompilationResult(
                source_article="Art. 32",
                success=True,
                meld_expression="(oughtToDo-WRT DataProtection dataController (processData))",
                flagged=True,
                flag_reason="vague_term: appropriate; low_confidence: 0.55",
            ),
        ]
        export = export_domain("flags", onto, results, tmp_path)
        assert len(export.flags) == 2
        reasons = {f.reason for f in export.flags}
        assert "vague_term" in reasons
        assert "low_confidence" in reasons
