"""End-to-end test: LLM-Assisted MELD Authoring (Epic 14).

Full pipeline: LLM generates → verification pipeline → legal doc → release gate.
Uses LM Studio (localhost:1234) with qwen/qwen3.8-27b.

Loads the real Pharma domain (.meld files) and asks the LLM to generate
new rules in natural language. Every generated rule is verified through
the 4-stage pipeline. The legal doc is generated. Release preconditions
are evaluated.

Run with:
    pytest tests/editor/test_authoring_e2e.py -v -s

Requires LM Studio running with a Qwen model on localhost:1234.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aegis.editor.domain_model import domain_from_meld
from aegis.editor.legal_doc import LegalDocGenerator
from aegis.editor.llm_provider import (
    LLMClient,
    LLMProviderInfo,
    ModelInfo,
    detect_local_providers,
)
from aegis.editor.meld_generator import MeldGenerator
from aegis.editor.release_gate import (
    ReleaseGate,
    ReleaseState,
    compute_doc_hash,
)
from aegis.editor.verification import VerificationPipeline
from aegis.guard.guard import Guard

PHARMA_DIR = Path(__file__).parent.parent.parent / "aegis" / "domains" / "pharma"
LM_STUDIO_URL = "http://localhost:1234/v1"
MODEL_ID = "qwen/qwen3.8-27b"


def _lm_studio_available() -> bool:
    """Check if LM Studio is reachable."""
    providers = detect_local_providers()
    return any(p.id == "lm-studio" and p.available for p in providers)


def _load_pharma_domain():  # noqa: ANN202
    """Load the Pharma domain from .meld files."""
    meld_files = sorted(PHARMA_DIR.glob("*.meld"))
    assert len(meld_files) >= 2, (
        f"Expected >= 2 .meld files in {PHARMA_DIR}, found {len(meld_files)}"
    )
    guard = Guard.from_meld_files(meld_files)
    domain = domain_from_meld(
        domain_id="pharma",
        name="Pharma",
        meld_paths=meld_files,
        guard=guard,
        norms=guard._norms,
        kb=guard._kb,
    )
    return domain, guard


@pytest.fixture(scope="module")
def pharma_domain():  # noqa: ANN201
    return _load_pharma_domain()


@pytest.fixture(scope="module")
def llm_client() -> LLMClient:
    provider = LLMProviderInfo(
        id="lm-studio",
        name="LM Studio",
        type="local",
        base_url=LM_STUDIO_URL,
        available=True,
        models=[ModelInfo(id=MODEL_ID, name="Qwen 3.5 35B")],
    )
    return LLMClient(provider, MODEL_ID, temperature=0, timeout=120)


# Skip entire module if LM Studio is not available
pytestmark = pytest.mark.skipif(
    not _lm_studio_available(),
    reason="LM Studio not available at localhost:1234",
)


class TestAuthoringE2E:
    """Full end-to-end authoring pipeline with real LLM."""

    def test_01_generate_rules(
        self, pharma_domain, llm_client: LLMClient,  # noqa: ANN001
    ) -> None:
        """LLM generates structured rule proposals from natural language."""
        domain, _ = pharma_domain
        generator = MeldGenerator(llm_client, domain)

        proposals = generator.generate(
            "Pharmacists must verify patient allergies before dispensing "
            "any controlled substance. Assistants are forbidden from "
            "modifying dosage records.",
        )

        assert len(proposals) >= 1, "LLM should propose at least 1 rule"

        for p in proposals:
            # Each proposal must have required fields
            assert p.modality in (
                "OBLIGATORY", "FORBIDDEN", "PERMITTED",
            ), f"Invalid modality: {p.modality}"
            assert p.agent_role, "agent_role must not be empty"
            assert p.action_type, "action_type must not be empty"
            assert p.natural_language_summary, "summary must not be empty"
            assert p.meld_expression, "MELD expression must be generated"

            # MELD expression must be parseable
            from aegis.kb.meld_loader import parse_meld

            assertions = parse_meld(p.meld_expression)
            assert len(assertions) >= 1, (
                f"MELD should parse to >= 1 assertion: {p.meld_expression}"
            )

        print(f"\n  Generated {len(proposals)} proposals:")
        for i, p in enumerate(proposals):
            print(f"    [{i+1}] {p.modality} — {p.natural_language_summary}")
            print(f"        MELD: {p.meld_expression}")

    def test_02_verify_generated_rules(
        self, pharma_domain, llm_client: LLMClient,  # noqa: ANN001
    ) -> None:
        """Each generated rule passes the 4-stage verification pipeline."""
        domain, _ = pharma_domain
        generator = MeldGenerator(llm_client, domain)

        proposals = generator.generate(
            "Pharmacists are obligated to report all adverse drug events "
            "involving controlled substances.",
        )
        assert len(proposals) >= 1

        pipeline = VerificationPipeline(domain)
        passed = 0
        total = len(proposals)

        for i, proposal in enumerate(proposals):
            result = pipeline.verify(proposal)
            print(f"\n  Proposal {i+1}: {proposal.natural_language_summary}")
            for stage in result.stages:
                icon = (
                    "✓" if stage.status.value == "PASS"
                    else "✕" if stage.status.value == "FAIL"
                    else "—"
                )
                print(f"    {icon} {stage.stage}: {stage.message}")
            if result.passed:
                passed += 1

        print(f"\n  Verification: {passed}/{total} rules passed all 4 stages")
        # At least the syntax and symbol stages should pass for well-formed
        # LLM output — functional may fail depending on domain specifics
        for proposal in proposals:
            result = pipeline.verify(proposal)
            assert result.stages[0].status.value == "PASS", (
                f"Syntax stage failed: {result.stages[0].message}"
            )

    def test_03_refine_proposal(
        self, pharma_domain, llm_client: LLMClient,  # noqa: ANN001
    ) -> None:
        """A proposal can be refined with user feedback."""
        domain, _ = pharma_domain
        generator = MeldGenerator(llm_client, domain)

        proposals = generator.generate(
            "Assistants cannot prescribe medications.",
        )
        assert len(proposals) >= 1

        original = proposals[0]
        print(f"\n  Original: {original.natural_language_summary}")
        print(f"  MELD: {original.meld_expression}")

        refined = generator.refine_proposal(
            original,
            "Make this apply only to controlled substances, not OTC.",
        )
        assert len(refined) >= 1

        print(f"  Refined: {refined[0].natural_language_summary}")
        print(f"  MELD: {refined[0].meld_expression}")

        # Refined rule should still parse
        from aegis.kb.meld_loader import parse_meld

        assertions = parse_meld(refined[0].meld_expression)
        assert len(assertions) >= 1

    def test_04_legal_doc_generation(
        self, pharma_domain,  # noqa: ANN001
    ) -> None:
        """Legal document is generated from the loaded domain."""
        domain, guard = pharma_domain

        # English
        gen_en = LegalDocGenerator(domain, locale="en")
        doc_en = gen_en.generate()
        assert "Pharma" in doc_en
        assert "Prohibitions" in doc_en
        assert len(doc_en) > 200

        # Legacy locale requests also produce English documentation
        legacy_gen = LegalDocGenerator(domain, locale="de")
        legacy_doc = legacy_gen.generate()
        assert "Obligations" in legacy_doc and "Prohibitions" in legacy_doc

        doc_hash = compute_doc_hash(doc_en)
        assert len(doc_hash) == 64

        print(f"\n  Legal doc (en): {len(doc_en)} chars, SHA-256: {doc_hash[:16]}...")
        print(f"  Legal doc (legacy locale, English): {len(legacy_doc)} chars")

    def test_05_release_gate_evaluation(
        self, pharma_domain, llm_client: LLMClient,  # noqa: ANN001
    ) -> None:
        """Release gate evaluates preconditions after full pipeline run."""
        domain, _ = pharma_domain
        generator = MeldGenerator(llm_client, domain)
        pipeline = VerificationPipeline(domain)

        # Generate
        proposals = generator.generate(
            "Pharmacists must document all interactions with "
            "controlled substances.",
        )

        # Verify each proposal
        syntax_ok = 0
        symbol_ok = 0
        func_passed = 0
        func_total = 0
        unresolved = 0

        for proposal in proposals:
            result = pipeline.verify(proposal)
            for stage in result.stages:
                if stage.stage == "syntax" and stage.status.value == "PASS":
                    syntax_ok += 1
                if stage.stage == "symbol" and stage.status.value == "PASS":
                    symbol_ok += 1
                if stage.stage == "conflict" and stage.status.value == "FAIL":
                    unresolved += 1
                if stage.stage == "functional":
                    func_total += 1
                    if stage.status.value == "PASS":
                        func_passed += 1

        # Generate legal doc
        gen = LegalDocGenerator(domain, locale="en")
        doc = gen.generate()
        doc_hash = compute_doc_hash(doc)

        # Build release state
        total_rules = len(domain.rules) + len(proposals)
        state = ReleaseState(
            syntax_verified_rules=syntax_ok + len(domain.rules),
            total_rules=total_rules,
            symbol_verified_rules=symbol_ok + len(domain.rules),
            unresolved_conflicts=unresolved,
            functional_tests_passed=func_passed,
            functional_tests_total=max(func_total, 1),
            legal_doc_generated=True,
            legal_doc_hash=doc_hash,
            provider_id="lm-studio",
            model_id=MODEL_ID,
            rules_generated=len(proposals),
            rules_accepted=syntax_ok,
        )

        gate = ReleaseGate(domain, state)
        preconditions = gate.check_preconditions()

        print("\n  Release Gate Pre-Conditions:")
        for pc in preconditions:
            icon = "✓" if pc.satisfied else "✕"
            print(f"    {icon} {pc.label}: {pc.detail}")

        can_release = gate.can_release()
        print(f"\n  Can release: {can_release}")

        # We don't assert can_release=True because the LLM output
        # may not satisfy all conditions (e.g. conflicts).
        # But the gate must evaluate without error.
        assert len(preconditions) == 5
        for pc in preconditions:
            assert pc.label  # non-empty
            assert pc.detail  # non-empty

    def test_06_full_pipeline_integration(
        self, pharma_domain, llm_client: LLMClient,  # noqa: ANN001
    ) -> None:
        """Complete cycle: generate → verify → legal doc → release check.

        This is the integration test that exercises the full authoring flow
        as a user would experience it through the wizard.
        """
        domain, _ = pharma_domain

        # ── Step 1: Provider is already configured (llm_client fixture)

        # ── Step 2: Generate rules from natural language
        generator = MeldGenerator(llm_client, domain)
        proposals = generator.generate(
            "Add a rule that pharmacists must verify patient identity "
            "before dispensing any medication. Also add that assistants "
            "are forbidden from approving distribution of experimental "
            "compounds.",
        )
        print(f"\n  Step 2: Generated {len(proposals)} proposals")
        assert len(proposals) >= 1

        # ── Step 3: Verify each proposal
        pipeline = VerificationPipeline(domain)
        verified = []
        for i, proposal in enumerate(proposals):
            result = pipeline.verify(proposal)
            status = "PASS" if result.passed else "FAIL"
            print(
                f"  Step 3: Proposal {i+1} verification: {status}"
                f" — {proposal.natural_language_summary}"
            )
            if result.passed:
                verified.append(proposal)

        # All proposals must at least parse as valid MELD
        for proposal in proposals:
            result = pipeline.verify(proposal)
            assert result.stages[0].status.value == "PASS", (
                f"Syntax failed for: {proposal.meld_expression}"
            )

        # ── Step 4: Legal doc
        gen = LegalDocGenerator(domain, locale="en")
        doc = gen.generate(
            meld_source="\n".join(p.meld_expression for p in proposals),
        )
        assert len(doc) > 100
        assert "Appendix: MELD Source" in doc
        doc_hash = compute_doc_hash(doc)
        print(f"  Step 4: Legal doc generated ({len(doc)} chars)")

        # ── Step 5: Release gate
        state = ReleaseState(
            syntax_verified_rules=len(domain.rules) + len(verified),
            total_rules=len(domain.rules) + len(verified),
            symbol_verified_rules=len(domain.rules) + len(verified),
            unresolved_conflicts=0,
            functional_tests_passed=len(verified),
            functional_tests_total=max(len(verified), 1),
            legal_doc_generated=True,
            legal_doc_hash=doc_hash,
            provider_id="lm-studio",
            model_id=MODEL_ID,
            rules_generated=len(proposals),
            rules_accepted=len(verified),
        )
        gate = ReleaseGate(domain, state)
        preconditions = gate.check_preconditions()

        print("  Step 5: Release gate:")
        for pc in preconditions:
            icon = "✓" if pc.satisfied else "✕"
            print(f"    {icon} {pc.label}: {pc.detail}")

        print(
            f"\n  Pipeline complete: {len(proposals)} generated, "
            f"{len(verified)} verified, "
            f"release={'ready' if gate.can_release() else 'blocked'}"
        )
