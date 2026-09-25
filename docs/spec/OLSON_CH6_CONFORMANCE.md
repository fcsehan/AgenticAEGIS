> Imported technical reference. Historical statuses,
> test counts and roadmap references describe earlier development states. See
> [limitations](../limitations.md) and [validation](../validation.md) for the
> public snapshot. Conformance labels below describe the original assessment,
> not a new independent verification of the dissertation.

# Olson Chapter 6 — conformance analysis

Comparison of Taylor Olson's *A Formal Theory of Norms*, Chapter 6
(implementation and empirical evaluation, pp. 102–175), with AEGIS.
Original assessment: 2026-03-22, with subsequent Epic 23/27/32 updates.

## Reading this document

- **CONFORMANT:** the assessed concept is implemented in AEGIS.
- **DELIBERATE DEVIATION:** a documented architectural decision excludes it.
- **OPEN:** an implementation or verification gap remains.

## 6.1 Cognitive architecture

**Status: DELIBERATE DEVIATION.** Olson uses the Companion Cognitive
Architecture, NextKB ontology, FIRE reasoning engine, an HTN planner and CNLU.
AEGIS implements its reasoning components in Python, following the decision to
use no external reasoning engines.

| Olson component | AEGIS counterpart | Source |
|---|---|---|
| NextKB ontology | KnowledgeBase fact store | `aegis/kb/knowledge_base.py` |
| FIRE with backward chaining and TMS | BPS-derived pattern matcher and JTMS | `aegis/engine/pattern_matcher.py`, `aegis/tms/jtms.py` |
| HTN planner | No planner; the Guard evaluates supplied actions and plans | `aegis/guard/` |
| CNLU parser | Declarative MELD, with separately reviewed authoring proposals | `aegis/kb/meld_loader.py` |

Builtins in `aegis/kb/builtins.py` implement closure for `isa` (instances),
`genls` (collection subsumption), `genlPreds` (predicate hierarchy) and
`negationPreds` (deontic pairs). The historical design specifies cycle detection
and a depth limit of 100. The objective is deterministic, auditable evaluation,
not an open-ended cognitive agent with abductive reasoning.

## 6.2 Norm frame representation

### 6.2.1 Norm frames (Definition 6.2.1)

**Status: CONFORMANT in the assessed representation.** Olson's four conceptual
slots map to AEGIS as follows:

| Olson slot | AEGIS field | Notes |
|---|---|---|
| Norm type | `NormFrame` class | Type represented by the data structure |
| Context | `proposition` tuple | Combined with behavior in v1; separate in v2 DDIC |
| Behavior | `proposition` tuple | Proposition head and arguments |
| Evaluation | `modality: DeonticModality` | Deontic status |

Additional fields are `code` (code of conduct), `agent_pattern` (role filter;
`*` matches all), `specificity` (hierarchy depth), `defeasible` (false for a
non-defeasible axiom), and `source` (MELD provenance).

| Operator | AEGIS modality | MELD predicates |
|---|---|---|
| Obligatory | `OBLIGATORY` | `oughtToDo`, `oughtToDo-WRT`, `oughtToBe` |
| Impermissible | `FORBIDDEN` | `forbiddenToDo`, `forbiddenToDo-WRT`, `forbiddenToBe` |
| Permissible | `PERMITTED` | `permittedToDo`, `permittedToDo-WRT`, `permittedToBe` |
| Optional | No separate modality | Legacy comparisons use `PERMITTED` |
| Non-optional | No separate modality | No dedicated representation |

The reduction to three modalities is a **DELIBERATE DEVIATION**. Optionality,
explicit permission and defeasibility must not be treated as interchangeable
logical concepts. A non-defeasible norm is an axiom; this alone is not a
representation of Olson's non-optionality operator.

### 6.2.2 Active norms (Definition 6.2.2)

Originally **OPEN**, subsequently recorded as completed by AEGIS-2308.
Olson activates a norm when the current context entails its context slot.
Legacy v1 uses proposition matching. V2 adds explicit context activation through
`context-subsumes`.

### 6.2.3 Scope (Definition 6.2.3)

The assessed correspondence uses proposition matching and hierarchy-derived
specificity to represent the behaviors to which a norm applies. This is not a
claim of unrestricted logical entailment.

## 6.3 Learning norms from natural language

**Status: DELIBERATE DEVIATION.** Olson's CNLU pipeline parses sentences,
disambiguates with abductive scoring and applies narrative function rules to
construct norm frames. The historical assessment cites 50 extraction rules and
96% F1 on 105 sentences, including two false positives and two false negatives.
Those figures describe Olson's experiment, not an AEGIS evaluation.

MELD is AEGIS's authoritative formal input. LLM-assisted authoring and DIP are
separate proposal paths requiring review; they do not reproduce CNLU or eliminate
natural-language interpretation error.

