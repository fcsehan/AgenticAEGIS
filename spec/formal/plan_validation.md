# Plan model: bounded validation

PAPER-RW-013, 2026-11-01. Validation prepared during revision of the unpublished
plan-governance manuscript. The update fixes model syntax/configuration,
sequence semantics, and the determinism/termination properties. It changes
formal evidence; the Python runtime and historical latency baseline are unchanged.

## Reproduce

Use Python 3.12+ with AgenticAEGIS installed, Java 11+, and the official
[TLA+ tools JAR, release v1.7.4](https://github.com/tlaplus/tlaplus/releases/tag/v1.7.4).
The checked JAR reports **TLC 2.19, 8 August 2024, revision 5a47802**; its SHA-256
is `936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88`.
The tool release number and TLC's version number are different identifiers.

From a repository checkout:

```sh
python spec/formal/check_plan_model.py --jar /path/to/tla2tools.jar --output-dir /tmp/plan-evidence
```

From the extracted formal supplement, using the runtime's Python environment:

```sh
python check_plan_model.py --jar /path/to/tla2tools.jar --output-dir /tmp/plan-evidence
```

A standalone model-only check, without Python correspondence, is also possible:

```sh
cd spec/formal
java -XX:+UseParallelGC -cp /path/to/tla2tools.jar tlc2.TLC -config plan_model.cfg plan_algorithm.tla
```

The runner generates temporary TLA+ oracle tables by calling the actual Python
sequence and aggregate checkers. TLC compares these outputs with its own
constraint predicates. It enumerates every sequence of lengths 0 through 4 over
`{a,b,c}` (121 sequences), every per-step verdict assignment, and both values
of an external-blocker flag. The plan limit is 3, so length 4 exercises the
oversize branch. Inputs remain fixed after initialization.

## Checked configurations and properties

Five configurations cover ordinary `a -> b` ordering, no sequence constraint,
cyclic `a -> b` / `b -> a` constraints, a self-pair `a -> a`, and a zero
aggregate cap. Other aggregate caps are 1 for `a` and 2 for `b`/`c`.
Each configuration explores 14,762 initial inputs and 32,800 reachable states.
All five complete with no invariant or temporal-property violation.

- `TypeOK`: well-typed state throughout execution.
- `Pl_1_Determinism`: terminal agreement with a total function of fixed input,
  rather than merely membership in the decision set. Together with termination,
  this fixes a unique final verdict per input in the bounded model.
- `Pl_2_PermittedSoundness`: permission implies all steps permitted and no blocker.
- `Pl_3_ForbiddenStepDominates`: a forbidden oracle step blocks an evaluable plan.
- `Pl_4_BlockingViolationDominates`: a modeled blocker prevents permission.
- `SentinelDecisions`: empty plans forbidden, oversize plans undecidable.
- `FailClosedUndecidability`: undecidability is preserved without a stronger blocker.
- `Pl_5_Termination`: `<>(state = "Done")`, a **temporal property** under weak
  fairness, not an implication that assumes termination has already occurred.
- `PythonConstraintCorrespondence`: matching sequence/aggregate violation kinds
  for all 121 sequences in every configuration, including oversize sequences.

Sequence ordering is conditional on both types occurring: no B may precede the
first A; a later repetition of A is allowed. Missing A or B is not an ordering
violation. A self-pair never violates this check, matching the Python evaluator.
Existence obligations and preconditions are separate checks.

## Negative controls and evidence

The runner also requires two deliberately broken models to fail:

1. The former reversed sequence predicate must violate Python correspondence.
2. Removing progress for ordinary plans must violate temporal termination.

A nonzero tool exit alone is insufficient: the expected diagnostic must occur.
Successful runs must report both completed model checking and temporal checking.
The portable transcripts and checksum-bound report are in `plan_evidence/`.
The report identifies the exact Python evaluator used for correspondence.

## Limits

These are exhaustive checks of five finite configurations, not an unbounded
proof, a mechanized refinement proof of Python, or verification of an LLM host.
DDIC is abstracted by arbitrary per-step verdicts. Timing and caller-state
preconditions are represented by a fixed Boolean blocker; their detailed
semantics and obligation coverage are not modeled. Python regression tests
remain independent evidence. Deadlock detection is disabled because Done is
terminal; temporal checking is enabled and catches stalled nonterminal runs.
