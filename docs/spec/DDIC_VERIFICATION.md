> Imported technical reference. Historical test counts
> describe earlier development states. Consult [limitations](../limitations.md)
> and [validation](../validation.md) for the current public snapshot.

# DDIC verification — evidence chain

This document records the four-layer verification approach for AEGIS against
Taylor Olson's *A Formal Theory of Norms* (Northwestern University, June 2025).
Original record: 2026-03-27. These layers support bounded claims; tests and model
files alone are not a universal correctness proof of the Python implementation.

## 1. Purpose

The question is what evidence supports the DDIC implementation. The chain starts
with dissertation examples, expands to a conflict matrix and a Cartesian test
space, and ends with a machine-checkable model. Each layer examines a different
class of errors within its stated assumptions.

## 2. Reference

- Chapter 3: definition of the Defeasible Deontic Inheritance Calculus.
- Chapter 6.4: implementation for norm-guided planning.
- Definitions 6.4.1–6.4.16: norm types, inference, exceptions and closure.
- Theorems 6.4.1–6.4.4: conflict resolution.
- Table 6.5: 16 conflict cases, p. 140.
- Examples 6.4.1–6.4.4: the Karli scenarios, pp. 135–138.

## 3. The legacy algorithm

`DDICEngine.evaluate()` in `aegis/engine/ddic.py` implements:

1. Filter applicable norms by agent and proposition.
2. Give non-defeasible moral axioms precedence (I4).
3. Order norms by specificity derived from `genls` depth.
4. Apply preemption: more specific norms defeat general conflicting norms.
5. Break remaining ties by cross-code precedence.
6. Return `UNDETERMINED` for unresolved conflicts.

The unified `evaluate_legacy_module()` in `aegis/engine/ddic_eval.py` applies
the legacy strategy to compiled DDIC formulas. The tests compare both paths.
This document distinguishes engine outcomes from public Guard verdicts.

## 4. Layer 1: Olson's examples

`tests/formal/test_olson_karli_examples.py` contains nine tests adapting four
scenarios in which Karli gives a care robot privacy instructions. The narratives
below are paraphrases.

### Example 6.4.1: permission with prohibitive closure

Karli permits telling her husband which medication she takes. The fixture has
`(permittedToDo companion (shareRecipe husband))` and no explicit prohibition.

| Query | Fixture expectation | Reason |
|---|---|---|
| shareRecipe to husband | PERMITTED | Explicit permission |
| shareMedicalRecord to husband | UNDECIDABLE in the normalized engine test | No matching norm |

Tests: `test_recipe_to_husband_permitted` and
`test_medical_record_to_husband_no_norm`. The public Guard can map missing
permission in a known domain to `FORBIDDEN/CWA_NO_PERMISSION`; do not confuse
that behavior with the normalized engine result.

### Example 6.4.2: a prohibition suppresses an obligation

Karli first requires sharing her health status with her children and later
prohibits sharing her medical record. The fixture gives the obligation
specificity 0 and the prohibition specificity 1. The more specific prohibition
wins by preemption, producing `FORBIDDEN`.

Test: `test_health_to_children_forbidden_after_prohibition`. The fixture adapts
the subsuming-prohibition case associated with Theorem 6.4.2.

### Example 6.4.3: a strictly narrower prohibition

Karli permits sharing her medical record but prohibits telling her husband
which medication she takes. Broad permission has specificity 0; the narrower
prohibition has specificity 2.

| Query | Expected result | Reason |
|---|---|---|
| General medical-record sharing | PERMITTED | Broad permission without a matching conflict |
| Medication information to husband | FORBIDDEN | More specific prohibition |

Tests: `test_medical_record_to_husband_permitted`,
`test_recipe_to_husband_forbidden`, and `test_order_independence`.
The last checks that input order does not change the result.

### Example 6.4.4: overlapping conflict

Karli permits medical-record sharing but prohibits upsetting her husband.
Neither behavior subsumes the other. The fixture separately permits record
sharing, forbids upsetting her husband, and returns `UNDECIDABLE` at the
unresolved overlap.

Tests: `test_medical_record_alone_permitted`,
`test_upset_husband_alone_forbidden`, and `test_intersection_undecidable`.

This is a documented legacy deviation: Olson's intersection case yields
impermissibility, whereas the fixture returns undecidability without an explicit
intersection relation. Both block execution under the Guard contract; they
support different explanations and repair routes.

## 5. Layer 2: Table 6.5

`tests/formal/test_olson_table_65.py` contains 16 adapted matrix cases and 16
cross-checks between the evaluators. The original record lists:

| Row | Theorem | N1 | Relation | N2 | DDIC result | AEGIS test result |
|---|---|---|---|---|---|---|
| 1 | 6.4.1 | Imp | = | Obl | Unknown | UNDECIDABLE ✓ |
| 2 | 6.4.1 | Imp | > | Obl | Unknown | FORBIDDEN ✓ |
| 3 | 6.4.1 | Imp | = | Opt | ¬Obl | UNDECIDABLE ✓ |
| 4 | 6.4.1 | Imp | > | Opt | ¬Obl | FORBIDDEN ✓ |
| 5 | 6.4.2 | Obl | = | Imp | Imp | UNDECIDABLE/FORBIDDEN ✓ |
| 6 | 6.4.2 | Obl | < | Imp | Imp | FORBIDDEN ✓ |
| 7 | 6.4.2 | Opt | = | Imp | Imp | UNDECIDABLE/FORBIDDEN ✓ |
| 8 | 6.4.2 | Opt | < | Imp | Imp | FORBIDDEN ✓ |
| 9 | 6.4.3 | Imp | < | Obl | Imp | FORBIDDEN ✓ |
| 10 | 6.4.3 | Obl | > | Imp | Imp | FORBIDDEN ✓ |
| 11 | 6.4.3 | Imp | < | Opt | Imp | FORBIDDEN ✓ |
| 12 | 6.4.3 | Opt | > | Imp | Imp | FORBIDDEN ✓ |
| 13 | 6.4.4 | Imp | ∩ | Obl | Imp | UNDECIDABLE/FORBIDDEN ✓ |
| 14 | 6.4.4 | Obl | ∩ | Imp | Imp | UNDECIDABLE/FORBIDDEN ✓ |
| 15 | 6.4.4 | Imp | ∩ | Opt | Imp | UNDECIDABLE/FORBIDDEN ✓ |
| 16 | 6.4.4 | Opt | ∩ | Imp | Imp | UNDECIDABLE/FORBIDDEN ✓ |

Notation: Imp = impermissible, Obl = obligatory, Opt = optional (mapped to
`PERMITTED` in these legacy tests). `=` is equal scope; `>` means N1 is more
specific; `<` means N2 is more specific; `∩` means overlap. Entries allowing
`UNDECIDABLE/FORBIDDEN` accept undecidability for unresolved ties and prohibition
where dominance is established. Such accepted alternatives are not exact
reproduction of every logical conclusion in Olson's table.

Cross-checks ensure the v1 and unified legacy paths agree for each adapted case.

## 6. Layer 3: the 216-combination matrix

`tests/formal/test_ddic_combinatorial.py` covers the Cartesian product:

| Dimension | Values | Count |
|---|---|---:|
| Modality pairs | P/F, F/P, O/F, F/O, O/P, P/O | 6 |
| Specificity relations | s1 > s2, s1 < s2, s1 = s2 | 3 |
| Defeasibility pairs | defeasible/defeasible, defeasible/axiom, axiom/defeasible, axiom/axiom | 4 |
| Code relations | same, c1 > c2, c1 < c2 | 3 |
| Total | | 216 |

Each case checks evaluator equivalence. Conflicting pairs also check an expected
outcome derived from the implemented precedence interpretation of Olson's rules:

```python
def expected_conflict(m1, s1, d1, c1, m2, s2, d2, c2, precedence):
    if not d1 and not d2:
        return None  # Conflicting axioms: undetermined.
    if not d1:
        return m1
    if not d2:
        return m2
    if s1 > s2:
        return m1
    if s2 > s1:
        return m2
    if precedence and c1 != c2:
        r1, r2 = rank(c1, precedence), rank(c2, precedence)
        if r1 > r2:
            return m1
        if r2 > r1:
            return m2
    return None
```

The snippet is explanatory pseudocode; `rank` represents the implementation's
code ranking. Obligation/permission pairs are nonconflicting in the logical
sense but can produce implementation-dependent legacy outcomes. Olson's conflict
theorems do not prescribe their exact output. Those cases check equivalence only,
not an independent theoretical oracle.

## 7. Layer 4: TLA+ model

`spec/formal/ddic_algorithm.tla` and `ddic_model.cfg` define a bounded state
machine with state `(norms, axioms, defeasible, surviving, defeated, result, step)`.

| Transition | Effect |
|---|---|
| Step2_SeparateAxioms | Separate axioms and defeasible norms |
| Step2b_AxiomCheck | Resolve immediately when axioms determine the result |
| Step2c_NoAxioms | Continue with defeasible norms |
| Step4_Preemption | Defeat less specific conflicting norms |
| Step5_Resolve | Resolve agreement or code precedence |

