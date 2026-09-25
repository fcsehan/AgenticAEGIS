"""Tests for DIP pipeline orchestrator."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from aegis.dip.pipeline import run_pipeline


def _mock_extract_response(*stmts: dict) -> dict:
    """Mock LLM response for extractor."""
    return {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": f"c{i}",
                        "type": "function",
                        "function": {
                            "name": "extract_normative_statement",
                            "arguments": json.dumps(s),
                        },
                    }
                    for i, s in enumerate(stmts)
                ],
            },
        }],
    }


def _mock_ontology_response() -> dict:
    """Mock LLM response for ontology builder."""
    return {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "o0",
                    "type": "function",
                    "function": {
                        "name": "define_ontology",
                        "arguments": json.dumps({
                            "roles": [
                                {"natural_name": "employee", "meld_symbol": "employee"},
                                {"natural_name": "IT department", "meld_symbol": "itDepartment"},
                                {"natural_name": "CISO", "meld_symbol": "ciso"},
                            ],
                            "actions": [
                                {"natural_name": "classify data", "meld_symbol": "classifyData"},
                                {"natural_name": "access data", "meld_symbol": "accessData"},
                                {"natural_name": "delete data", "meld_symbol": "deleteData", "parameters": ["dataCategory"]},
                                {"natural_name": "transfer data", "meld_symbol": "transferData", "parameters": ["destination"]},
                                {"natural_name": "share credentials", "meld_symbol": "shareCredentials"},
                                {"natural_name": "bypass security", "meld_symbol": "bypassSecurity"},
                                {"natural_name": "grant emergency access", "meld_symbol": "grantEmergencyAccess"},
                            ],
                            "object_categories": ["confidentialData", "personalData", "internalData"],
                            "role_hierarchy": [{"child": "ciso", "parent": "itDepartment"}],
                            "codes": ["CorporatePolicy"],
                        }),
                    },
                }],
            },
        }],
    }


FIXTURES = Path(__file__).parent / "fixtures"


class TestRunPipeline:
    def _mock_client(self) -> MagicMock:
        """Build a mock LLM client that returns extraction + ontology responses."""
        extract_resp = _mock_extract_response(
            {"source_ref": "Art. 3(1)", "modality": "OBLIGATORY", "subject": "employee", "action": "classify data", "confidence": 0.9},
            {"source_ref": "Art. 4(1)", "modality": "FORBIDDEN", "subject": "employee", "action": "access data", "conditions": ["beyond authorization"], "confidence": 0.95},
            {"source_ref": "Art. 5(1)", "modality": "OBLIGATORY", "subject": "employee", "action": "delete data", "object_description": "personalData within 30 days", "confidence": 0.9},
            {"source_ref": "Art. 6(1)", "modality": "FORBIDDEN", "subject": "employee", "action": "transfer data", "confidence": 0.95},
            {"source_ref": "Art. 6(2)", "modality": "FORBIDDEN", "subject": "employee", "action": "bypass security", "confidence": 0.95},
        )
        # Empty extraction for additional batches
        empty_extract = _mock_extract_response()
        ontology_resp = _mock_ontology_response()
        client = MagicMock()
        # 3 extraction batches (15 chunks / 5 per batch) + 1 ontology call
        client.chat = MagicMock(side_effect=[extract_resp, empty_extract, empty_extract, ontology_resp])
        return client

    def test_full_pipeline(self, tmp_path: Path) -> None:
        client = self._mock_client()
        export = run_pipeline(
            source=str(FIXTURES / "sample_policy_en.md"),
            name="test_policy",
            client=client,
            output_dir=tmp_path,
            language="en",
        )
        assert export.total_rules > 0
        assert export.domain_name == "test_policy"
        assert (tmp_path / "TestPolicyDomainOntologyMt.meld").exists()
        assert (tmp_path / "TestPolicyActionVocabMt.meld").exists()
        assert (tmp_path / "TestPolicyDeonticRulesMt.meld").exists()
        assert (tmp_path / "test_policy-review.json").exists()

    def test_dry_run(self, tmp_path: Path) -> None:
        client = self._mock_client()
        export = run_pipeline(
            source=str(FIXTURES / "sample_policy_en.md"),
            name="dry",
            client=client,
            output_dir=tmp_path,
            language="en",
            dry_run=True,
        )
        assert export.total_rules > 0
        assert not (tmp_path / "DryDomainOntologyMt.meld").exists()

    def test_progress_callback(self, tmp_path: Path) -> None:
        client = self._mock_client()
        stages_seen: list[int] = []
        export = run_pipeline(
            source=str(FIXTURES / "sample_policy_en.md"),
            name="prog",
            client=client,
            output_dir=tmp_path,
            language="en",
            on_progress=lambda s, m: stages_seen.append(s),
        )
        # Should see stages 1-6
        assert 1 in stages_seen
        assert 2 in stages_seen
        assert 3 in stages_seen
        assert 4 in stages_seen
        assert 5 in stages_seen
        assert 6 in stages_seen

    def test_guard_loads_generated_domain(self, tmp_path: Path) -> None:
        """Generated domain should load via Guard.from_meld_files()."""
        client = self._mock_client()
        export = run_pipeline(
            source=str(FIXTURES / "sample_policy_en.md"),
            name="guard_test",
            client=client,
            output_dir=tmp_path,
            language="en",
        )
        from aegis.guard.guard import Guard
        paths = [
            Path(export.ontology_path),
            Path(export.vocab_path),
            Path(export.rules_path),
        ]
        guard = Guard.from_meld_files(paths, code_prevalence=["CorporatePolicy"])
        assert guard is not None
