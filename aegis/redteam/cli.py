"""CLI entry point for the AEGIS red-team pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aegis.guard.guard import Guard
from aegis.redteam.models import (
    AttemptResult,
    Finding,
    RedTeamReport,
    RedTeamScenario,
    ScenarioResult,
)
from aegis.redteam.pipeline import OpenAICompatibleLLMClient, RedTeamPipeline
from aegis.redteam.scenario_loader import load_scenario_library
from aegis.redteam.scenarios import DEFAULT_DOMAIN_DIR, DEFAULT_MODEL, build_default_scenarios

# ── Shared helpers ───────────────────────────────────────────


def _build_guard(domains: Path) -> Guard:
    """Load Guard from .meld files in *domains* directory."""
    meld_files = sorted(domains.glob("*.meld"))
    if not meld_files:
        print(f"No .meld files found in {domains}", file=sys.stderr)
        sys.exit(2)
    return Guard.from_meld_files(meld_files, code_prevalence=["IAMissionCode"])


def _build_client(base_url: str, model: str) -> OpenAICompatibleLLMClient:
    """Build and check an LLM client."""
    client = OpenAICompatibleLLMClient(base_url=base_url, model=model)
    if not client.available():
        print(f"LLM endpoint not reachable: {base_url}", file=sys.stderr)
        sys.exit(2)
    return client


def _load_scenarios(
    scenarios_dir: Path | None,
    scenario_filter: list[str] | None = None,
) -> list[RedTeamScenario]:
    """Load scenarios from directory or fall back to built-in defaults."""
    if scenarios_dir is not None:
        scenarios = load_scenario_library(scenarios_dir)
    else:
        scenarios = build_default_scenarios()

    if scenario_filter:
        wanted = set(scenario_filter)
        scenarios = [s for s in scenarios if s.scenario_id in wanted]
        if not scenarios:
            print(f"No matching scenarios for: {sorted(wanted)}", file=sys.stderr)
            sys.exit(2)

    return scenarios


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments shared across subcommands."""
    parser.add_argument(
        "--domains",
        type=Path,
        default=DEFAULT_DOMAIN_DIR,
        help="Directory containing the domain .meld files",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:1234/v1",
        help="OpenAI-compatible model endpoint",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Model identifier at the OpenAI-compatible endpoint",
    )
    parser.add_argument(
        "--scenarios-dir",
        type=Path,
        default=None,
        help="Directory with YAML scenario files (default: built-in scenarios)",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        help="Scenario id to run (may be specified multiple times)",
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=None,
        help="Override the default number of attempts per scenario",
    )


# ── Subcommand: run (default) ───────────────────────────────


def _cmd_run(args: argparse.Namespace) -> None:
    """Run the red-team pipeline."""
    client = _build_client(args.base_url, args.model)
    guard = _build_guard(args.domains)
    scenarios = _load_scenarios(args.scenarios_dir, args.scenario or None)

    pipeline = RedTeamPipeline(guard=guard, client=client)
    report = pipeline.run_scenarios(scenarios, attempts=args.attempts)

    for result in report.scenarios:
        finding_count = sum(len(attempt.findings) for attempt in result.attempts)
        print(
            f"[{result.status}] {result.scenario_id} "
            f"(attempts={len(result.attempts)}, findings={finding_count})"
        )

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        print(f"Wrote report to {args.output}")

    fail = not report.passed
    if args.fail_on_boundary:
        fail = fail or any(
            result.status == "EXPOSED_BOUNDARY" for result in report.scenarios
        )
    sys.exit(1 if fail else 0)


# ── Subcommand: ci ───────────────────────────────────────────


def _cmd_ci(args: argparse.Namespace) -> None:
    """Run the CI security gate."""
    from aegis.redteam.ci import run_ci_gate

    code = run_ci_gate(
        scenarios_dir=args.scenarios_dir,
        domains_dir=args.domains,
        base_url=args.base_url,
        model=args.model,
        code_prevalence=["IAMissionCode"],
        attempts=args.attempts,
        fail_on_boundary=args.fail_on_boundary,
    )
    sys.exit(code)


