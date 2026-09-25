"""Tests for AEGIS-1406: Production Release Gate."""

from __future__ import annotations

import pytest

from aegis.editor.domain_model import DomainInfo, RuleInfo
from aegis.editor.release_gate import (
    PreConditionId,
    ReleaseGate,
    ReleaseState,
    compute_doc_hash,
)


@pytest.fixture()
def domain() -> DomainInfo:
    return DomainInfo(
        id="test",
        name="Test",
        rules=[
            RuleInfo(id="r1", code="C", agent_role="a", modality="FORBIDDEN", proposition="x"),
            RuleInfo(id="r2", code="C", agent_role="b", modality="PERMITTED", proposition="y"),
        ],
    )


@pytest.fixture()
def satisfied_state() -> ReleaseState:
    """A state where all preconditions are satisfied."""
    return ReleaseState(
        syntax_verified_rules=2,
        total_rules=2,
        symbol_verified_rules=2,
        unresolved_conflicts=0,
        functional_tests_passed=2,
        functional_tests_total=2,
        legal_doc_generated=True,
        legal_doc_hash="abc123",
        provider_id="lm-studio",
        model_id="qwen-35b",
        rules_generated=5,
        rules_accepted=2,
    )


@pytest.fixture()
def unsatisfied_state() -> ReleaseState:
    """A state where some preconditions are NOT satisfied."""
    return ReleaseState(
        syntax_verified_rules=1,
        total_rules=2,
        symbol_verified_rules=1,
        unresolved_conflicts=1,
        functional_tests_passed=1,
        functional_tests_total=2,
        legal_doc_generated=False,
    )


class TestCheckPreconditions:
    def test_all_satisfied(self, domain: DomainInfo, satisfied_state: ReleaseState) -> None:
        gate = ReleaseGate(domain, satisfied_state)
        pcs = gate.check_preconditions()
        assert len(pcs) == 5
        assert all(pc.satisfied for pc in pcs)

    def test_some_unsatisfied(
        self, domain: DomainInfo, unsatisfied_state: ReleaseState,
    ) -> None:
        gate = ReleaseGate(domain, unsatisfied_state)
        pcs = gate.check_preconditions()
        unsatisfied_ids = {pc.id for pc in pcs if not pc.satisfied}
        assert PreConditionId.ALL_CONFLICTS_RESOLVED in unsatisfied_ids
        assert PreConditionId.LEGAL_DOC_GENERATED in unsatisfied_ids

    def test_precondition_details(self, domain: DomainInfo, satisfied_state: ReleaseState) -> None:
        gate = ReleaseGate(domain, satisfied_state)
        pcs = gate.check_preconditions()
        for pc in pcs:
            assert pc.label  # non-empty label
            assert pc.detail  # non-empty detail


class TestCanRelease:
    def test_can_release_when_satisfied(
        self, domain: DomainInfo, satisfied_state: ReleaseState,
    ) -> None:
        gate = ReleaseGate(domain, satisfied_state)
        assert gate.can_release() is True

    def test_cannot_release_when_unsatisfied(
        self, domain: DomainInfo, unsatisfied_state: ReleaseState,
    ) -> None:
        gate = ReleaseGate(domain, unsatisfied_state)
        assert gate.can_release() is False

    def test_cannot_release_empty_domain(self) -> None:
        domain = DomainInfo(id="empty", name="Empty")
        state = ReleaseState()
        gate = ReleaseGate(domain, state)
        assert gate.can_release() is False


class TestPreconditionToDict:
    def test_to_dict(self, domain: DomainInfo, satisfied_state: ReleaseState) -> None:
        gate = ReleaseGate(domain, satisfied_state)
        pcs = gate.check_preconditions()
        for pc in pcs:
            d = pc.to_dict()
            assert "id" in d
            assert "label" in d
            assert "satisfied" in d
            assert "detail" in d
            assert isinstance(d["id"], str)


class TestComputeDocHash:
    def test_deterministic(self) -> None:
        h1 = compute_doc_hash("test content")
        h2 = compute_doc_hash("test content")
        assert h1 == h2

    def test_different_content_different_hash(self) -> None:
        h1 = compute_doc_hash("content A")
        h2 = compute_doc_hash("content B")
        assert h1 != h2

    def test_returns_hex_string(self) -> None:
        h = compute_doc_hash("test")
        assert len(h) == 64  # SHA-256 hex digest
        assert all(c in "0123456789abcdef" for c in h)


class TestReleaseGateRelease:
    def test_release_fails_if_not_ready(
        self, domain: DomainInfo, unsatisfied_state: ReleaseState,
    ) -> None:
        gate = ReleaseGate(domain, unsatisfied_state)
        import tempfile
        from pathlib import Path

        from aegis.editor.governance import GovernanceManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = GovernanceManager(repo_path=Path(tmpdir))
            result = gate.release(
                governance=mgr,
                output_dir=Path(tmpdir) / "test",
                version="1.0.0",
            )
            assert result.success is False
            assert "not met" in result.error
