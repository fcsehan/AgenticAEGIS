"""Tests for AEGIS-1708: IFC Host Integration Rules."""

from __future__ import annotations

from pathlib import Path

from aegis.ifc.host_contract import IFCHostContract, check_ifc_contracts
from aegis.redteam.tools import WorkspaceFileRuntime


def _make_entry(path: str, classification: str) -> WorkspaceFileRuntime:
    return WorkspaceFileRuntime(
        relative_path=path,
        absolute_path=Path(f"/tmp/{path}"),
        classification=classification,
        description="test",
        canary_tokens=(),
    )


class TestHC005BrokerConfigured:
    def test_violation_when_broker_not_configured(self) -> None:
        contract = IFCHostContract(contract_id="test", mandatory_broker=True)
        violations = check_ifc_contracts(
            contract, {}, broker_configured=False,
        )
        codes = [v.code for v in violations]
        assert "HC-005" in codes

    def test_passes_when_broker_configured(self) -> None:
        contract = IFCHostContract(contract_id="test", mandatory_broker=True)
        violations = check_ifc_contracts(
            contract, {}, broker_configured=True,
        )
        codes = [v.code for v in violations]
        assert "HC-005" not in codes

    def test_optional_broker_no_violation(self) -> None:
        contract = IFCHostContract(contract_id="test", mandatory_broker=False)
        violations = check_ifc_contracts(
            contract, {}, broker_configured=False,
        )
        codes = [v.code for v in violations]
        assert "HC-005" not in codes


class TestHC006RawClassifiedReads:
    def test_violation_with_classified_files_no_broker(self) -> None:
        contract = IFCHostContract(contract_id="test")
        files = {
            "secret.txt": _make_entry("secret.txt", "secret"),
            "public.txt": _make_entry("public.txt", "public"),
        }
        violations = check_ifc_contracts(
            contract, files, broker_configured=False,
            tool_suite_tools=["read_workspace_file"],
        )
        codes = [v.code for v in violations]
        assert "HC-006" in codes

    def test_no_violation_when_all_public(self) -> None:
        contract = IFCHostContract(contract_id="test")
        files = {
            "a.txt": _make_entry("a.txt", "public"),
            "b.txt": _make_entry("b.txt", "public"),
        }
        violations = check_ifc_contracts(
            contract, files, broker_configured=False,
            tool_suite_tools=["read_workspace_file"],
        )
        codes = [v.code for v in violations]
        assert "HC-006" not in codes

    def test_no_violation_with_broker(self) -> None:
        contract = IFCHostContract(contract_id="test")
        files = {
            "secret.txt": _make_entry("secret.txt", "secret"),
        }
        violations = check_ifc_contracts(
            contract, files, broker_configured=True,
        )
        codes = [v.code for v in violations]
        assert "HC-006" not in codes


class TestHC007ClassificationRequired:
    def test_violation_for_unclassified_files(self) -> None:
        contract = IFCHostContract(contract_id="test", classification_required=True)
        files = {
            "good.txt": _make_entry("good.txt", "public"),
            "bad.txt": _make_entry("bad.txt", ""),
        }
        violations = check_ifc_contracts(
            contract, files, broker_configured=True,
        )
        codes = [v.code for v in violations]
        assert "HC-007" in codes

    def test_passes_when_all_classified(self) -> None:
        contract = IFCHostContract(contract_id="test", classification_required=True)
        files = {
            "a.txt": _make_entry("a.txt", "public"),
            "b.txt": _make_entry("b.txt", "secret"),
        }
        violations = check_ifc_contracts(
            contract, files, broker_configured=True,
        )
        codes = [v.code for v in violations]
        assert "HC-007" not in codes


class TestHC008RecipientConstraints:
    def test_violation_for_empty_allowed_levels(self) -> None:
        contract = IFCHostContract(
            contract_id="test",
            recipient_constraints={"externalService": ()},
        )
        violations = check_ifc_contracts(
            contract, {}, broker_configured=True,
        )
        codes = [v.code for v in violations]
        assert "HC-008" in codes

    def test_passes_with_proper_constraints(self) -> None:
        contract = IFCHostContract(
            contract_id="test",
            recipient_constraints={"externalService": ("public",)},
        )
        violations = check_ifc_contracts(
            contract, {}, broker_configured=True,
        )
        codes = [v.code for v in violations]
        assert "HC-008" not in codes