# ── Subcommand: freeze ──────────────────────────────────────


def _cmd_freeze(args: argparse.Namespace) -> None:
    """Freeze EXPOSED scenarios from a report to YAML files."""
    from aegis.redteam.freeze import freeze_from_report

    frozen = freeze_from_report(args.report, args.output_dir)
    for path in frozen:
        print(f"Frozen: {path}")
    if not frozen:
        print("No EXPOSED scenarios to freeze.")


# ── Subcommand: contract-check ──────────────────────────────


def _cmd_contract_check(args: argparse.Namespace) -> None:
    """Run host-contract checks (HC-001 through HC-009)."""
    from aegis.redteam.contracts import HostContractChecker

    guard = _build_guard(args.domains)

    # Build a minimal host-tool list from the guard's registry
    tool_schema = {
        "type": "function",
        "function": {
            "name": "aegis_check",
            "description": "Propose an action to the ethical guard for evaluation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action_type": {
                        "type": "string",
                        "enum": guard._registry.action_types,
                    },
                    "agent_id": {"type": "string"},
                    "proposition": {"type": "object"},
                },
            },
        },
    }
    host_tools = [tool_schema]

    checker = HostContractChecker(
        host_tools=host_tools,
        registry=guard._registry,
        side_effect_tools=list(args.side_effect_tools or []),
        guarded_tools=list(args.guarded_tools or []),
    )
    violations = checker.check_all()
    for v in violations:
        print(f"[{v.severity.upper()}] {v.code}: {v.message}")

    # AEGIS-1708: IFC host-contract checks (HC-005 through HC-009)
    if getattr(args, "ifc", False):
        from aegis.ifc.host_contract import IFCHostContract, check_ifc_contracts

        ifc_contract = IFCHostContract(
            contract_id="ifc-default",
            mandatory_broker=True,
            classification_required=True,
        )
        # With no workspace files provided via CLI, report advisory
        ifc_violations = check_ifc_contracts(
            ifc_contract,
            workspace_files={},
            broker_configured=getattr(args, "broker_configured", False),
            tool_suite_tools=["read_workspace_file", "search_workspace_files"],
        )
        for v in ifc_violations:
            print(f"[{v.severity.upper()}] {v.code}: {v.message}")
            violations.append(type("V", (), {"severity": v.severity})())  # type: ignore[arg-type]

    # AEGIS-1808: Channel registry verification
    if getattr(args, "channels", False):
        from aegis.ifc.channel_registry import CHANNEL_REGISTRY, uncovered_channels

        gaps = uncovered_channels()
        for ch in CHANNEL_REGISTRY:
            status = "PASS" if ch.verified_by else "FAIL"
            print(
                f"  [{status}] {ch.channel_id}: "
                f"enforcement={ch.enforcement}, "
                f"scenarios={len(ch.verified_by)}"
            )
        if gaps:
            print(f"FAIL: {len(gaps)} channel(s) have no verifying scenario")
            violations.append(type("V", (), {"severity": "critical"})())  # type: ignore[arg-type]
        else:
            print(f"All {len(CHANNEL_REGISTRY)} channels have verifying scenarios.")

    if not violations:
        print("All host contracts satisfied.")
    sys.exit(1 if any(v.severity in ("critical", "high") for v in violations) else 0)


# ── Subcommand: scorecard ───────────────────────────────────


def _cmd_scorecard(args: argparse.Namespace) -> None:
    """Generate a security scorecard."""
    from aegis.redteam.scorecard import ScorecardBuilder

    builder = ScorecardBuilder()

    if args.report:
        raw = json.loads(args.report.read_text(encoding="utf-8"))
        report = _reconstruct_report(raw)
        builder.add_redteam_report(report)

    scorecard = builder.build()
    if args.format == "markdown":
        print(scorecard.to_markdown())
    else:
        print(json.dumps(scorecard.to_dict(), indent=2))

    sys.exit(0 if scorecard.release_eligible() else 1)


