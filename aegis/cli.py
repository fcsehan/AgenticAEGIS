"""AEGIS CLI — entry point for the ``aegis`` command.

Subcommands:
  serve      — Start the AEGIS API server
  check      — Check a single action from JSON
  load       — Load and validate .meld domain files
  generate   — Generate MELD rules from natural language (LLM-based)
  dip        — Document Intelligence Pipeline (document → MELD domain)
  orchestrate — Send a prompt through Guard + LLM loop
  config     — Show active configuration
  audit      — Audit trail operations (verify)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aegis import __version__


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aegis",
        description="AEGIS — Architectural Ethics Guard for Intelligent Systems",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="command")

    # serve
    serve_p = sub.add_parser("serve", help="Start the AEGIS API server")
    serve_p.add_argument(
        "--domains", type=Path, help="Path to domain .meld files directory"
    )
    serve_p.add_argument("--host", default=None, help="Bind host")
    serve_p.add_argument("--port", type=int, default=None, help="Bind port")

    # check
    check_p = sub.add_parser("check", help="Check an action against the guard")
    check_p.add_argument("action_json", type=Path, help="Path to action JSON file")
    check_p.add_argument(
        "--domains", type=Path, required=True, help="Path to domain .meld files"
    )

    # plan-check (AEGIS-2720, Epic 27)
    plan_p = sub.add_parser(
        "plan-check",
        help="Evaluate a Plan (JSON) against the guard. "
             "Exit codes: 0=PERMITTED, 1=FORBIDDEN, 2=UNDECIDABLE.",
    )
    plan_p.add_argument(
        "plan_json", type=Path, help="Path to plan JSON file",
    )
    plan_p.add_argument(
        "--domains", type=Path, required=True,
        help="Path to domain .meld files directory",
    )
    plan_p.add_argument(
        "--explain", action="store_true",
        help="Print human-readable explanation of the plan verdict.",
    )
    plan_p.add_argument(
        "--audit-trail", type=Path, default=None,
        help="Append audit events for this plan-check to the given file.",
    )

    # plan-verify (AEGIS-2720)
    pverify_p = sub.add_parser(
        "plan-verify",
        help="Verify the plan-constraints in a domain (no plan needed).",
    )
    pverify_p.add_argument(
        "domain_dir", type=Path,
        help="Directory containing the .meld files of the domain.",
    )

    # plan-benchmark (AEGIS-2720)
    pbench_p = sub.add_parser(
        "plan-benchmark",
        help="Benchmark plan_check on a plan JSON over N iterations.",
    )
    pbench_p.add_argument(
        "plan_json", type=Path, help="Path to plan JSON file",
    )
    pbench_p.add_argument(
        "--domains", type=Path, required=True,
        help="Path to domain .meld files directory",
    )
    pbench_p.add_argument(
        "--iterations", type=int, default=1000,
        help="Number of plan_check iterations (default: %(default)d)",
    )

    # load
    load_p = sub.add_parser("load", help="Load and validate .meld domain files")
    load_p.add_argument("domain_dir", type=Path, help="Directory containing .meld files")

    # config
    sub.add_parser("config", help="Show active configuration")

    # orchestrate
    orch_p = sub.add_parser(
        "orchestrate",
        help="Send a user prompt through the full Guard + LLM loop",
    )
    orch_p.add_argument("--prompt", required=True, help="User prompt text")
    orch_p.add_argument(
        "--domains", type=Path, required=True,
        help="Path to domain .meld files directory",
    )
    orch_p.add_argument(
        "--base-url", default="http://localhost:1234/v1",
        help="OpenAI-compatible LLM endpoint (default: %(default)s)",
    )
    orch_p.add_argument(
        "--model", default="qwen/qwen3.8-27b",
        help="Model identifier at the endpoint (default: %(default)s)",
    )
    orch_p.add_argument(
        "--agent-id", default="intelligenceAgentInMission",
        help="Agent identity for Guard evaluation (default: %(default)s)",
    )
    orch_p.add_argument(
        "--system-prompt", default=None,
        help="Custom system prompt (default: built-in agent prompt)",
    )
    orch_p.add_argument(
        "--code-prevalence", nargs="*", default=None,
        help="Code prevalence order (default: derived from domain)",
    )
    orch_p.add_argument(
        "--max-rejections", type=int, default=3,
        help="FORBIDDEN retries before escalation (default: %(default)s)",
    )
    orch_p.add_argument(
        "--verbose", action="store_true",
        help="Print full verdict details and conversation trace",
    )

    # generate
    gen_p = sub.add_parser(
        "generate",
        help="Generate MELD rules from natural language description",
    )
    gen_p.add_argument(
        "domain_dir", type=Path,
        help="Directory containing existing .meld domain files",
    )
    gen_p.add_argument(
        "--description", "-d", required=True,
        help="Natural language description of the rules to generate",
    )
    gen_p.add_argument(
        "--provider", default="anthropic",
        help="LLM provider: anthropic, openai, lm-studio, ollama (default: %(default)s)",
    )
    gen_p.add_argument(
        "--model", default="claude-sonnet-4-6",
        help="Model identifier (default: %(default)s)",
    )
    gen_p.add_argument(
        "--output", "-o", type=Path, default=None,
        help="Output .meld file path (default: print to stdout)",
    )
    gen_p.add_argument(
        "--verify", action="store_true",
        help="Run 4-stage verification on each generated rule",
    )

    # dip
    dip_p = sub.add_parser(
        "dip",
        help="Document Intelligence Pipeline — convert normative documents to MELD domains",
    )
    dip_p.add_argument(
        "source",
        help="URL or file path to the normative document",
    )
    dip_p.add_argument(
        "--name", "-n", required=True,
        help="Domain name for the exported files (e.g. 'gdpr', 'corporate-policy')",
    )
    dip_p.add_argument(
        "--output", "-o", type=Path, default=None,
        help="Output directory (default: aegis/domains/dip-generated/<name>/). "
             "DIP-generated domains are kept separate from manual domains to "
             "prevent silent overwrite — see decision D-015.",
    )
    dip_p.add_argument(
        "--force", action="store_true",
        help="Override soft coexistence conflicts (overwrite existing .meld "
             "files in output dir). Cannot override hard conflicts "
             "(writing into a manual domain path).",
    )
    dip_p.add_argument(
        "--source-type", default="auto",
        choices=["auto", "html", "html-index", "text", "pdf"],
        help="Source type (default: auto-detect)",
    )
    dip_p.add_argument(
        "--language", default="auto",
        choices=["auto", "en"],
        help="Document language for chunker (default: auto-detect)",
    )
    dip_p.add_argument(
        "--domain-context", default="",
        help="Domain-specific hints for the LLM (e.g. 'GDPR data protection law')",
    )
    dip_p.add_argument(
        "--provider", default="anthropic",
        help="LLM provider: anthropic, openai, lm-studio, ollama (default: %(default)s)",
    )
    dip_p.add_argument(
        "--model", default="claude-sonnet-4-6",
        help="Model identifier (default: %(default)s)",
    )
    dip_p.add_argument(
        "--verify", action="store_true",
        help="Run 4-stage verification on each generated rule",
    )
    dip_p.add_argument(
        "--dry-run", action="store_true",
        help="Show compilation results without writing MELD files",
    )
    dip_p.add_argument(
        "--stats", action="store_true",
        help="Show detailed statistics after pipeline completion",
    )
    dip_p.add_argument(
        "--batch-size", type=int, default=5,
        help="Chunks per LLM call (default: %(default)s)",
    )

    # dip-verify
    dipv_p = sub.add_parser(
        "dip-verify",
        help="Verify a DIP-generated domain (coverage, reference tests)",
    )
    dipv_p.add_argument(
        "domain_dir", type=Path,
        help="Directory containing generated .meld files",
    )
    dipv_p.add_argument(
        "--reference", type=Path, default=None,
        help="JSON file with reference test cases",
    )
    dipv_p.add_argument(
        "--source", type=Path, default=None,
        help="Source document (for coverage analysis)",
    )

    # audit
    audit_p = sub.add_parser("audit", help="Audit trail operations")
    audit_sub = audit_p.add_subparsers(dest="audit_command")
    verify_p = audit_sub.add_parser("verify", help="Verify audit trail integrity")
    verify_p.add_argument("path", type=Path, help="Path to audit JSONL file")

    drift_p = audit_sub.add_parser(
        "drift-scan",
        help="Scan audit trail for suspected intent-action mismatches (AEGIS-3005)",
    )
    drift_p.add_argument("path", type=Path, help="Path to audit JSONL file")
    drift_p.add_argument(
        "--format", choices=["text", "json"], default="text",
        help="Output format (default: text)",
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "serve":
        _cmd_serve(args)
    elif args.command == "check":
        _cmd_check(args)
    elif args.command == "plan-check":
        _cmd_plan_check(args)
    elif args.command == "plan-verify":
        _cmd_plan_verify(args)
    elif args.command == "plan-benchmark":
        _cmd_plan_benchmark(args)
    elif args.command == "load":
        _cmd_load(args)
    elif args.command == "config":
        _cmd_config()
    elif args.command == "orchestrate":
        _cmd_orchestrate(args)
    elif args.command == "generate":
        _cmd_generate(args)
    elif args.command == "dip":
        _cmd_dip(args)
    elif args.command == "dip-verify":
        _cmd_dip_verify(args)
    elif args.command == "audit":
        _cmd_audit(args)
    else:
        parser.print_help()
        sys.exit(1)


def _cmd_serve(args: argparse.Namespace) -> None:
    """Start the AEGIS API server."""
    from aegis.api.server import GuardState, create_app
    from aegis.audit.trail import AuditTrail
    from aegis.config import AegisConfig
    from aegis.guard.guard import Guard
    from aegis.observability.logging import configure_logging

    config = AegisConfig()
    configure_logging(config.guard.log_level)

    domains_path = args.domains or config.guard.domains_path
    meld_files = sorted(Path(domains_path).glob("*.meld"))
    if not meld_files:
        print(f"Error: No .meld files found in {domains_path}")
        sys.exit(1)

    audit_path = config.guard.audit_path
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    trail = AuditTrail(audit_path)

    guard = Guard.from_meld_files(meld_files, audit_trail=trail)
    state = GuardState(guard=guard, audit_trail=trail, audit_path=audit_path)
    app = create_app(state)

    host = args.host or config.api.host
    port = args.port or config.api.port

    print(f"AEGIS Guard API starting on {host}:{port}")
    print(f"  Domains: {domains_path} ({len(meld_files)} files)")
    print(f"  Audit: {audit_path}")
    print(f"  Norms: {len(guard._norms)}")

    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="info")


def _cmd_check(args: argparse.Namespace) -> None:
    """Check a single action from a JSON file."""
    from aegis.guard.action import Action
    from aegis.guard.guard import Guard

    meld_files = sorted(Path(args.domains).glob("*.meld"))
    if not meld_files:
        print(f"Error: No .meld files found in {args.domains}")
        sys.exit(1)

    guard = Guard.from_meld_files(meld_files)

    action_data = json.loads(args.action_json.read_text())
    action = Action(
        action_type=action_data.get("action_type", ""),
        agent_id=action_data.get("agent_id", ""),
        proposition=action_data.get("proposition", {}),
        context=action_data.get("context", {}),
    )

    verdict = guard.check(action)
    print(verdict.explain())
    sys.exit(0 if verdict.decision.value == "PERMITTED" else 1)


def _cmd_plan_check(args: argparse.Namespace) -> None:
    """AEGIS-2720 (Epic 27) — evaluate a plan from JSON.

    Plan JSON shape::

        {
            "plan_id": "<optional>",
            "initial_state": {"k": "v", ...},
            "steps": [
                {"action_type": "X", "agent_id": "A",
                 "proposition": {...}, "context": {...},
                 "scheduled_duration_s": 0.0,
                 "pre_state": {...}, "post_state": {...}},
                ...
            ]
        }

    Exit codes:
        0 — plan_decision == PERMITTED
        1 — plan_decision == FORBIDDEN
        2 — plan_decision == UNDECIDABLE
        3 — runtime/argument error (e.g. malformed JSON, missing files)
    """
    from aegis.audit.trail import AuditTrail
    from aegis.guard.guard import Guard
    from aegis.guard.verdict import PlanDecision

    meld_files = sorted(Path(args.domains).glob("*.meld"))
    if not meld_files:
        print(f"Error: No .meld files found in {args.domains}")
        sys.exit(3)

    audit_trail = AuditTrail(args.audit_trail) if args.audit_trail else None
    guard = Guard.from_meld_files(meld_files, audit_trail=audit_trail)

    try:
        plan_data = json.loads(args.plan_json.read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"Error: Failed to read plan JSON: {e}")
        sys.exit(3)

    try:
        plan = _plan_from_json(plan_data)
    except ValueError as e:
        print(f"Error: Invalid plan JSON: {e}")
        sys.exit(3)

    verdict = guard.plan_check(plan)
    if args.explain:
        print(_explain_plan_verdict(verdict))
    else:
        print(verdict.plan_decision.value)
        if verdict.reason_summary:
            print(f"reason: {verdict.reason_summary}")

    decision_to_exit = {
        PlanDecision.PERMITTED: 0,
        PlanDecision.FORBIDDEN: 1,
        PlanDecision.UNDECIDABLE: 2,
    }
    sys.exit(decision_to_exit[verdict.plan_decision])


def _cmd_plan_verify(args: argparse.Namespace) -> None:
    """AEGIS-2720 — run the plan-constraint verifier on a domain.

    Loads the domain, extracts the compiled plan-constraints, and runs
    them through ``verify_plan_constraints``. Exit code is 0 when the
    verifier passes, 1 when symbol/conflict issues are reported.
    """
    from aegis.editor.plan_constraint_verification import verify_plan_constraints
    from aegis.guard.guard import Guard

    meld_files = sorted(Path(args.domain_dir).glob("*.meld"))
    if not meld_files:
        print(f"Error: No .meld files found in {args.domain_dir}")
        sys.exit(3)
    guard = Guard.from_meld_files(meld_files)

    if guard._module is None:
        print("Error: Domain has no compiled module (v1 fallback only).")
        sys.exit(3)

    constraints = guard._module.plan_constraints
    result = verify_plan_constraints(
        constraints,
        registry=guard._registry,
        existing_norms=guard._norms,
    )
    print(f"plan-constraints: {len(constraints)}")
    for stage in result.stages:
        print(f"  {stage.stage:<11} {stage.status.value} — {stage.message}")
    if result.plan_constraint_cycles:
        print(f"  cycles: {result.plan_constraint_cycles}")
    if result.plan_constraint_conflicts:
        print(f"  conflicts: {len(result.plan_constraint_conflicts)} entries")
    sys.exit(0 if result.passed else 1)


def _cmd_plan_benchmark(args: argparse.Namespace) -> None:
    """AEGIS-2720 — micro-benchmark for ``plan_check``.

    Runs ``--iterations`` plan_check calls on the same plan and prints
    min / mean / max / p95 wall-clock times. Useful for catching
    obvious regressions outside of pytest-benchmark.
    """
    import time

    from aegis.guard.guard import Guard

    meld_files = sorted(Path(args.domains).glob("*.meld"))
    if not meld_files:
        print(f"Error: No .meld files found in {args.domains}")
        sys.exit(3)
    guard = Guard.from_meld_files(meld_files)

    try:
        plan_data = json.loads(args.plan_json.read_text())
        plan = _plan_from_json(plan_data)
    except (OSError, json.JSONDecodeError, ValueError) as e:
        print(f"Error: Failed to load plan: {e}")
        sys.exit(3)

    iterations = max(args.iterations, 1)
    samples: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        guard.plan_check(plan)
        samples.append((time.perf_counter() - t0) * 1000.0)

    samples.sort()
    p95_index = min(len(samples) - 1, int(0.95 * len(samples)))
    print(f"plan-benchmark over {iterations} iterations:")
    print(f"  min   : {samples[0]:9.3f} ms")
    print(f"  mean  : {sum(samples) / len(samples):9.3f} ms")
    print(f"  p95   : {samples[p95_index]:9.3f} ms")
    print(f"  max   : {samples[-1]:9.3f} ms")
    print(f"  steps : {len(plan.steps)}")
    sys.exit(0)


def _plan_from_json(data: dict) -> object:
    """Build a Plan from a parsed JSON dict.

    Unknown fields are tolerated (forward-compat). Missing fields fall
    back to defaults from the Plan / PlanStep / StateSnapshot types.
    """
    from aegis.guard.action import Action
    from aegis.guard.plan import Plan, PlanStep, StateSnapshot

    if not isinstance(data, dict):
        raise ValueError(f"plan JSON must be an object, got {type(data).__name__}")

    raw_steps = data.get("steps", [])
    if not isinstance(raw_steps, list):
        raise ValueError("plan.steps must be an array")

    steps: list[PlanStep] = []
    for index, raw in enumerate(raw_steps):
        if not isinstance(raw, dict):
            raise ValueError(f"plan.steps[{index}] must be an object")
        action = Action(
            action_type=str(raw.get("action_type", "")),
            agent_id=str(raw.get("agent_id", "")),
            proposition=raw.get("proposition", {}) or {},
            context=raw.get("context", {}) or {},
            user_intent=str(raw.get("user_intent", "")),
        )
        pre_fields = raw.get("pre_state", {}) or {}
        post_fields = raw.get("post_state", {}) or {}
        if not isinstance(pre_fields, dict) or not isinstance(post_fields, dict):
            raise ValueError(
                f"plan.steps[{index}].pre_state / .post_state must be objects",
            )
        steps.append(PlanStep(
            action=action,
            step_id=str(raw.get("step_id", "")),
            scheduled_duration_s=float(raw.get("scheduled_duration_s", 0.0)),
            pre_state=StateSnapshot(fields=pre_fields),
            post_state=StateSnapshot(fields=post_fields),
        ))

    initial_fields = data.get("initial_state", {}) or {}
    if not isinstance(initial_fields, dict):
        raise ValueError("plan.initial_state must be an object")

    return Plan(
        steps=tuple(steps),
        initial_state=StateSnapshot(fields=initial_fields),
        plan_id=str(data.get("plan_id", "")),
    )


def _explain_plan_verdict(verdict: object) -> str:
    """Format a PlanVerdict in the same human-readable style as
    ``Verdict.explain()``."""
    lines = [
        f"PlanDecision: {verdict.plan_decision.value}",  # type: ignore[attr-defined]
        f"evaluation_mode: {verdict.evaluation_mode!r}",  # type: ignore[attr-defined]
    ]
    if verdict.reason_summary:  # type: ignore[attr-defined]
        lines.append(f"reason: {verdict.reason_summary}")  # type: ignore[attr-defined]
    if verdict.violations:  # type: ignore[attr-defined]
        lines.append("Violations:")
        for v in verdict.violations:  # type: ignore[attr-defined]
            piece = f"  - {v.violation_type.value}"
            if v.constraint_id:
                piece += f" (constraint={v.constraint_id})"
            if v.step_index >= 0:
                piece += f" @step={v.step_index}"
            if v.detail:
                piece += f": {v.detail}"
            lines.append(piece)
    if verdict.per_step_verdicts:  # type: ignore[attr-defined]
        lines.append("Per-step decisions:")
        for index, step_v in enumerate(verdict.per_step_verdicts):  # type: ignore[attr-defined]
            lines.append(
                f"  [{index}] {step_v.action_type}: {step_v.decision.value} "
                f"({step_v.reason_type.value})",
            )
    return "\n".join(lines)


def _cmd_load(args: argparse.Namespace) -> None:
    """Load and validate .meld domain files."""
    from aegis.guard.guard import Guard

    domain_dir = Path(args.domain_dir)
    meld_files = sorted(domain_dir.glob("*.meld"))
    if not meld_files:
        print(f"Error: No .meld files found in {domain_dir}")
        sys.exit(1)

    print(f"Loading {len(meld_files)} .meld files from {domain_dir}...")
    try:
        guard = Guard.from_meld_files(meld_files)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    print(f"  Facts: {guard._kb.fact_count}")
    print(f"  Microtheories: {list(guard._kb.microtheories)}")
    print(f"  Norms: {len(guard._norms)}")
    print(f"  Action types: {guard._registry.action_types}")
    print("Domain loaded successfully.")


_DEFAULT_SYSTEM_PROMPT = """\
You are {agent_id}, an AI agent operating under AEGIS governance.