class TestHC010ChannelMappingRequired:
    """AEGIS-1805: every registered channel must have a Channel-to-
    Action mapping; HC-010 catches gaps."""

    def test_currently_no_unmapped_channels(self) -> None:
        """Per AEGIS-1802 every channel is mapped. The contract test
        passes by construction today; if a future channel is added
        without a mapping the test (and HC-010) catches it."""
        contract = IFCHostContract(contract_id="test")
        violations = check_ifc_contracts(
            contract, {}, broker_configured=True,
        )
        codes = [v.code for v in violations]
        assert "HC-010" not in codes


class TestHC011BrokerMediation:
    """AEGIS-1805: requires_broker channels must declare BROKER mediation."""

    def test_no_violation_under_default_registry(self) -> None:
        """All current broker-required channels declare BROKER
        mediation by construction (verified by
        test_broker_mediated_implies_requires_broker in the registry
        test suite). HC-011 is silent here but ready to catch a
        regression if a future commit drifts the two fields apart."""
        contract = IFCHostContract(contract_id="test")
        violations = check_ifc_contracts(
            contract, {}, broker_configured=True,
        )
        codes = [v.code for v in violations]
        assert "HC-011" not in codes


class TestHC012GuardInterposition:
    def test_no_violation_under_default_registry(self) -> None:
        contract = IFCHostContract(contract_id="test")
        violations = check_ifc_contracts(
            contract, {}, broker_configured=True,
        )
        codes = [v.code for v in violations]
        assert "HC-012" not in codes


class TestReleaseGate:
    def test_critical_violation_blocks_release(self) -> None:
        from aegis.ifc.host_contract import (
            IFCContractViolation,
            evaluate_release_gate,
        )
        violations = [
            IFCContractViolation(
                code="HC-X", severity="critical", message="x",
            ),
        ]
        result = evaluate_release_gate(violations)
        assert result.release_blocked is True
        assert result.exit_code() == 1
        assert result.critical_count == 1

    def test_high_only_does_not_block(self) -> None:
        from aegis.ifc.host_contract import (
            IFCContractViolation,
            evaluate_release_gate,
        )
        violations = [
            IFCContractViolation(
                code="HC-Y", severity="high", message="y",
            ),
        ]
        result = evaluate_release_gate(violations)
        assert result.release_blocked is False
        assert result.exit_code() == 0
        assert result.high_count == 1

    def test_empty_violations(self) -> None:
        from aegis.ifc.host_contract import evaluate_release_gate

        result = evaluate_release_gate([])
        assert result.release_blocked is False
        assert result.exit_code() == 0
        assert result.critical_count == 0
        assert "Release-gate OK" in result.summary()

    def test_summary_message_blocked(self) -> None:
        from aegis.ifc.host_contract import (
            IFCContractViolation,
            evaluate_release_gate,
        )
        violations = [
            IFCContractViolation(
                code="HC-X", severity="critical", message="x",
            ),
            IFCContractViolation(
                code="HC-Y", severity="high", message="y",
            ),
        ]
        result = evaluate_release_gate(violations)
        assert "RELEASE BLOCKED" in result.summary()
        assert "1 critical" in result.summary()
        assert "1 high" in result.summary()

    def test_severity_counts(self) -> None:
        from aegis.ifc.host_contract import (
            IFCContractViolation,
            evaluate_release_gate,
        )
        violations = [
            IFCContractViolation(code="A", severity="critical", message=""),
            IFCContractViolation(code="B", severity="critical", message=""),
            IFCContractViolation(code="C", severity="high", message=""),
            IFCContractViolation(code="D", severity="medium", message=""),
            IFCContractViolation(code="E", severity="medium", message=""),
            IFCContractViolation(code="F", severity="medium", message=""),
        ]
        result = evaluate_release_gate(violations)
        assert result.critical_count == 2
        assert result.high_count == 1
        assert result.medium_count == 3
        assert result.release_blocked is True