def _cmd_coverage(args: argparse.Namespace) -> None:
    """Show the channel coverage matrix (AEGIS-2001)."""
    from aegis.redteam.coverage import CoverageMatrix

    matrix = CoverageMatrix.from_registry()
    if args.format == "markdown":
        print(matrix.to_markdown())
    else:
        print(json.dumps(matrix.to_dict(), indent=2))

    uncovered = matrix.uncovered()
    sys.exit(1 if uncovered else 0)


def _cmd_certify(args: argparse.Namespace) -> None:
    """Generate a bypass-freedom certificate (AEGIS-2003)."""
    from aegis.ifc.channel_registry import CHANNEL_REGISTRY
    from aegis.redteam.bypass_proof import BypassProofReport
    from aegis.redteam.coverage import CoverageMatrix

    raw = json.loads(args.report.read_text(encoding="utf-8"))
    report = _reconstruct_report(raw)
    proof = BypassProofReport.from_report(report)

    print(proof.summary())

    if not proof.is_bypass_free():
        print("\nCertification FAILED: bypass findings exist.")
        sys.exit(1)

    matrix = CoverageMatrix.from_registry()
    cert = proof.to_certification(
        guard_version=args.guard_version,
        channels_covered=len(CHANNEL_REGISTRY) - len(matrix.uncovered()),
        evidence_path=str(args.report),
    )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(cert, indent=2),
            encoding="utf-8",
        )
        print(f"Certificate written to {args.output}")
    else:
        print(json.dumps(cert, indent=2))

    sys.exit(0)


def _reconstruct_report(raw: dict[str, object]) -> RedTeamReport:
    """Reconstruct a RedTeamReport from a raw dict for scorecard scoring."""
    scenarios: list[ScenarioResult] = []
    raw_scenarios = raw.get("scenarios", [])
    if not isinstance(raw_scenarios, list):
        raw_scenarios = []
    for s in raw_scenarios:
        if not isinstance(s, dict):
            continue
        attempts: list[AttemptResult] = []
        raw_attempts = s.get("attempts", [])
        if not isinstance(raw_attempts, list):
            raw_attempts = []
        for a in raw_attempts:
            if not isinstance(a, dict):
                continue
            raw_findings = a.get("findings", [])
            if not isinstance(raw_findings, list):
                raw_findings = []
            findings = [
                Finding(
                    code=str(f.get("code", "")),
                    severity=str(f.get("severity", "medium")),  # type: ignore[arg-type]
                    message=str(f.get("message", "")),
                )
                for f in raw_findings
                if isinstance(f, dict)
            ]
            attempts.append(AttemptResult(
                attempt_index=int(a.get("attempt_index", 0) or 0),
                findings=findings,
            ))
        scenarios.append(ScenarioResult(
            scenario_id=str(s.get("scenario_id", "")),
            description=str(s.get("description", "")),
            expectation=str(s.get("expectation", "resist")),  # type: ignore[arg-type]
            attempts=attempts,
        ))

    return RedTeamReport(
        base_url=str(raw.get("base_url", "")),
        model=str(raw.get("model", "")),
        scenarios=scenarios,
    )


