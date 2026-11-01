"""Run bounded TLC checks and compare constraints with the Python evaluator.

Use the Python environment of the runtime artifact being checked. Pass a local
TLA+ tools JAR; the checker and Java are not vendored. All generated models and
state files live in a temporary directory. --output-dir preserves portable logs
and a hash-bound JSON report. This is bounded evidence, not a refinement proof.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Also allow the corrected supplement to run against an installed v0.1.0.
ROOT = Path(__file__).resolve().parents[2]
if (ROOT / "aegis").is_dir():
    sys.path.insert(0, str(ROOT))

from aegis.engine import plan_eval  # noqa: E402
from aegis.engine.ddic_ir import (  # noqa: E402
    DDICInteger,
    DDICPlanConstraint,
    DDICSymbol,
    PlanConstraintKind,
)

ACTIONS = ("a", "b", "c")
VARIANTS = {
    "standard": ((("a", "b"),), (1, 2, 2)),
    "no_sequence": ((), (1, 2, 2)),
    "cycle": ((("a", "b"), ("b", "a")), (1, 2, 2)),
    "self_pair": ((("a", "a"),), (1, 2, 2)),
    "zero_limit": ((("a", "b"),), (1, 2, 0)),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tla_sequence(values: tuple[str, ...]) -> str:
    return "<<" + ", ".join(json.dumps(v) for v in values) + ">>"


def tla_set(values: list[str]) -> str:
    return "{" + ", ".join(values) + "}"


def oracle_module(pairs: tuple[tuple[str, str], ...], limits: tuple[int, ...]) -> str:
    constraints = tuple(
        DDICPlanConstraint(
            constraint_id=f"sequence-{i}",
            kind=PlanConstraintKind.OBLIGATE_SEQUENCE,
            args=tuple(DDICSymbol(a) for a in pair),
        )
        for i, pair in enumerate(pairs)
    ) + tuple(
        DDICPlanConstraint(
            constraint_id=f"aggregate-{a}",
            kind=PlanConstraintKind.FORBID_AGGREGATE,
            args=(DDICSymbol(a), DDICInteger(limit)),
        )
        for a, limit in zip(ACTIONS, limits, strict=True)
    )
    cases: list[str] = []
    for size in range(5):
        for actions in itertools.product(ACTIONS, repeat=size):
            view = plan_eval.PlanView(
                steps=tuple(
                    plan_eval.PlanStepView(i, a, "model-agent", (a,)) for i, a in enumerate(actions)
                )
            )
            violations = plan_eval._check_obligate_sequence(
                constraints, view
            ) + plan_eval._check_forbid_aggregate(constraints, view)
            kinds = sorted({v.kind.value for v in violations})
            cases.append(
                f"plan = {tla_sequence(actions)} -> " + tla_set([json.dumps(k) for k in kinds])
            )
    sequence = tla_set([tla_sequence(pair) for pair in pairs])
    limit_cases = " [] ".join(
        f"a = {json.dumps(a)} -> {limit}" for a, limit in zip(ACTIONS, limits, strict=True)
    )
    return (
        "---- MODULE plan_correspondence ----\nEXTENDS plan_algorithm\n"
        f"CheckedSequenceConstraints == {sequence}\n"
        f"CheckedAggregateLimits == [a \\in Actions |-> CASE {limit_cases}]\n"
        "PythonConstraintKinds == CASE " + "\n    [] ".join(cases) + "\n"
        "PythonConstraintCorrespondence ==\n"
        '    (ConstraintViolations \\ {"EXTERNAL_BLOCKING_VIOLATION"})\n'
        "    = PythonConstraintKinds\n====\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jar", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    jar = args.jar.resolve(strict=True)
    source_dir = Path(__file__).resolve().parent
    model_text = (source_dir / "plan_algorithm.tla").read_text()
    config = (
        (source_dir / "plan_model.cfg")
        .read_text()
        .replace("ModelSequenceConstraints", "CheckedSequenceConstraints")
        .replace("ModelAggregateLimits", "CheckedAggregateLimits")
    )
    config += "\nINVARIANT PythonConstraintCorrespondence\n"
    report: dict[str, object] = {
        "scope": "bounded model and Python sequence/aggregate correspondence",
        "actions": ACTIONS,
        "max_plan_steps": 3,
        "enumerated_plan_lengths": [0, 1, 2, 3, 4],
        "plans_per_variant": 121,
        "inputs_per_variant": 14762,
        "oracle": "all per-step verdict assignments and both external-blocker values",
        "jar_sha256": digest(jar),
        "model_sha256": digest(source_dir / "plan_algorithm.tla"),
        "config_sha256": digest(source_dir / "plan_model.cfg"),
        "runner_sha256": digest(Path(__file__)),
        "python_evaluator_sha256": digest(Path(plan_eval.__file__)),
        "python_version": sys.version.split()[0],
    }
    runs: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="aegis-plan-tlc-") as temp:
        temp_dir = Path(temp)
        for name in [*VARIANTS, "negative_sequence", "negative_termination"]:
            pairs, limits = VARIANTS.get(name, VARIANTS["standard"])
            run_dir = temp_dir / name
            run_dir.mkdir()
            changed_model = model_text
            expected_failure = ""
            if name == "negative_sequence":
                start = changed_model.index("SequenceViolated ==")
                end = changed_model.index("\nAggregateViolated ==", start)
                changed_model = (
                    changed_model[:start]
                    + (
                        "SequenceViolated ==\n"
                        "    \\E i \\in 1..Len(plan), j \\in 1..Len(plan):\n"
                        "        /\\ i > j\n"
                        "        /\\ <<plan[j], plan[i]>> \\in SequenceConstraints\n"
                    )
                    + changed_model[end:]
                )
                expected_failure = "Invariant PythonConstraintCorrespondence is violated"
            elif name == "negative_termination":
                changed_model = changed_model.replace(
                    "Next == HandleEmpty \\/ HandleOversize \\/ EvaluateSteps "
                    "\\/ CheckConstraints \\/ Aggregate",
                    "Next == HandleEmpty \\/ HandleOversize",
                )
                expected_failure = "Temporal properties were violated"
            (run_dir / "plan_algorithm.tla").write_text(changed_model)
            (run_dir / "plan_correspondence.tla").write_text(oracle_module(pairs, limits))
            (run_dir / "plan_model.cfg").write_text(config)
            command = [
                "java",
                "-XX:+UseParallelGC",
                "-Xmx2g",
                "-cp",
                str(jar),
                "tlc2.TLC",
                "-workers",
                "2",
                "-seed",
                "1",
                "-fp",
                "0",
                "-metadir",
                str(run_dir / "states"),
                "-config",
                "plan_model.cfg",
                "plan_correspondence.tla",
            ]
            result = subprocess.run(
                command, cwd=run_dir, capture_output=True, text=True, timeout=120
            )
            output = result.stdout + result.stderr
            success = (
                result.returncode != 0 and expected_failure in output
                if expected_failure
                else result.returncode == 0
                and "Model checking completed. No error has been found." in output
                and "Finished checking temporal properties" in output
            )
            portable = output.replace(str(temp_dir), "<temporary-models>")
            portable = portable.replace(str(Path.home()), "<user-home>")
            # TLC also reports its standard-library extraction directory.
            portable = re.sub(r"Parsing file .*/([^/\n]+\.tla)", r"Parsing file \1", portable)
            if args.output_dir:
                args.output_dir.mkdir(parents=True, exist_ok=True)
                (args.output_dir / f"{name}.txt").write_text(portable)
            runs.append(
                {
                    "name": name,
                    "passed": success,
                    "expected_failure": expected_failure or None,
                    "exit_code": result.returncode,
                }
            )
            print(f"{name}: {'PASS' if success else 'FAIL'}", flush=True)
            if not success:
                print(portable)
                raise SystemExit(1)
        report["runs"] = runs
        if args.output_dir:
            (args.output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print("All five bounded checks and both negative controls passed.")


if __name__ == "__main__":
    main()