| Olson extraction step | MELD counterpart |
|---|---|
| 6.3.2.1 Deontic operators | Predicate to `DeonticModality.from_meld_predicate()` |
| 6.3.2.2 Behavior | ToDo argument 2 / ToBe argument 1 to proposition |
| 6.3.2.3 Context | WRT argument represented in the extracted proposition |
| 6.3.2.4 Norm construction | `NormFrame(code, agent, modality, proposition, ...)` |

Explicit syntax makes the evaluated representation reproducible. It does not
prove that a human or model translated the intended policy correctly.

## 6.4 DDIC for norm-guided planning

### 6.4.1–6.4.3 Norm types

The assessment maps obligations to `OBLIGATORY`, discretionary norms to the
legacy `PERMITTED` representation, and prohibitions to `FORBIDDEN`.

### 6.4.4 Normative beliefs

**Status: CONFORMANT in v2**, recorded by AEGIS-2301/2305. Legacy v1 expresses
normative conclusions through `NormStatus`. V2 separates testimony and belief
layers, including `testimony-obligatory`, `testimony-forbidden` and
`belief-obligatory`.

### 6.4.5 Entailment (Algorithm 2)

**Status: PARTIAL.** Olson reifies two CycL conjunctions in a temporary
microtheory and queries one against the other plus background knowledge. AEGIS
provides pattern matching, `unify_terms()`, prefix matching and transitive
`genls`/`isa` closure. It does not implement generic conjunction entailment with
reification. Guard claims must stay within that restricted matching scope.

### 6.4.6 Subsumption

**Status: CONFORMANT in the declared v2 relations.**
`ddic_eval._subsumes(sub, sup, relations, namespace)` checks
`behavior-subsumes` and `context-subsumes`. Legacy v1 approximates specificity
through a numeric comparison.

### 6.4.7 Intersection

**Status: CONFORMANT in the declared v2 relations.**
`ddic_eval._intersection(a, b, relations, namespace)` resolves declared
`behavior-intersects` and `context-intersects` relations. This does not remove
the legacy intersection limitation described in the verification document.

### 6.4.8 Temporal ordering

**Status: CONFORMANT in v2.** `ddic_eval._is_later(a, b, relations)` checks
`before` relations for lex-posterior defeat. Legacy v1 assumes a static rulebase.

### 6.4.9 Norm-guided plans

**Status: architectural abstraction of norm-guided plan evaluation.** Epic 27
introduced the plan API on 2026-05-08. Terminology was clarified on 2026-05-26
following Olson's feedback.

Olson's planner consults DDIC while selecting HTN decompositions. AEGIS receives
a caller-supplied plan through `Guard.plan_check(plan)` and returns a
`PlanVerdict`: `PERMITTED`, `FORBIDDEN` or `UNDECIDABLE`. The empirical planning
reference in Olson's work is a SocialBot in Microsoft Teams; AEGIS does not
replicate that planner or its experiment.

DDIC resolves conflicts among deontic action norms. Plan constraints form a
separate composition layer above those verdicts. AEGIS evaluates plans; it does
not generate them.

| Predicate | Planning correspondence | AEGIS check |
|---|---|---|
| `obligateSequence A B` | Ordering | `_check_obligate_sequence` |
| `forbidAggregate A N` | Aggregate bounds | `_check_forbid_aggregate` |
| `obligateWithin A T` | Declared timing | `_check_obligate_within` |
| `requirePrecondition A P` | Preconditions | State patterns with `unify_terms` |

Limits remain explicit:

1. Obligation-to-intention is open in Olson's dissertation, p. 141, footnote 48.
   AEGIS provides `require_obligation_coverage=False` as an opt-in switch.
2. Timing checks caller-declared `scheduled_duration_s`, not wall-clock execution.
3. Aggregates apply within one plan, not across an entire session.
4. `same-session` and `end-of-plan` are accepted as satisfied by the in-plan
   evaluator; they do not implement cross-plan lifecycle enforcement.

Evidence includes plan conformance tests, the five properties in
`spec/formal/plan_algorithm.tla`, and DevOps fixtures. Current semantics and
historical test counts are documented in
[plan governance](../reference/PLAN_LEVEL_GOVERNANCE.md).

### 6.4.10–6.4.16 Inference rules and exceptions

| Definition | Concept | Legacy v1 | V2 DDIC |
|---|---|---|---|
| 6.4.10 | Permission rule | Most specific permission | Explicit R1 |
| 6.4.11 | Later subsuming prohibition | Preemption | `before` and `behavior-subsumes` |
| 6.4.12 | Nonsubsuming prohibition | Preemption | Explicit defeat checks |
| 6.4.13 | Prohibitive closure | Guard fail-closed behavior | Explicitly representable |
| 6.4.14 | Impermissibility rule | Most specific prohibition | Explicit R2 |
| 6.4.15 | Later permission | Preemption | `before` and `behavior-subsumes` |
| 6.4.16 | Permissive closure | Permissions must be supplied | Explicitly representable in the calculus |