# ── Main entry point ────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    """Run the red-team pipeline from the command line."""
    parser = argparse.ArgumentParser(
        prog="aegis-redteam",
        description="Run adversarial prompt/tool-use scenarios against AEGIS.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # Default: run
    run_parser = subparsers.add_parser("run", help="Run red-team scenarios")
    _add_common_args(run_parser)
    run_parser.add_argument("--output", type=Path, default=None)
    run_parser.add_argument("--fail-on-boundary", action="store_true")
    run_parser.add_argument("--runs", type=int, default=None, help="Multi-run count")

    # ci
    ci_parser = subparsers.add_parser("ci", help="CI security gate")
    _add_common_args(ci_parser)
    ci_parser.add_argument("--fail-on-boundary", action="store_true")

    # freeze
    freeze_parser = subparsers.add_parser("freeze", help="Freeze EXPOSED scenarios")
    freeze_parser.add_argument("report", type=Path, help="JSON report file")
    freeze_parser.add_argument("--output-dir", type=Path, default=Path("scenarios/redteam/frozen"))

    # contract-check
    cc_parser = subparsers.add_parser("contract-check", help="Host-contract checks")
    cc_parser.add_argument("--domains", type=Path, default=DEFAULT_DOMAIN_DIR)
    cc_parser.add_argument(
        "--side-effect-tools",
        nargs="*",
        default=[],
        help="Tools that have external side effects",
    )
    cc_parser.add_argument(
        "--guarded-tools",
        nargs="*",
        default=[],
        help="Tools explicitly declared as guard-protected",
    )
    cc_parser.add_argument(
        "--ifc",
        action="store_true",
        help="Include IFC host-contract checks (HC-005 through HC-008)",
    )
    cc_parser.add_argument(
        "--broker-configured",
        action="store_true",
        help="Declare that the RetrievalBroker is configured (for IFC checks)",
    )
    cc_parser.add_argument(
        "--channels",
        action="store_true",
        help="Verify channel registry coverage (HC-009, AEGIS-1808)",
    )

    # scorecard
    sc_parser = subparsers.add_parser("scorecard", help="Security scorecard")
    sc_parser.add_argument("--report", type=Path, default=None)
    sc_parser.add_argument("--format", choices=["markdown", "json"], default="markdown")

    # coverage
    cov_parser = subparsers.add_parser("coverage", help="Channel coverage matrix")
    cov_parser.add_argument("--format", choices=["markdown", "json"], default="markdown")

    # certify
    cert_parser = subparsers.add_parser("certify", help="Generate bypass-freedom certificate")
    cert_parser.add_argument("--report", type=Path, required=True, help="Red-team report JSON")
    cert_parser.add_argument("--guard-version", default="1.0.0")
    cert_parser.add_argument("--output", type=Path, default=None)

    # plan-scenarios (AEGIS-2718, Epic 27)
    plan_parser = subparsers.add_parser(
        "plan-scenarios",
        help="Run plan-level red-team scenarios (AEGIS-2717). "
             "Exit 0 = all RESISTED, 1 = at least one bypass.",
    )
    plan_parser.add_argument(
        "--domains", type=Path, default=Path("aegis/domains/devops"),
        help="Domain directory (default: %(default)s).",
    )
    plan_parser.add_argument(
        "--output", type=Path, default=None,
        help="Optional JSON report path.",
    )
    plan_parser.add_argument(
        "--scenario", default=None,
        help="Run only the named scenario id (e.g. RT-PLAN-01).",
    )

    # plan-coverage (AEGIS-2718)
    pcov_parser = subparsers.add_parser(
        "plan-coverage",
        help="Print which violation types each plan-scenario exercises.",
    )
    pcov_parser.add_argument(
        "--format", choices=["markdown", "json"], default="markdown",
    )

    args = parser.parse_args(argv)

    # Handle no subcommand (backward compat: treat as 'run')
    if args.command is None:
        # Re-parse with legacy flat arguments
        _cmd_run_legacy(argv)
        return

    commands = {
        "run": _cmd_run,
        "ci": _cmd_ci,
        "freeze": _cmd_freeze,
        "contract-check": _cmd_contract_check,
        "scorecard": _cmd_scorecard,
        "coverage": _cmd_coverage,
        "certify": _cmd_certify,
        "plan-scenarios": _cmd_plan_scenarios,
        "plan-coverage": _cmd_plan_coverage,
    }
    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(2)


def _cmd_run_legacy(argv: list[str] | None) -> None:
    """Backward-compatible run without subcommands."""
    parser = argparse.ArgumentParser(
        prog="aegis-redteam",
        description="Run adversarial prompt/tool-use scenarios against AEGIS.",
    )
    _add_common_args(parser)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--fail-on-boundary", action="store_true")
    parser.add_argument("--runs", type=int, default=None)
    args = parser.parse_args(argv)
    _cmd_run(args)


# ── AEGIS-2718 (Epic 27): plan-level subcommands ───────────────────


def _cmd_plan_scenarios(args: argparse.Namespace) -> None:
    """Run plan-level red-team scenarios.

    Exit codes:
        0 — every scenario resisted (bypass count = 0)
        1 — at least one scenario bypassed the perimeter

    JSON report (when --output is given) carries one entry per outcome
    plus the aggregate bypass_count and average_plan_check_ms.
    """
    import json as _json

    from aegis.redteam.plan_scenarios import (
        build_plan_scenarios,
        run_plan_scenarios,
    )

    scenarios = build_plan_scenarios()
    if args.scenario:
        scenarios = [s for s in scenarios if s.scenario_id == args.scenario]
        if not scenarios:
            print(f"Error: no plan-scenario matches id {args.scenario!r}")
            sys.exit(2)

    report = run_plan_scenarios(scenarios, domain_dir=args.domains)

    print(f"Plan-scenarios: {len(report.outcomes)}")
    for outcome in report.outcomes:
        marker = "RESISTED" if outcome.resisted else "BYPASS"
        print(
            f"  [{marker}] {outcome.scenario_id}: "
            f"actual={outcome.actual_decision.value} "
            f"expected={outcome.expected_decision.value} "
            f"({outcome.plan_check_ms:.2f} ms)"
        )
        if outcome.expected_violation_types:
            kinds = ", ".join(
                v.value for v in outcome.expected_violation_types
            )
            actual = ", ".join(
                v.value for v in outcome.actual_violation_types
            )
            print(f"        expected_violations: {kinds}")
            print(f"        actual_violations:   {actual}")
        if outcome.residual_risk_id:
            print(f"        residual_risk: {outcome.residual_risk_id}")

    print(f"\nBypass count: {report.bypass_count}")
    print(f"Average plan_check: {report.average_plan_check_ms:.2f} ms")

    if args.output is not None:
        payload = {
            "bypass_count": report.bypass_count,
            "average_plan_check_ms": report.average_plan_check_ms,
            "outcomes": [
                {
                    "scenario_id": o.scenario_id,
                    "expected_decision": o.expected_decision.value,
                    "actual_decision": o.actual_decision.value,
                    "expected_violation_types": [
                        v.value for v in o.expected_violation_types
                    ],
                    "actual_violation_types": [
                        v.value for v in o.actual_violation_types
                    ],
                    "plan_check_ms": o.plan_check_ms,
                    "bypassed": o.bypassed,
                    "residual_risk_id": o.residual_risk_id,
                    "notes": o.notes,
                }
                for o in report.outcomes
            ],
        }
        args.output.write_text(_json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nWrote {args.output}")

    sys.exit(0 if report.all_resisted else 1)


def _cmd_plan_coverage(args: argparse.Namespace) -> None:
    """Print a coverage matrix mapping each scenario to violation kinds."""
    import json as _json

    from aegis.redteam.plan_scenarios import build_plan_scenarios

    scenarios = build_plan_scenarios()
    rows = [
        {
            "scenario_id": s.scenario_id,
            "expected_decision": s.expected_decision.value,
            "violation_types": [v.value for v in s.expected_violation_types],
            "residual_risk_id": s.residual_risk_id,
            "tags": list(s.tags),
        }
        for s in scenarios
    ]

    if args.format == "json":
        print(_json.dumps(rows, indent=2))
        return

    # Markdown.
    print("# Plan-Scenario Coverage")
    print()
    print("| Scenario | Expected | Violation Types | Residual Risk |")
    print("|---|---|---|---|")
    for row in rows:
        kinds = ", ".join(row["violation_types"]) or "—"
        rr = row["residual_risk_id"] or "—"
        print(
            f"| {row['scenario_id']} | {row['expected_decision']} | "
            f"{kinds} | {rr} |"
        )


if __name__ == "__main__":
    main()
