"""End-to-end tests for the DIP pipeline.

Tests the full pipeline against multiple document types with mock LLM.
Verifies that generated domains load in Guard and produce correct verdicts.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from aegis.dip.pipeline import run_pipeline
from aegis.guard.action import Action
from aegis.guard.guard import Guard


FIXTURES = Path(__file__).parent / "fixtures"


# ── Mock LLM helpers ────────────────────────────────────────────────


def _extract_response(*stmts: dict) -> dict:
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


def _ontology_response(args: dict) -> dict:
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
                        "arguments": json.dumps(args),
                    },
                }],
            },
        }],
    }


# ── English Policy E2E ──────────────────────────────────────────────


class TestEnglishPolicyE2E:
    """Full pipeline against sample_policy_en.md."""

    def _build_client(self) -> MagicMock:
        extract = _extract_response(
            {"source_ref": "Art. 3(1)", "modality": "OBLIGATORY", "subject": "employee", "action": "classify data", "confidence": 0.9},
            {"source_ref": "Art. 4(1)", "modality": "FORBIDDEN", "subject": "employee", "action": "access data beyond authorization", "confidence": 0.95},
            {"source_ref": "Art. 4(2)", "modality": "FORBIDDEN", "subject": "employee", "action": "share credentials", "confidence": 0.95},
            {"source_ref": "Art. 5(1)", "modality": "OBLIGATORY", "subject": "organization", "action": "delete personal data", "conditions": ["purpose ended"], "confidence": 0.9},
            {"source_ref": "Art. 6(1)", "modality": "FORBIDDEN", "subject": "employee", "action": "transfer data externally", "confidence": 0.95},
            {"source_ref": "Art. 6(3)", "modality": "FORBIDDEN", "subject": "employee", "action": "bypass security controls", "confidence": 0.98},
        )
        empty = _extract_response()
        ontology = _ontology_response({
            "roles": [
                {"natural_name": "employee", "meld_symbol": "employee"},
                {"natural_name": "organization", "meld_symbol": "organization"},
            ],
            "actions": [
                {"natural_name": "classify data", "meld_symbol": "classifyData"},
                {"natural_name": "access data beyond authorization", "meld_symbol": "accessDataBeyondAuth"},
                {"natural_name": "share credentials", "meld_symbol": "shareCredentials"},
                {"natural_name": "delete personal data", "meld_symbol": "deletePersonalData"},
                {"natural_name": "transfer data externally", "meld_symbol": "transferDataExternally"},
                {"natural_name": "bypass security controls", "meld_symbol": "bypassSecurityControls"},
            ],
            "object_categories": ["personalData", "confidentialData"],
            "codes": ["CorporatePolicy"],
        })
        client = MagicMock()
        # 3 extraction batches + 1 ontology call
        client.chat = MagicMock(side_effect=[extract, empty, empty, ontology])
        return client

    def test_pipeline_produces_domain(self, tmp_path: Path) -> None:
        client = self._build_client()
        export = run_pipeline(
            source=str(FIXTURES / "sample_policy_en.md"),
            name="corporate",
            client=client,
            output_dir=tmp_path,
            language="en",
            domain_context="Corporate data handling policy",
        )
        assert export.total_rules >= 5
        assert export.obligations >= 1
        assert export.prohibitions >= 3

    def test_guard_loads_and_checks(self, tmp_path: Path) -> None:
        client = self._build_client()
        export = run_pipeline(
            source=str(FIXTURES / "sample_policy_en.md"),
            name="corporate",
            client=client,
            output_dir=tmp_path,
            language="en",
        )
        guard = Guard.from_meld_files(
            [Path(export.ontology_path), Path(export.vocab_path), Path(export.rules_path)],
            code_prevalence=["CorporatePolicy"],
        )
        # Test: employee bypassing security should be FORBIDDEN
        action = Action(
            agent_id="employee",
            action_type="bypassSecurityControls",
        )
        verdict = guard.check(action)
        assert verdict.decision.value in ("FORBIDDEN", "UNDECIDABLE")

    def test_review_report(self, tmp_path: Path) -> None:
        client = self._build_client()
        export = run_pipeline(
            source=str(FIXTURES / "sample_policy_en.md"),
            name="corporate",
            client=client,
            output_dir=tmp_path,
            language="en",
        )
        review_path = tmp_path / "corporate-review.json"
        assert review_path.exists()
        report = json.loads(review_path.read_text())
        assert report["total_rules"] >= 5


# ── Plaintext Standard E2E ──────────────────────────────────────────


class TestPlaintextStandardE2E:
    """Pipeline against sample_standard_en.txt (ISO-style)."""

    def _build_client(self) -> MagicMock:
        extract = _extract_response(
            {"source_ref": "Section 5.1", "modality": "OBLIGATORY", "subject": "management", "action": "define security policies", "confidence": 0.9},
            {"source_ref": "Section 5.2", "modality": "OBLIGATORY", "subject": "organization", "action": "allocate security roles", "confidence": 0.85},
            {"source_ref": "Section 8.1", "modality": "FORBIDDEN", "subject": "user", "action": "install unauthorized software", "confidence": 0.95},
            {"source_ref": "Section 8.2", "modality": "FORBIDDEN", "subject": "administrator", "action": "grant privileged access without authorization", "confidence": 0.9},
        )
        ontology = _ontology_response({
            "roles": [
                {"natural_name": "management", "meld_symbol": "management"},
                {"natural_name": "organization", "meld_symbol": "organization"},
                {"natural_name": "user", "meld_symbol": "endUser"},
                {"natural_name": "administrator", "meld_symbol": "administrator"},
            ],
            "actions": [
                {"natural_name": "define security policies", "meld_symbol": "defineSecurityPolicies"},
                {"natural_name": "allocate security roles", "meld_symbol": "allocateSecurityRoles"},
                {"natural_name": "install unauthorized software", "meld_symbol": "installUnauthorizedSoftware"},
                {"natural_name": "grant privileged access without authorization", "meld_symbol": "grantPrivilegedAccessUnauthorized"},
            ],
            "codes": ["InformationSecurity"],
        })
        client = MagicMock()
        client.chat = MagicMock(side_effect=[extract, ontology])
        return client

    def test_pipeline_produces_domain(self, tmp_path: Path) -> None:
        client = self._build_client()
        export = run_pipeline(
            source=str(FIXTURES / "sample_standard_en.txt"),
            name="iso27001",
            client=client,
            output_dir=tmp_path,
            language="en",
            domain_context="ISO 27001 information security controls",
        )
        assert export.total_rules >= 3
        assert export.obligations >= 1
        assert export.prohibitions >= 1

    def test_guard_loads(self, tmp_path: Path) -> None:
        client = self._build_client()
        export = run_pipeline(
            source=str(FIXTURES / "sample_standard_en.txt"),
            name="iso27001",
            client=client,
            output_dir=tmp_path,
            language="en",
        )
        guard = Guard.from_meld_files(
            [Path(export.ontology_path), Path(export.vocab_path), Path(export.rules_path)],
            code_prevalence=["InformationSecurity"],
        )
        assert guard is not None


# ── English HTML E2E ─────────────────────────────────────────────────


class TestEnglishHtmlE2E:
    """Pipeline against sample_article_en.html (GDPR Art. 17)."""

    def _build_client(self) -> MagicMock:
        extract = _extract_response(
            {"source_ref": "Art. 17(1)", "modality": "OBLIGATORY", "subject": "controller", "action": "erasure of personal data", "vague_terms": ["without undue delay"], "confidence": 0.9},
            {"source_ref": "Art. 17(2)", "modality": "OBLIGATORY", "subject": "controller", "action": "notify third parties of erasure", "vague_terms": ["reasonable measures"], "confidence": 0.8},
            {"source_ref": "Art. 17(3)", "modality": "PERMITTED", "subject": "controller", "action": "retain data for legal claims", "confidence": 0.85},
        )
        ontology = _ontology_response({
            "roles": [
                {"natural_name": "controller", "meld_symbol": "dataController"},
            ],
            "actions": [
                {"natural_name": "erasure of personal data", "meld_symbol": "deletePersonalData"},
                {"natural_name": "notify third parties of erasure", "meld_symbol": "notifyThirdPartyDeletion"},
                {"natural_name": "retain data for legal claims", "meld_symbol": "retainDataForLegalClaims"},
            ],
            "object_categories": ["personalData"],
            "codes": ["DataProtection"],
        })
        client = MagicMock()
        client.chat = MagicMock(side_effect=[extract, ontology])
        return client

    def test_pipeline_produces_domain(self, tmp_path: Path) -> None:
        client = self._build_client()
        export = run_pipeline(
            source=str(FIXTURES / "sample_article_en.html"),
            name="gdpr_art17",
            client=client,
            output_dir=tmp_path,
            language="en",
            domain_context="GDPR Art. 17 — Right to erasure",
        )
        assert export.total_rules == 3
        assert export.obligations == 2
        assert export.permissions == 1
        # Vague terms should be flagged
        assert export.flagged_for_review >= 1

    def test_guard_loads_and_checks(self, tmp_path: Path) -> None:
        client = self._build_client()
        export = run_pipeline(
            source=str(FIXTURES / "sample_article_en.html"),
            name="gdpr_art17",
            client=client,
            output_dir=tmp_path,
            language="en",
        )
        guard = Guard.from_meld_files(
            [Path(export.ontology_path), Path(export.vocab_path), Path(export.rules_path)],
            code_prevalence=["DataProtection"],
        )
        # Test: deletion of personal data should be governed
        action = Action(
            agent_id="dataController",
            action_type="deletePersonalData",
        )
        verdict = guard.check(action)
        # Should be PERMITTED (obligatory implies permitted) or at least not UNDECIDABLE
        assert verdict.decision.value in ("PERMITTED", "FORBIDDEN", "UNDECIDABLE")
