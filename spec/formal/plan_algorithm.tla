---------------------------- MODULE plan_algorithm ----------------------------
(* Bounded model of plan evaluation. DDIC verdicts and the timing/state
   blocker are oracle inputs, fixed after Init. This is not a refinement
   proof of the Python implementation. See plan_validation.md. *)
EXTENDS Integers, Sequences, FiniteSets, TLC

CONSTANTS Actions, MaxPlanSteps, SequenceConstraints, AggregateLimits

Decisions == {"PERMITTED", "FORBIDDEN", "UNDECIDABLE"}
BoundedPlans == UNION {[1..n -> Actions] : n \in 0..(MaxPlanSteps + 1)}

VARIABLES plan, oracleDecisions, extraBlocking,
          stepDecisions, violations, planVerdict, state
vars == <<plan, oracleDecisions, extraBlocking,
          stepDecisions, violations, planVerdict, state>>
inputs == <<plan, oracleDecisions, extraBlocking>>

EmptyPlan == Len(plan) = 0
OverBudget == Len(plan) > MaxPlanSteps
Evaluable == ~EmptyPlan /\ ~OverBudget
HasForbiddenStep == "FORBIDDEN" \in {stepDecisions[i] : i \in DOMAIN stepDecisions}
HasUndecidableStep == "UNDECIDABLE" \in {stepDecisions[i] : i \in DOMAIN stepDecisions}

(* Match Python's conditional co-occurrence semantics: if both action types
   occur, no B may precede the first A. Later repetitions of A are allowed.
   A missing A or B does not itself violate this ordering constraint.
   For a self-pair A=A, the occurrence itself satisfies the <= comparison. *)
SequenceViolated ==
    \E pair \in SequenceConstraints:
        /\ \E i \in 1..Len(plan): plan[i] = pair[1]
        /\ \E j \in 1..Len(plan):
            /\ plan[j] = pair[2]
            /\ ~\E i \in 1..j: plan[i] = pair[1]

AggregateViolated ==
    \E a \in Actions:
        Cardinality({i \in 1..Len(plan): plan[i] = a}) > AggregateLimits[a]

ConstraintViolations ==
    (IF SequenceViolated THEN {"SEQUENCE_VIOLATION"} ELSE {}) \cup
    (IF AggregateViolated THEN {"AGGREGATE_VIOLATION"} ELSE {}) \cup
    (IF extraBlocking THEN {"EXTERNAL_BLOCKING_VIOLATION"} ELSE {})

(* Declarative total decision function, independent of the pipeline's stored
   stepDecisions/violations. Agreement fixes one terminal decision per input. *)
ExpectedDecision ==
    IF EmptyPlan THEN "FORBIDDEN"
    ELSE IF OverBudget THEN "UNDECIDABLE"
    ELSE IF \E i \in 1..Len(plan): oracleDecisions[i] = "FORBIDDEN"
         THEN "FORBIDDEN"
    ELSE IF ConstraintViolations # {} THEN "FORBIDDEN"
    ELSE IF \E i \in 1..Len(plan): oracleDecisions[i] = "UNDECIDABLE"
         THEN "UNDECIDABLE"
    ELSE "PERMITTED"

Init ==
    /\ plan \in BoundedPlans
    /\ oracleDecisions \in [1..Len(plan) -> Decisions]
    /\ extraBlocking \in BOOLEAN
    /\ stepDecisions = << >>
    /\ violations = {}
    /\ planVerdict = "UNDECIDABLE"
    /\ state = "Init"

HandleEmpty ==
    /\ state = "Init" /\ EmptyPlan
    /\ planVerdict' = "FORBIDDEN"
    /\ violations' = {"EMPTY_PLAN"}
    /\ state' = "Done"
    /\ UNCHANGED <<inputs, stepDecisions>>

HandleOversize ==
    /\ state = "Init" /\ OverBudget
    /\ planVerdict' = "UNDECIDABLE"
    /\ violations' = {"PLAN_TOO_LONG"}
    /\ state' = "Done"
    /\ UNCHANGED <<inputs, stepDecisions>>

EvaluateSteps ==
    /\ state = "Init" /\ Evaluable
    /\ stepDecisions' = oracleDecisions
    /\ state' = "Constraints"
    /\ UNCHANGED <<inputs, violations, planVerdict>>

CheckConstraints ==
    /\ state = "Constraints"
    /\ violations' = ConstraintViolations
    /\ state' = "Aggregate"
    /\ UNCHANGED <<inputs, stepDecisions, planVerdict>>

Aggregate ==
    /\ state = "Aggregate"
    /\ planVerdict' =
        IF HasForbiddenStep THEN "FORBIDDEN"
        ELSE IF violations # {} THEN "FORBIDDEN"
        ELSE IF HasUndecidableStep THEN "UNDECIDABLE"
        ELSE "PERMITTED"
    /\ state' = "Done"
    /\ UNCHANGED <<inputs, stepDecisions, violations>>

Next == HandleEmpty \/ HandleOversize \/ EvaluateSteps \/ CheckConstraints \/ Aggregate
Spec == Init /\ [][Next]_vars /\ WF_vars(Next)

TypeOK ==
    /\ plan \in BoundedPlans
    /\ oracleDecisions \in [1..Len(plan) -> Decisions]
    /\ extraBlocking \in BOOLEAN
    /\ stepDecisions \in {<< >>, oracleDecisions}
    /\ violations \subseteq {"EMPTY_PLAN", "PLAN_TOO_LONG", "SEQUENCE_VIOLATION",
                             "AGGREGATE_VIOLATION", "EXTERNAL_BLOCKING_VIOLATION"}
    /\ planVerdict \in Decisions
    /\ state \in {"Init", "Constraints", "Aggregate", "Done"}

Pl_1_Determinism == state = "Done" => planVerdict = ExpectedDecision
Pl_2_PermittedSoundness ==
    (state = "Done" /\ planVerdict = "PERMITTED") =>
        /\ Evaluable
        /\ \A i \in 1..Len(plan): oracleDecisions[i] = "PERMITTED"
        /\ ConstraintViolations = {}
        /\ violations = {}
Pl_3_ForbiddenStepDominates ==
    (state = "Done" /\ Evaluable /\
        (\E i \in 1..Len(plan): oracleDecisions[i] = "FORBIDDEN"))
    => planVerdict = "FORBIDDEN"
Pl_4_BlockingViolationDominates ==
    (state = "Done" /\ Evaluable /\ ConstraintViolations # {})
    => planVerdict = "FORBIDDEN"
(* Temporal liveness, checked as PROPERTY, not as an implication at Done. *)
Pl_5_Termination == <> (state = "Done")
SentinelDecisions ==
    state = "Done" =>
        /\ (EmptyPlan => planVerdict = "FORBIDDEN")
        /\ (OverBudget => planVerdict = "UNDECIDABLE")
FailClosedUndecidability ==
    (state = "Done" /\ Evaluable /\ ConstraintViolations = {} /\
        ~(\E i \in 1..Len(plan): oracleDecisions[i] = "FORBIDDEN") /\
        (\E i \in 1..Len(plan): oracleDecisions[i] = "UNDECIDABLE"))
    => planVerdict = "UNDECIDABLE"

(* TLC configuration substitutes these operators for constants. *)
ModelSequenceConstraints == {<<"a", "b">>}
ModelAggregateLimits == [a \in Actions |-> IF a = "a" THEN 1 ELSE 2]
=============================================================================