| Property | Meaning |
|---|---|
| TypeOK | State variables have the expected types |
| AxiomMonotonicity (I4) | A consistent applicable axiom determines the modality |
| ForbiddenDominance | An all-forbidden norm set yields prohibition |
| Theorem641 | More specific permission/obligation defeats a general prohibition |
| Theorem642 | More specific prohibition defeats general permission/obligation |
| Theorem644 | Equal specificity and code with a conflict yields undetermined |
| AlwaysTerminates | Eventually reach step 7; a temporal property |

Parameters: three modalities, specificity 0–3, two codes and at most four norms.
There are 48 norm configurations and subsets of up to four norms. TLC can explore
the reachable bounded states. No new TLC result is claimed by this publication.

```sh
# From spec/formal, with a local TLA+ toolchain:
java -jar tla2tools.jar ddic_algorithm.tla -config ddic_model.cfg
```

Agent/proposition matching is abstracted; applicability is assumed. General
intersection is not modeled, only equal propositions. Code precedence is bounded
to two codes. A four-norm model is not a universal proof for larger inputs or
proof that the Python implementation refines the model. Larger bounds, symmetry
reduction or inductive proofs would require additional work.

## 8. Additional verification

The following figures describe the historical test design; property trials and
repetitions are not separate pytest test items.

| Area | File | Method and historical scope |
|---|---|---|
| Axiom monotonicity I4 | `test_axiom_monotonicity.py` | 1–50 random defeasible norms plus one axiom; two properties with 200 trials each |
| Determinism I1 | `test_determinism_extended.py` | 100 repetitions per action type, 10 threads, 50 norm shuffles |
| Totality | `test_ddic_totality.py` | 200 trials with 1–100 norms; stress case of 1,000 norms |
| Duality I7 | `test_duality.py` | 100 property trials and fixed checks |
| Closed-world completeness | `test_cwa_completeness.py` | Enumerate registered action types without permission |
| Legacy evaluator equivalence | `tests/engine/test_ddic_legacy_equivalence.py` and `test_olson_conformance.py` | 10 focused cases plus 52 parametrized cases |
| Norm enumeration | `test_norm_enumeration.py` | Parameterized norm configurations |

The historical runs recorded no counterexamples or timeouts in these scopes.
The totality argument uses bounded input and O(n²) preemption with
`MAX_APPLICABLE_NORMS=10_000`. A passing finite test suite alone does not prove
termination for every possible implementation input.

## 9. Evidence summary

| Layer | Historical scope |
|---|---|
| Karli examples | 9 tests |
| Table 6.5 adaptations | 32 tests |
| Cartesian matrix | 216 tests |
| TLA+ model | Bounded specification; run TLC separately |
| Additional Olson conformance | 52 tests |

The original record reported 361 collected formal tests at its checkpoint.
Use the current test runner and [release record](../release.md) for present counts.

The evidence supports agreement on the tested examples and bounded parameter
space, observed determinism and axiom precedence, and equivalence of the two
legacy evaluators over those cases. It does not establish unrestricted
correctness, complete matching for all proposition structures, or a mechanized
proof of the implementation.

## 10. Documented deviations

1. **Legacy overlap:** unresolved intersection can yield `UNDECIDABLE` rather
   than Olson's impermissibility. V2 declared intersection relations are a
   separate capability.
2. **Closure:** the Guard uses prohibitive closure. In-domain absence of positive
   permission currently yields `FORBIDDEN/CWA_NO_PERMISSION`; out-of-domain
   or other unsupported cases may be undecidable. The legacy conflict reason
   also has a documented defect.
3. **Nonconflicting O/P pairs:** exact legacy outcomes are implementation-specific
   and are compared for equivalence rather than claimed as Olson-prescribed.

## 11. Further work

| Work item | Benefit | Original priority |
|---|---|---|
| Run TLC and record its result | Machine-checked bounded properties | High |
| Increase norm bounds to 6, 8 or 10 | Broader state exploration | Medium |
| Model general intersection | Check the intersection case explicitly | Medium |
| Inductive theorem-prover proof | Unbounded result with stated assumptions | Lower; substantial effort |
| Model agent/proposition matching | Formal treatment of applicability | Lower |

## 12. Implementation references

- `aegis/engine/ddic.py`: v1 six-step evaluator.
- `aegis/engine/ddic_eval.py`: unified evaluator.
- `aegis/engine/normframe_compile.py`: norm-frame compiler.
- `aegis/engine/pattern_matcher.py`: `unify` and `unify_terms`.
- [Chapter 6 conformance](OLSON_CH6_CONFORMANCE.md).
- [MELD specification](../_archive/MELD_SPEC.md).
- [Formal models](../../spec/formal/README.md).