Olson treats the two closure assumptions symmetrically. The Guard authorizes
execution only on positive permission; permissive closure is excluded from its
enforcement contract. See [limitations](../limitations.md) for the current
`CWA_NO_PERMISSION` behavior and its distinction from explicit prohibition.

### Theorems 6.4.1–6.4.4 and legacy conflict resolution

The historical assessment relates the six-step legacy algorithm to Olson's
conflict-resolution theorems:

1. Filter norms by agent and proposition.
2. Give non-defeasible axioms precedence.
3. Order by specificity.
4. Apply preemption by more specific norms.
5. Use code precedence to break remaining ties.
6. Return an undetermined result for unresolved conflicts.

The test suite includes `test_ddic_soundness.py`,
`test_axiom_monotonicity.py` and 52 historical parametrized conformance tests
covering both `DDICEngine` and `evaluate_legacy_module()`.

| Theorem | Assessed concept | Legacy steps |
|---|---|---|
| 6.4.1 | Defeat involving subsumed permissions | 2 and 4 |
| 6.4.2 | Suppression by subsuming prohibitions | 4 |
| 6.4.3 | Exceptions from strictly subsumed prohibitions | 4 and 5 |
| 6.4.4 | Overlapping conflicts without subsumption | 6 |

This is an implementation correspondence, subject to the documented legacy
intersection and closure deviations, not an unrestricted equivalence theorem.

## 6.5 Robust norm adaptation with belief functions

**Status: DELIBERATE DEVIATION.** Olson uses Dempster–Shafer belief functions:
a deontic frame of discernment, mass assignments, DS-BELIEVED (Algorithm 3),
CPI/CPI-P population inheritance and the Moral Conventional Transgression
experiment. Related predicates include `normativeKnowledge`,
`normativeAttitude`, `normativeBelief` and the axiomatic `MoralNorm` class.

AEGIS uses deterministic evaluation. Norms have fixed modalities rather than
probabilistic mass assignments. Conflicts use specificity and precedence;
unresolved cases produce a discrete verdict. The Guard treats the loaded
rulebase as authoritative and does not model a population negotiating beliefs.

| Olson concept | AEGIS treatment |
|---|---|
| Belief-function mass assignment | Outside the deterministic Guard scope |
| CPI/CPI-P population inheritance | No population model |
| Belief versus knowledge in this adaptation model | No corresponding probabilistic adaptation layer |
| MoralNorm | Analogous non-defeasible norm flag |
| Moral Conventional Transgression experiment | Outside the Guard's adversarial evaluation scope |

The v2 testimony/belief distinction does not imply implementation of Olson's
probabilistic norm-adaptation model.

## Recorded implementation milestones

| Ticket | Component | Historical status |
|---|---|---|
| AEGIS-2306 | Priority/defeater engine, lex posterior | DONE, 2026-05-08 |
| AEGIS-2307 | Direct, indirect and overlapping conflict ontology | DONE, 2026-05-08 |
| AEGIS-2308 | Context activation | DONE |
| AEGIS-2309 | Compatibility layer and evaluation mode | DONE, 2026-05-08 |
| AEGIS-2310 | Olson conformance tests | DONE, 52 tests |
| AEGIS-2313 | Action-to-DDIC query mapping | DONE, 2026-05-08 |
| AEGIS-2314 | Defeat-aware justification chains | DONE, 2026-05-08 |
| AEGIS-2315 | Mixed-mode loading policy | DONE, 2026-05-08 |

Other recorded components include `unify_terms()`, the v1-to-DDICModule compiler
and the unified evaluation pipeline. Original development commits are not part
of this repository's fresh history.

## Specificity from norm space to action space (Epic 32)

Olson's specificity concerns norm hierarchies. Epic 32 applies a related
selection principle to candidate actions through `Guard.check_candidates`:

| DDIC concept | Candidate-action use |
|---|---|
| More specific norms defeat general norms | Prefer narrower permitted actions |
| Behavior subsumption | MELD `narrowerThan` between action types |
| Conflict resolution | Candidate tie-breaking |
| Declared behavior relations | Explicit `SubsumptionGraph` |

This selection is separated from the caller's planner. Its guarantee requires
both a correctly declared MELD subsumption graph and a complete candidate set
from the caller. Under those assumptions, AEGIS deterministically selects the
most specific permitted candidate. The Guard does not establish either
assumption from natural language.

## References

- Taylor Olson, *A Formal Theory of Norms*, Northwestern University, June 2025,
  Chapter 6, pp. 102–175.
- [DDIC verification](DDIC_VERIFICATION.md).
- [MELD specification](../_archive/MELD_SPEC.md).
- [Architecture separation](../../spec/AEGIS_v2_ARCHITECTURE_SEPARATION.md).
- [Guarantee boundary](../assessment/GUARANTEE_BOUNDARY.md).
