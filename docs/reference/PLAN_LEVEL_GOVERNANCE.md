> Imported technical reference. Historical test counts
> and roadmap references describe earlier development states; see
> [limitations](../limitations.md) and [validation](../validation.md) for the
> public snapshot.

# Plan-level governance

Epic 27 closeout reference for the plan semantics of the AEGIS Guard.
Original checkpoint: 2026-05-09, with 22 of 22 tickets recorded complete.

## 1. Motivation

Olson's Chapter 6.4 describes norm-guided HTN planning: a planner consults the
DDIC belief base during decomposition. The empirical reference is a SocialBot
in Microsoft Teams. AEGIS abstracts plan evaluation into a separate Guard API;
it does not reproduce that planner.

Before Epic 27, individual action checks did not express ordering, aggregate
limits, declared state preconditions, or plan-wide obligation coverage. Callers
such as HTN planners, BPMN engines, CI/CD pipelines and LLM tool chains had to
reduce their plans to isolated checks. Individually permitted steps can also
combine into a prohibited plan, and a changed step can invalidate earlier
approval. Plan checking and execution tokens address these distinct problems.

`Guard.plan_check(Plan) -> PlanVerdict` adds plan evaluation while keeping plan
generation with the caller. Obligation coverage remains explicitly opt-in.

## 2. Design principle

Every effective modeled action, information and disclosure path must be
mediated by a formal, fail-closed, auditable Guard. AEGIS evaluates caller-supplied
plans; it does not formulate them. DDIC resolves action-norm conflicts, while
plan constraints compose those action decisions at the Guard boundary.

## 3. Data model

`aegis/guard/plan.py` uses frozen dataclasses with slots. The essential fields are:

```text
StateSnapshot
  fields: dict[str, Any]             # Caller-declared state; trust boundary I3

PlanStep
  action: Action
  step_id: str
  scheduled_duration_s: float
  pre_state: StateSnapshot
  post_state: StateSnapshot

Plan
  steps: tuple[PlanStep, ...]
  initial_state: StateSnapshot
  plan_id: str
  from_action(action) -> single-step plan
  to_facts() -> facts
  validate_limits() -> limit violations
```

`PlanVerdict` in `aegis/guard/verdict.py` contains `plan_decision`,
`per_step_verdicts`, `violations`, `reason_summary` and `evaluation_mode`.
`PlanDecision` is `PERMITTED`, `FORBIDDEN` or `UNDECIDABLE`.

### Violation types

| ViolationType | Source | Blocking |
|---|---|---|
| SEQUENCE_VIOLATION | obligateSequence | Yes |
| AGGREGATE_VIOLATION | forbidAggregate | Yes |
| TIMING_VIOLATION | obligateWithin | Yes |
| PRECONDITION_VIOLATION | requirePrecondition | Yes |
| STEP_FORBIDDEN | Forbidden step verdict | Yes |
| STEP_UNDECIDABLE | Undecidable step verdict | No; prevents permission |
| OBLIGATION_UNCOVERED | oughtToDo with coverage enabled | Yes |
| EMPTY_PLAN | Empty plan | Yes |

## 4. MELD predicates

### obligateSequence

`(obligateSequence ?predecessor ?successor)` requires every successor occurrence
to follow at least one predecessor occurrence. It is **conditional on
co-occurrence**: if only one of the two action types is present, this constraint
alone produces no violation.

```lisp
(obligateSequence runTests deploy)
```

### forbidAggregate

`(forbidAggregate ?action-type ?max-count)` limits the count of an action type.
The bound is an integer at least zero; zero prohibits every occurrence.

```lisp
(forbidAggregate deployArtifact 3)
(forbidAggregate forceModifyRepository 0)
```

### obligateWithin

`(obligateWithin ?action-type ?timeframe)` supports:

- `immediate`: the step must be at index 0.
- `same-session` and `end-of-plan`: accepted as satisfied by this in-plan
  evaluator; cross-plan lifecycle enforcement is not implemented.
- Integer N: the cumulative declared `scheduled_duration_s` before the first
  occurrence must be at most N seconds.

```lisp
(obligateWithin emergencyRollback immediate)
(obligateWithin deployArtifact 1800)
```

### requirePrecondition

`(requirePrecondition ?action-type ?precondition)` matches a state predicate
pattern against the merged pre-state using `unify_terms`.

```lisp
(requirePrecondition deployArtifact (testStatus passed))
(requirePrecondition modifySensitiveConfig (approvalFrom reviewer))
```

### Schema spelling

| V1 camelCase | V2 kebab-case |
|---|---|
| `obligateSequence` | `obligate-sequence` |
| `forbidAggregate` | `forbid-aggregate` |
| `obligateWithin` | `obligate-within` |
| `requirePrecondition` | `require-precondition` |

The v2 parser accepts both forms and normalizes to kebab-case in the IR.

## 5. Evaluation

Conceptual algorithm:

```python
def plan_check(plan):
    if plan.validate_limits():
        return UNDECIDABLE("d_007_limit")
    if not plan.steps:
        return FORBIDDEN("empty_plan")
    per_step_verdicts = [guard.check(step.action) for step in plan.steps]
    plan_view = build_plan_view(plan)
    core_result = evaluate_plan_module(module, plan_view)
    return aggregate(per_step_verdicts, core_result)
```

### Aggregation

| Step verdicts | Plan constraint | Plan decision |
|---|---|---|
| All PERMITTED | No violation | PERMITTED |
| All PERMITTED | Blocking violation | FORBIDDEN |
| Any FORBIDDEN | Any | FORBIDDEN |
| No FORBIDDEN, at least one UNDECIDABLE | No blocking violation | UNDECIDABLE |
| No FORBIDDEN, at least one UNDECIDABLE | Blocking violation | FORBIDDEN |

An undecidable step does not override a known blocking constraint violation.

### Check order in evaluate_plan_module

1. Delegate step reasoning to `evaluate_legacy_module` or the scoped v2
   `evaluate_ddic_module`; record forbidden and undecidable step outcomes.
2. Check step preconditions against `merged_pre`.
3. Check sequence constraints using action indices.
4. Count actions for aggregate constraints.
5. Check cumulative declared durations.
6. Check obligation coverage only when `module.require_obligation_coverage` is true.

For each step, state combines `initial_state`, preceding post-states and the
step's pre-state, with later layers overriding earlier values. These are declared
facts, not independently observed execution state.

## 6. Backward compatibility

The Pl-Aeq property states:

```text
Guard.plan_check(Plan.from_action(a)).per_step_verdicts[0].decision
  == Guard.check(a).decision
```

`Plan.from_action(a)` constructs a single step; the plan pipeline calls the same
`Guard.check` path for that step. This concerns the **step verdict**; a plan-level
constraint can still change the overall plan decision.

The historical `test_plan_equivalence.py` suite contains 19 tests using DevOps
action/agent cases and synthetic modality coverage. The original migration
required no changes to six existing domains, over 1,300 tests or 23 red-team
scenarios. Hosts without plan support can keep the action API; plan-aware
adapters call `plan_check` where path semantics matter.

## 7. DevOps reference domain

`aegis/domains/devops/DevOpsPlanNormsMt.meld` contains these 12 plan constraints:

```lisp
;; Sequence
(obligateSequence buildArtifact testArtifact)
(obligateSequence testArtifact deployArtifact)
(obligateSequence requestApproval modifySensitiveConfig)

;; Aggregate limits
(forbidAggregate forceModifyRepository 0)
(forbidAggregate executeRemoteCode 0)
(forbidAggregate modifySensitiveConfig 1)
(forbidAggregate deployArtifact 3)

;; Timing
(obligateWithin emergencyRollback immediate)
(obligateWithin deployArtifact 1800)

;; Preconditions
(requirePrecondition deployArtifact (testStatus passed))
(requirePrecondition modifySensitiveConfig (approvalFrom reviewer))
(requirePrecondition forceModifyRepository (approvalFrom emergencyBreakGlass))
```

An additional `(oughtToDo ciAgent reportIncident)` provides the opt-in obligation
coverage trigger for RT-PLAN-06; it is not a thirteenth plan predicate.

Ten JSON fixtures in `tests/fixtures/devops_plans/` cover a happy path, reversed
sequence, aggregate overflow, force-push, missing preconditions, late rollback,
empty plan, a realistic 20-step plan, single-action compatibility and tampering.
The historical `tests/domains/test_devops_plan_norms.py` suite contains 13 tests
for these paths and domain loading.

## 8. Plan execution permits

`PlanPermitToken` in `aegis/hardening/permit.py` is frozen and contains:

| Field | Type | Meaning |
|---|---|---|
| token_id | str | 32 hexadecimal characters from `secrets.token_hex(16)` |
| plan_id | str | Plan identifier |
| expected_step_hashes | tuple[str, ...] | Canonical action hash per step |
| consumed_step_indices | frozenset[int] | Steps already consumed |
| issued_at | float | Monotonic issue time |
| ttl_seconds | float | Lifetime, 30 seconds by default |
| invalidated | bool | Permanent invalidation flag |

A hash mismatch in `consume_plan_step` permanently invalidates the token, so
later steps cannot execute even if their hashes match. This prevents continued
execution after plan tampering within the mediated executor.

`PlanActionExecutor` in `aegis/api/plan_executor.py` performs:

1. `Guard.plan_check(plan)` before execution.
2. No step executor calls for a nonpermitted plan.
3. Issue a token with step hashes for a permitted plan.
4. Consume/check each step hash before invoking its executor.
5. On mismatch, runtime exception or missing executor: invalidate, abort and
   return a partial result.

The host must use this path consistently; the library cannot prevent effects
executed through an unmediated host path.

## 9. Verification

### TLA+ model

`spec/formal/plan_algorithm.tla` models the pipeline with:

| Property | Meaning |
|---|---|
| Pl_1_Determinism | A completed state has a member of PlanDecisions |
| Pl_2_PermittedSoundness | Permission implies no blocking step or constraint issue |
| Pl_3_ForbiddenStepDominates | A forbidden step makes the plan forbidden |
| Pl_4_BlockingViolationDominates | A blocking violation makes the plan forbidden |
| Pl_5_Termination | Termination, with oversized/empty-plan handling |

The small configuration uses three action symbols and `MaxPlanSteps=3`.

```sh
java -jar tla2tools.jar plan_algorithm.tla -config plan_model.cfg
```

Model files are separate evidence from a completed TLC run or a proof of Python
refinement. See [formal model limitations](../../spec/formal/README.md).

### Historical test inventory

| File | Tests | Property |
|---|---:|---|
| `test_plan_equivalence.py` | 19 | Pl-Aeq |
| `test_plan_soundness.py` | 23 | Pl-Sound-1 through 7 |
| `test_plan_totality.py` | 10 | Totality and determinism |
| `test_olson_planning_examples.py` | 6 | Five Karli scenarios represented as plans |

The closeout records 58 formal plan tests plus 52 core evaluation, 21 pipeline,
17 executor, 13 DevOps norm, 16 DevOps E2E, 13 red-team, seven CLI and 24 adapter
tests: 221 added tests at that checkpoint. Consult the current release record
for present collected totals.

Six canonical adversarial scenarios, RT-PLAN-01 through 06, are defined in
`aegis/redteam/plan_scenarios.py`. The target is zero mediated execution bypasses.
RT-PLAN-04, state fabrication, is advisory evidence of the caller-state boundary.

## 10. Caller integration

### Tool-chain LLM

`aegis/integrations/opencode_plan_adapter.py` converts `OpenCodeToolCall` lists
into plans. Its action mapping follows the original TypeScript `resolveAction`
order plus seven CI/CD patterns. The separate OpenCode fork used the same mapping
and `POST /v1/plan_check`; that fork is not included in this repository.

### CI/CD

Use `aegis plan-check <plan.json> --domains <dir>` as a deployment gate.
Exit codes: 0 permitted, 1 forbidden, 2 undecidable, 3 runtime/argument error.

```yaml
- name: AEGIS plan-check
  run: aegis plan-check pipeline.json --domains aegis/domains/devops
```

### HTN planner

A caller can check after each decomposition: expand on permission, backtrack on
prohibition, escalate on undecidability. The caller implements the planner;
AEGIS provides verdicts.

### BPMN concept mapping

| BPMN concept | AEGIS concept |
|---|---|
| Task | PlanStep |
| Sequence flow | obligateSequence |
| Exclusive gateway | Proposed future conditional step support |
| Timer event | obligateWithin, subject to declared-time limits |

A production BPMN integration is separate future work.

## 11. Limits and residual risks

- Timing uses declared durations, not wall-clock enforcement.
- State snapshots are caller assertions. The Guard checks consistency against
  declared state, not truth in the external world (boundary I3).
- Aggregate limits are per plan; splitting actions across plans remains a risk.
- `same-session` and `end-of-plan` do not enforce cross-plan lifecycle rules.
- Obligation-to-intention remains open; coverage defaults to false, consistent
  with the open question on p. 141, footnote 48 of Olson's dissertation.

| ID | Risk | Control or remaining work |
|---|---|---|
| R-1 | Oversized plan denial of service | 500-step hard cap and byte budget |
| R-2 | Aggregate evasion across plans | Future session-level aggregation |
| R-3 | Plan tampering | Permit hash validation |
| R-4 | Fabricated state | Explicit trust boundary and declared-state audit |
| R-5 | Evaluation cost above budget | Performance tests and step cap |

Historical Apple Silicon measurements reported 840 microseconds for 10 steps,
8.2 ms for 100 and 40.7 ms for 500, against budgets of 5, 50 and 500 ms. These
are checkpoint-specific measurements, not performance guarantees for other
hardware, rulebases or deployments.

## 12. Domain migration outline

The original follow-up proposed:

1. IFC: classification before disclosure.
2. Pharma: trial/report sequence and review-board approval precondition.
3. Sanctions: sanctions check before shipment.
4. Legal/GDPR: consent before processing and declared 72-hour reporting deadlines.
5. IAMission: approval sequences and classification-dependent aggregate bounds.

For each domain, identify the intended constraints, implement them in MELD and
verify positive and negative scenarios. These are modeling examples, not a claim
that the sample domains implement all applicable obligations.

## Related references

- [Olson conformance](../spec/OLSON_CH6_CONFORMANCE.md), section 6.4.9.
- [Guarantee boundary](../assessment/GUARANTEE_BOUNDARY.md).
- [MELD specification](../_archive/MELD_SPEC.md).
- `aegis/guard/plan.py`, `aegis/guard/plan_pipeline.py`,
  `aegis/engine/plan_eval.py`, `aegis/api/plan_executor.py`.
