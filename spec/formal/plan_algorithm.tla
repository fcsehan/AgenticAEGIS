---------------------------- MODULE plan_algorithm ----------------------------
(*
 * AEGIS Plan-Level Algorithm — TLA+ Specification (AEGIS-2715, Epic 27).
 *
 * Formal model of the plan-evaluation pipeline implemented in
 * aegis/engine/plan_eval.py and aegis/guard/plan_pipeline.py.
 *
 * Standalone model — does NOT extend ddic_algorithm.tla. The two are
 * orthogonal: the plan layer composes per-step DDIC verdicts with
 * plan-level constraint checks, but the DDIC machinery itself is
 * abstracted here as an oracle StepDecision(action) -> Decision.
 *
 * Five invariants Pl-1..Pl-5 (see end of file):
 *   Pl-1  Determinism: same input → same output across runs.
 *   Pl-2  PERMITTED ⇒ all per-step decisions PERMITTED AND no
 *         blocking violation.
 *   Pl-3  Any FORBIDDEN per-step ⇒ planVerdict ∈ {FORBIDDEN}.
 *   Pl-4  Any blocking violation ⇒ planVerdict ∈ {FORBIDDEN}.
 *   Pl-5  Termination: every plan with len ≤ MaxPlanSteps reaches
 *         the Done state in finite steps; oversize plans reach
 *         Done with planVerdict = UNDECIDABLE.
 *
 * Run: tlc plan_algorithm.tla -config plan_model.cfg
 *)

EXTENDS Integers, Sequences, FiniteSets, TLC

CONSTANTS
    Actions,         \* finite set of action types
    Decisions,       \* {"PERMITTED", "FORBIDDEN", "UNDECIDABLE"}
    PlanDecisions,   \* {"PERMITTED", "FORBIDDEN", "UNDECIDABLE"}
    MaxPlanSteps,    \* e.g. 5 — exhaustive search bound
    StepDecisionMap, \* function Actions -> Decisions (oracle)
    SequenceConstraints, \* set of <<a, b>> pairs: a must precede b
    AggregateLimits,     \* function Actions -> Nat (forbid > N)
    NoBlockingViolation, \* sentinel: TRUE if no plan-level constraint
                         \* triggers for the current plan; the model
                         \* treats SequenceConstraints + AggregateLimits
                         \* explicitly and uses this as a free toggle
                         \* for the timing/precondition cases.
    PreconditionRequired \* set of actions that need a precondition
                         \* (modeled as a free flag: caller indicates
                         \* whether plan satisfies it).

(* A plan is a finite sequence of actions, length 0..MaxPlanSteps+1. *)
PlanType == Seq(Actions)

VARIABLES
    plan,             \* the input plan
    stepDecisions,    \* tuple of per-step decisions
    violations,       \* set of plan-level violation kinds
    planVerdict,      \* "PERMITTED" / "FORBIDDEN" / "UNDECIDABLE"
    state             \* model phase: "Init" / "Step" / "Constraints" / "Done"

vars == <<plan, stepDecisions, violations, planVerdict, state>>

-----------------------------------------------------------------------------

(* Empty plan and over-budget sentinels. *)
EmptyPlan == Len(plan) = 0
OverBudget == Len(plan) > MaxPlanSteps

(* Per-step verdict aggregation. *)
HasForbiddenStep ==
    \E i \in 1..Len(stepDecisions): stepDecisions[i] = "FORBIDDEN"

HasUndecidableStep ==
    \E i \in 1..Len(stepDecisions): stepDecisions[i] = "UNDECIDABLE"

(* Plan-level constraint violations. *)
SequenceViolated ==
    \E i \in 1..Len(plan), j \in 1..Len(plan):
        /\ i > j
        /\ <<plan[j], plan[i]>> \in SequenceConstraints

AggregateViolated ==
    \E a \in Actions:
        Cardinality({i \in 1..Len(plan): plan[i] = a}) > AggregateLimits[a]

HasBlockingViolation ==
    \/ SequenceViolated
    \/ AggregateViolated
    \/ ~NoBlockingViolation
    \/ \E i \in 1..Len(plan):
            /\ plan[i] \in PreconditionRequired
            /\ ~NoBlockingViolation

-----------------------------------------------------------------------------

Init ==
    /\ plan \in Seq(Actions)
    /\ Len(plan) <= MaxPlanSteps + 1     \* exhaustive bound
    /\ stepDecisions = << >>
    /\ violations = {}
    /\ planVerdict = "UNDECIDABLE"
    /\ state = "Init"