Rules:
1. Before performing ANY action, you MUST call the aegis_check tool.
2. If the guard returns PERMITTED, confirm the action to the user.
3. If the guard returns FORBIDDEN, explain why and suggest an alternative.
4. If the guard returns UNDECIDABLE, escalate to a human operator.
5. Never attempt to perform actions without guard approval.
"""


def _cmd_orchestrate(args: argparse.Namespace) -> None:
    """Send a user prompt through the full Guard + LLM orchestration loop."""
    import urllib.request

    from aegis.api.executor import ActionExecutor
    from aegis.guard.guard import Guard
    from aegis.hardening.output_guard import OutputFilter
    from aegis.hardening.permit import PermitStore
    from aegis.hardening.refusal import RefusalRegistry
    from aegis.orchestrator.orchestrator import AgentOrchestrator

    # 1. Load domain
    meld_files = sorted(Path(args.domains).glob("*.meld"))
    if not meld_files:
        print(f"Error: No .meld files found in {args.domains}", file=sys.stderr)
        sys.exit(1)

    code_prevalence = args.code_prevalence
    if code_prevalence is None:
        # Derive from domain dir name: aegis/domains/iamission → IAMissionCode
        domain_name = args.domains.name.replace("Project", "").replace("meld", "")
        code_prevalence = [f"{domain_name}Code"] if domain_name else []

    permit_store = PermitStore()
    guard = Guard.from_meld_files(
        meld_files,
        code_prevalence=code_prevalence,
        permit_store=permit_store,
    )

    # 2. Check LLM endpoint
    try:
        req = urllib.request.Request(f"{args.base_url.rstrip('/')}/models", method="GET")
        with urllib.request.urlopen(req, timeout=5):
            pass
    except Exception:
        print(f"Error: LLM endpoint not reachable: {args.base_url}", file=sys.stderr)
        sys.exit(2)

    # 3. Build executor (no side-effect handlers in CLI mode — Guard-only evaluation)
    executor = ActionExecutor(guard, permit_store=permit_store)

    # 4. Build orchestrator with full hardening stack
    system_prompt = args.system_prompt or _DEFAULT_SYSTEM_PROMPT.format(
        agent_id=args.agent_id,
    )
    output_guard = OutputFilter()
    refusal_registry = RefusalRegistry()

    orchestrator = AgentOrchestrator(
        executor=executor,
        base_url=args.base_url,
        model=args.model,
        system_prompt=system_prompt,
        max_rejections=args.max_rejections,
        output_guard=output_guard,
        refusal_registry=refusal_registry,
    )

    # 5. Run
    if args.verbose:
        print(f"Domain:   {args.domains} ({len(meld_files)} files)")
        print(f"Norms:    {len(guard._norms)}")
        print(f"Actions:  {guard._registry.action_types}")
        print(f"LLM:      {args.base_url} / {args.model}")
        print(f"Agent:    {args.agent_id}")
        print(f"Max rej:  {args.max_rejections}")
        print("─" * 60)
        print(f"Prompt:   {args.prompt}")
        print("─" * 60)

    result = orchestrator.run(args.prompt)

    # 6. Output
    if args.verbose:
        for v in result.verdicts:
            print(f"\n[{v.decision.value}] {v.action_type}")
            print(f"  Reason: {v.reason_type.value}")
            for line in v.justification_chain:
                print(f"  │ {line}")
            if v.norms_applied:
                print(f"  Norms: {', '.join(v.norms_applied)}")
        if result.output_sanitized:
            print(f"\n⚠ OutputFilter redacted: {result.output_violations}")
        if result.escalated:
            print("\n⚠ Escalated to human operator.")
        print("─" * 60)

    print(f"\n{result.final_response}")

    # Exit code: 0 = ok, 1 = escalated/forbidden, 2 = error
    if result.escalated:
        sys.exit(1)


def _cmd_generate(args: argparse.Namespace) -> None:
    """Generate MELD rules from natural language description."""
    from aegis.editor.domain_model import domain_from_meld
    from aegis.editor.llm_provider import LLMClient, LLMProviderInfo
    from aegis.editor.meld_generator import MeldGenerator
    from aegis.guard.guard import Guard

    # 1. Load existing domain
    domain_dir = Path(args.domain_dir)
    meld_files = sorted(domain_dir.glob("*.meld"))
    if not meld_files:
        print(f"Error: No .meld files found in {domain_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading domain from {domain_dir} ({len(meld_files)} files)...")
    try:
        guard = Guard.from_meld_files(meld_files)
    except Exception as e:
        print(f"Error loading domain: {e}", file=sys.stderr)
        sys.exit(1)

    domain = domain_from_meld(
        domain_id=domain_dir.name,
        name=domain_dir.name,
        meld_paths=meld_files,
        guard=guard,
        norms=guard._norms,
        kb=guard._kb,
    )
    print(f"  Roles: {[r.name for r in domain.roles]}")
    print(f"  Codes: {[c.name for c in domain.codes]}")
    print(f"  Existing rules: {len(domain.rules)}")

    # 2. Set up LLM client
    provider_id = args.provider
    model = args.model

    # Determine base_url from provider
    provider_urls = {
        "lm-studio": "http://localhost:1234/v1",
        "ollama": "http://localhost:11434/v1",
        "vllm": "http://localhost:8000/v1",
        "openai": "https://api.openai.com/v1",
        "anthropic": "https://api.anthropic.com",
    }
    base_url = provider_urls.get(provider_id, provider_urls["anthropic"])

    import os

    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""

    provider = LLMProviderInfo(
        id=provider_id,
        name=provider_id,
        base_url=base_url,
        available=True,
        models=[model],
        api_key=api_key,
    )
    client = LLMClient(provider, model, temperature=0)

    # 3. Generate
    print(f"\nGenerating rules with {provider_id}/{model}...")
    print(f"  Description: {args.description}")
    print()

    generator = MeldGenerator(client, domain)
    try:
        proposals = generator.generate(args.description)
    except Exception as e:
        print(f"Error during generation: {e}", file=sys.stderr)
        sys.exit(1)

    if not proposals:
        print("No rules generated. Try a more specific description.")
        sys.exit(0)

    # 4. Display proposals
    print(f"Generated {len(proposals)} rule(s):\n")
    meld_lines: list[str] = []
    for i, p in enumerate(proposals, 1):
        print(f"  [{i}] {p.modality} — {p.agent_role}")
        print(f"      {p.natural_language_summary}")
        print(f"      MELD: {p.meld_expression}")
        if p.reasoning:
            print(f"      Reasoning: {p.reasoning}")
        meld_lines.append(p.meld_expression)
        print()

    # 5. Optional verification
    if args.verify:
        from aegis.kb.meld_loader import extract_norm, parse_meld

        print("Verifying generated rules...")
        for i, p in enumerate(proposals, 1):
            assertions = parse_meld(p.meld_expression)
            if assertions:
                norm = extract_norm(assertions[0], "generated", f"gen:{i}")
                if norm is not None:
                    print(f"  [{i}] ✓ Syntax + Extraction OK")
                else:
                    print(f"  [{i}] ✗ Extraction failed")
            else:
                print(f"  [{i}] ✗ Parse failed")
        print()

    # 6. Output
    if args.output:
        output_path = Path(args.output)
        header = "(aegis-schema-version 1)\n(case GeneratedRulesMt)\n\n"
        content = header + "\n".join(meld_lines) + "\n"
        output_path.write_text(content, encoding="utf-8")
        print(f"Written to {output_path}")
    else:
        print("─" * 60)
        print("MELD output (copy to your domain's DeonticRules file):\n")
        for line in meld_lines:
            print(f"  {line}")


def _cmd_dip(args: argparse.Namespace) -> None:
    """Run the Document Intelligence Pipeline."""
    from aegis.dip.coexistence import default_output_dir
    from aegis.dip.pipeline import run_pipeline
    from aegis.editor.llm_provider import LLMClient, LLMProviderInfo, ModelInfo

    # Resolve output directory — default isolates DIP-generated domains
    # from manual ones (decision D-015).
    output_dir = args.output
    if output_dir is None:
        output_dir = default_output_dir(args.name)
    output_dir = Path(output_dir)

    # Build LLM client
    provider = LLMProviderInfo(
        id=args.provider,
        name=args.provider,
        type="local" if args.provider in ("lm-studio", "ollama", "vllm") else "remote",
        base_url={
            "lm-studio": "http://localhost:1234/v1",
            "ollama": "http://localhost:11434/v1",
            "vllm": "http://localhost:8000/v1",
            "openai": "https://api.openai.com/v1",
            "anthropic": "https://api.anthropic.com",
        }.get(args.provider, "http://localhost:1234/v1"),
        available=True,
        models=[ModelInfo(id=args.model, name=args.model)],
    )
    client = LLMClient(provider, args.model)

    # Progress callback
    def on_progress(stage: int, message: str) -> None:
        print(f"[Stage {stage}/6] {message}")

    print(f"DIP: {args.source} → {output_dir}/")
    print(f"LLM: {args.provider}/{args.model}")
    if args.domain_context:
        print(f"Context: {args.domain_context}")
    print()

    try:
        export = run_pipeline(
            source=args.source,
            name=args.name,
            client=client,
            output_dir=output_dir,
            source_type=args.source_type,
            language=args.language,
            domain_context=args.domain_context,
            batch_size=args.batch_size,
            verify=args.verify,
            dry_run=args.dry_run,
            on_progress=on_progress,
            force=args.force,
        )
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)

    # Summary
    print(f"\n{export.summary()}")

    if args.stats:
        print("\nFiles:")
        if export.ontology_path:
            print(f"  Ontology:  {export.ontology_path}")
        if export.vocab_path:
            print(f"  Vocab:     {export.vocab_path}")
        if export.rules_path:
            print(f"  Rules:     {export.rules_path}")
        print("\nStatistics:")
        print(f"  Obligations:  {export.obligations}")
        print(f"  Prohibitions: {export.prohibitions}")
        print(f"  Permissions:  {export.permissions}")
        if export.flags:
            print(f"\nReview flags ({export.flagged_for_review}):")
            reasons: dict[str, int] = {}
            for f in export.flags:
                reasons[f.reason] = reasons.get(f.reason, 0) + 1
            for reason, count in sorted(reasons.items()):
                print(f"  {reason}: {count}")

    if export.flagged_for_review > 0:
        sys.exit(2)  # warnings present
    sys.exit(0)


def _cmd_dip_verify(args: argparse.Namespace) -> None:
    """Verify a DIP-generated domain."""
    from aegis.guard.guard import Guard

    domain_dir = args.domain_dir
    meld_files = sorted(domain_dir.glob("*.meld"))
    if not meld_files:
        print(f"Error: No .meld files found in {domain_dir}", file=sys.stderr)
        sys.exit(1)

    # Load Guard
    print(f"Loading domain from {domain_dir}/ ({len(meld_files)} files)...")
    try:
        guard = Guard.from_meld_files(meld_files)
        print(f"  Guard loaded: {len(guard._norms)} norms")
    except Exception as e:
        print(f"  Error loading domain: {e}", file=sys.stderr)
        sys.exit(1)

    exit_code = 0

    # Reference tests
    if args.reference:
        from aegis.dip.coverage import load_reference_tests, run_reference_tests

        print(f"\nRunning reference tests from {args.reference}...")
        tests = load_reference_tests(args.reference)
        report = run_reference_tests(guard, tests)
        print(f"  {report.summary()}")
        for r in report.results:
            status = "PASS" if r.passed else "FAIL"
            print(f"    [{status}] {r.test.agent_id}/{r.test.action_type}: "
                  f"expected {r.test.expected_verdict}, got {r.actual_verdict}"
                  f" — {r.test.description}")
        if report.failed > 0:
            exit_code = 2

    # Coverage analysis (if source document provided)
    if args.source:
        from aegis.dip.chunker import chunk_document
        from aegis.dip.coverage import analyze_coverage
        from aegis.dip.fetcher import fetch_document

        print(f"\nCoverage analysis for {args.source}...")
        doc = fetch_document(str(args.source))
        chunks = chunk_document(doc)
        # We can only analyze what we have — no statements/results without LLM
        report = analyze_coverage(doc, chunks, [], [])
        print(f"  {report.summary()}")
        for a in report.articles:
            status = "✓" if a.chunks_produced > 0 else "—"
            print(f"    [{status}] Art. {a.number}: {a.title} "
                  f"({a.chunks_produced} chunks)")

    # Review report — find *-review.json in domain dir
    review_path = None
    for candidate in domain_dir.glob("*-review.json"):
        review_path = candidate
        break

    if review_path and review_path.exists():
        import json
        review = json.loads(review_path.read_text())
        print(f"\nReview report: {review_path.name}")
        print(f"  Rules: {review.get('total_rules', '?')}")
        print(f"  Auto-generated: {review.get('auto_generated', '?')}")
        print(f"  Flagged: {review.get('flagged_for_review', '?')}")
        reasons = review.get("flagged_reasons", {})
        if reasons:
            print("  Flag reasons:")
            for reason, count in sorted(reasons.items()):
                print(f"    {reason}: {count}")

    sys.exit(exit_code)


def _cmd_config() -> None:
    """Show active configuration."""
    from aegis.config import AegisConfig

    config = AegisConfig()
    print(config.show())


def _cmd_audit(args: argparse.Namespace) -> None:
    """Audit trail operations."""
    if args.audit_command == "verify":
        from aegis.audit.integrity import verify_integrity

        result = verify_integrity(args.path)
        if result.valid:
            print(
                f"Audit trail valid: {result.total_entries} entries, "
                f"verified in {result.verification_time_ms:.1f}ms"
            )
        else:
            print(f"Audit trail INVALID: {len(result.errors)} errors")
            for error in result.errors:
                print(f"  [{error.error_type}] Entry {error.entry_id}: {error.message}")
            sys.exit(1)
    elif args.audit_command == "drift-scan":
        from aegis.audit.drift_reporter import (
            render_json_report,
            render_text_report,
            scan_audit_log,
        )

        findings = scan_audit_log(args.path)
        if args.format == "json":
            print(render_json_report(findings))
        else:
            print(render_text_report(findings))
        # Exit non-zero when high-severity findings are present so CI
        # gates can attach to the result.
        if any(f.severity == "high" for f in findings):
            sys.exit(2)
    else:
        print("Usage: aegis audit {verify,drift-scan} <path>")
        sys.exit(1)
