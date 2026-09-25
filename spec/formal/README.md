# DDIC algorithm — TLA+ formal specification

Machine-checkable specification of the six-step DDIC algorithm in
`aegis/engine/ddic.py`. These files define models and properties; their presence
does not establish a successful TLC run for the current release.

## Files

| File | Contents |
|---|---|
| `ddic_algorithm.tla` | Algorithm specification and invariants |
| `ddic_model.cfg` | TLC model-checking configuration |

## Specified properties

| Property | Type | Olson reference |
|---|---|---|
| TypeOK | Invariant | Type safety |
| AxiomMonotonicity (I4) | Invariant | Chapter 3.2 |
| ForbiddenDominance | Invariant | Prohibitive closure |
| Theorem641 | Invariant | Chapter 6.4.2, p. 135 |
| Theorem642 | Invariant | Chapter 6.4.2, p. 136 |
| Theorem644 | Invariant | Chapter 6.4.2, p. 138 |
| AlwaysTerminates | Temporal | Totality |

## Model parameters

```text
Modalities = {OBLIGATORY, FORBIDDEN, PERMITTED}
MaxSpecificity = 3 (0..3)
Codes = {CodeA, CodeB}
MaxNorms = 4
```

With three modalities, four specificity levels, two defeasibility values and
two codes, there are 3 × 4 × 2 × 2 = 48 possible norms. The model considers
subsets of up to four norms.

## Running the model

```sh
# TLA+ Toolbox or a command-line installation:
tlc ddic_algorithm.tla -config ddic_model.cfg

# Alternatively, use tla2tools.jar:
java -jar tla2tools.jar ddic_algorithm.tla -config ddic_model.cfg
```

## Limitations

- Agent and proposition matching are abstracted. Input norms are assumed to be
  applicable already, corresponding to step 1.
- Intersection in Theorem 6.4.4 is not modeled; only equal propositions are covered.
- Code precedence is limited to two codes.

## Plan algorithm (AEGIS-2715, Epic 27)

The separate plan model abstracts the evaluation pipeline in
`aegis/engine/plan_eval.py` and `aegis/guard/plan_pipeline.py`. It sits alongside
the DDIC model: per-step decisions are treated as oracle input and composed with
plan constraints.

### Files

| File | Contents |
|---|---|
| `plan_algorithm.tla` | Plan pipeline and invariants Pl-1 through Pl-5 |
| `plan_model.cfg` | TLC configuration |

### Specified properties

| Property | Meaning |
|---|---|
| `Pl_1_Determinism` | `state=Done ⇒ planVerdict ∈ PlanDecisions`; a valid decision in the final state |
| `Pl_2_PermittedSoundness` | A permitted plan has no forbidden/undecidable step or blocking violation |
| `Pl_3_ForbiddenStepDominates` | Any forbidden step makes the plan forbidden |
| `Pl_4_BlockingViolationDominates` | A sequence, aggregate or precondition violation makes the plan forbidden |
| `Pl_5_Termination` | Bounded plans reach Done; oversized plans are undecidable and empty plans forbidden |

### Model parameters

```text
Actions = {a, b, c}
Decisions = {PERMITTED, FORBIDDEN, UNDECIDABLE}
MaxPlanSteps = 3
SequenceConstraints = {<<a, b>>}
AggregateLimits = [x \in {a,b,c} |-> 5]
```

The configuration is small to allow exhaustive exploration. State space grows
exponentially with `MaxPlanSteps`.

```sh
java -jar tla2tools.jar plan_algorithm.tla -config plan_model.cfg
```

### Code-to-model correspondence

- `state="Init"`: entry to `PlanPipeline.run`.
- `HandleEmpty`: an empty plan returns `FORBIDDEN`.
- `HandleOversize`: exceeded limits return `UNDECIDABLE`.
- `EvaluateSteps`: `tuple(self._guard.check(s.action) for s in plan.steps)`.
- `CheckConstraints`: plan checks in `evaluate_plan_module`.
- `Aggregate`: `_aggregate_plan_decision` aggregation table.
- `state="Done"`: return `PlanVerdict(...)`.

### Limitations

- `StepDecisionMap` abstracts per-step DDIC reasoning. The models separately
  examine DDIC decisions and their plan-level composition; this is not a proof
  that the Python implementation refines their composition.
- Timing (`obligateWithin`) and state (`requirePrecondition`) are abstracted by
  the Boolean sentinel `NoBlockingViolation`. Full argument semantics would
  make the TLC state space too large for this configuration.
- Obligation coverage is not modeled; the code provides it as an opt-in feature
  disabled by default.