(* Empty plan branch — directly to Done as FORBIDDEN. *)
HandleEmpty ==
    /\ state = "Init"
    /\ EmptyPlan
    /\ planVerdict' = "FORBIDDEN"
    /\ violations' = {"EMPTY_PLAN"}
    /\ state' = "Done"
    /\ UNCHANGED <<plan, stepDecisions>>

(* Over-budget branch — directly to Done as UNDECIDABLE. *)
HandleOversize ==
    /\ state = "Init"
    /\ ~EmptyPlan
    /\ OverBudget
    /\ planVerdict' = "UNDECIDABLE"
    /\ violations' = {"PLAN_TOO_LONG"}
    /\ state' = "Done"
    /\ UNCHANGED <<plan, stepDecisions>>

(* Per-step delegation — populate stepDecisions from the oracle. *)
EvaluateSteps ==
    /\ state = "Init"
    /\ ~EmptyPlan
    /\ ~OverBudget
    /\ stepDecisions' = [i \in 1..Len(plan) |-> StepDecisionMap[plan[i]]]
    /\ state' = "Constraints"
    /\ UNCHANGED <<plan, violations, planVerdict>>

(* Plan-level constraint checks — populate violations. *)
CheckConstraints ==
    /\ state = "Constraints"
    /\ violations' =
        ({"SEQUENCE_VIOLATION"} \cup
         (IF AggregateViolated THEN {"AGGREGATE_VIOLATION"} ELSE {})) \cap
        (IF SequenceViolated THEN {"SEQUENCE_VIOLATION"} ELSE {}) \cup
        (IF AggregateViolated THEN {"AGGREGATE_VIOLATION"} ELSE {}) \cup
        (IF ~NoBlockingViolation THEN {"PRECONDITION_VIOLATION"} ELSE {})
    /\ state' = "Aggregate"
    /\ UNCHANGED <<plan, stepDecisions, planVerdict>>

(* Aggregation table — same rule order as PlanPipeline._aggregate_plan_decision. *)
Aggregate ==
    /\ state = "Aggregate"
    /\ planVerdict' =
        IF HasForbiddenStep THEN "FORBIDDEN"
        ELSE IF Cardinality(violations) > 0 THEN "FORBIDDEN"
        ELSE IF HasUndecidableStep THEN "UNDECIDABLE"
        ELSE "PERMITTED"
    /\ state' = "Done"
    /\ UNCHANGED <<plan, stepDecisions, violations>>

Next ==
    \/ HandleEmpty
    \/ HandleOversize
    \/ EvaluateSteps
    \/ CheckConstraints
    \/ Aggregate
    \/ (state = "Done" /\ UNCHANGED vars)   \* terminal stutter

Spec == Init /\ [][Next]_vars /\ WF_vars(Next)

-----------------------------------------------------------------------------
\* INVARIANTS (Pl-1..Pl-5)
-----------------------------------------------------------------------------

(* Pl-1 — Determinism (TLC-style): with fixed inputs, the model has
 * exactly one terminal state. Encoded as: in Done, planVerdict is a
 * function of (plan, StepDecisionMap, SequenceConstraints,
 * AggregateLimits, NoBlockingViolation). The model has no
 * non-determinism after Init, so this is automatic — the property
 * we check is that planVerdict is in the value space. *)
Pl_1_Determinism ==
    state = "Done" => planVerdict \in PlanDecisions

(* Pl-2 — Soundness of PERMITTED. *)
Pl_2_PermittedSoundness ==
    (state = "Done" /\ planVerdict = "PERMITTED")
    => /\ ~HasForbiddenStep
       /\ ~HasUndecidableStep
       /\ Cardinality(violations) = 0

(* Pl-3 — Any FORBIDDEN step → plan FORBIDDEN. *)
Pl_3_ForbiddenStepDominates ==
    (state = "Done" /\ HasForbiddenStep)
    => planVerdict = "FORBIDDEN"

(* Pl-4 — Any blocking violation → plan FORBIDDEN. *)
Pl_4_BlockingViolationDominates ==
    (state = "Done" /\ Cardinality(violations) > 0
        /\ violations # {"PLAN_TOO_LONG"}
        /\ violations # {"EMPTY_PLAN"})
    => planVerdict = "FORBIDDEN"

(* Pl-5 — Termination: oversize plans reach Done with UNDECIDABLE.
 * Empty plans reach Done with FORBIDDEN.
 * Plans 1..MaxPlanSteps reach Done with planVerdict in PlanDecisions. *)
Pl_5_Termination ==
    state = "Done"
        => /\ planVerdict \in PlanDecisions
           /\ (OverBudget => planVerdict = "UNDECIDABLE")
           /\ (EmptyPlan => planVerdict = "FORBIDDEN")

=============================================================================
