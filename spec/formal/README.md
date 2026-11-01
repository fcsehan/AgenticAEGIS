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

## Plan algorithm: bounded validation (PAPER-RW-013)

The plan model checks safety properties and temporal termination under weak
fairness, with arbitrary per-step oracle decisions.

See [plan validation](plan_validation.md) for the exact scope, tool version,
reproduction commands, five bounded configurations, Python constraint
correspondence, and two negative controls. Portable results are in
[plan_evidence/report.json](plan_evidence/report.json).

The model and validation evidence are also packaged as a formal supplement to
the unpublished plan-governance preprint. This repository update changes the
formal model and its validation; the Python runtime is unchanged.
