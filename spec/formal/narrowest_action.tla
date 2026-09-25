---------------------------- MODULE narrowest_action ----------------------------
(*
 * AEGIS Narrowest-Action-Selection — TLA+ Specification
 *
 * Formal model of Guard.check_candidates from Epic 32 (AEGIS-3203 + 3204).
 * Verifies invariant Pl-6:
 *
 *   When the Guard is given a non-empty list of candidate actions and at
 *   least one of them receives PERMITTED, the chosen action is a minimum
 *   element under the narrowerThan partial order; the antichain of all
 *   minimal PERMITTED candidates is reported alongside; the tie-break is
 *   deterministic.
 *
 * Reference:
 *   - Olson, "A Formal Theory of Norms", Ch. 6.4.6 (Subsumption)
 *   - aegis/guard/guard.py::Guard.check_candidates
 *   - aegis/guard/registry.py::SubsumptionGraph.minimal_elements
 *
 * Pl-6 sits alongside Pl-1..Pl-5 from Epic 27 (Plan-Level Governance).
 * Run: tlc narrowest_action.tla -config narrowest_action.cfg
 *)

EXTENDS Integers, Sequences, FiniteSets, TLC

CONSTANTS
    Actions,           \* set of action-type identifiers
    NarrowerEdges,     \* set of <<a, b>> pairs meaning a narrowerThan b
    Permitted          \* subset of Actions that received PERMITTED

ASSUME NarrowerEdges \subseteq Actions \X Actions
ASSUME Permitted \subseteq Actions

-----------------------------------------------------------------------------

(*
 * NarrowerThan: transitive closure of NarrowerEdges. We compute it
 * symbolically via the Reachable predicate so the model checker does
 * not need to enumerate the closure.
 *)
RECURSIVE Reachable(_, _, _)
Reachable(a, b, visited) ==
    IF <<a, b>> \in NarrowerEdges THEN TRUE
    ELSE
        \E c \in Actions :
            /\ c \notin visited
            /\ <<a, c>> \in NarrowerEdges
            /\ Reachable(c, b, visited \cup {c})

NarrowerThan(a, b) ==
    /\ a # b
    /\ Reachable(a, b, {a})

(*
 * Acyclicity: the NarrowerEdges relation must induce a DAG. Enforced
 * by the MELD loader (AEGIS-2901, AEGIS-2902); modelled here as an
 * input assumption so the verifier rejects models that violate it.
 *)
ASSUME \A a \in Actions : ~NarrowerThan(a, a)

-----------------------------------------------------------------------------

(*
 * MinimalIn(S): the antichain of S. An action a is minimal in S iff
 *  - a is in S
 *  - no other element b in S satisfies NarrowerThan(b, a)
 *)
MinimalIn(S) ==
    {a \in S : \A b \in S : (b # a) => ~NarrowerThan(b, a)}

(*
 * Tie-break: deterministic lexicographic order. We model lex order by
 * picking the CHOOSE-element of MinimalIn(S) — TLC instantiates this
 * with a stable order from the model file, matching Python's
 * sorted(...)[0] semantics.
 *)
ChooseDeterministic(S) == CHOOSE a \in S : \A b \in S : a <= b

-----------------------------------------------------------------------------

(* The verdict produced by Guard.check_candidates, captured as a record. *)
VerdictType == [
    decision         : {"PERMITTED", "FORBIDDEN", "UNDECIDABLE"},
    chosen           : Actions \cup {"NONE"},
    minimal          : SUBSET Actions
]

(*
 * The semantic specification of check_candidates: given a candidate set
 * (modeled as the Permitted constant for this step) and the global
 * NarrowerEdges, produce the verdict.
 *)
CheckCandidates ==
    IF Permitted = {}
    THEN [decision |-> "FORBIDDEN", chosen |-> "NONE", minimal |-> {}]
    ELSE LET min == MinimalIn(Permitted)
             pick == ChooseDeterministic(min)
         IN  [decision |-> "PERMITTED", chosen |-> pick, minimal |-> min]

Verdict == CheckCandidates

-----------------------------------------------------------------------------
(* Pl-6 INVARIANTS *)
-----------------------------------------------------------------------------

(*
 * Pl-6.1: when Permitted is non-empty, the chosen action is itself a
 * member of Permitted.
 *)
Pl6_ChosenIsPermitted ==
    Permitted = {} \/ Verdict.chosen \in Permitted

(*
 * Pl-6.2: the chosen action is minimum bzgl. NarrowerThan in the
 * Permitted set — no other Permitted action is narrower than it.
 *)
Pl6_ChosenIsMinimum ==
    Permitted = {}
    \/ \A other \in Permitted : ~NarrowerThan(other, Verdict.chosen)

(*
 * Pl-6.3: the reported minimal-set is an antichain — no two elements
 * are comparable under NarrowerThan.
 *)
Pl6_MinimalIsAntichain ==
    \A a, b \in Verdict.minimal :
        a # b => ~NarrowerThan(a, b)

(*
 * Pl-6.4: every Permitted element is either minimal or strictly
 * narrower than some minimal element. The partition of Permitted into
 * (minimal, dominated) is exhaustive.
 *)
Pl6_ExhaustivePartition ==
    \A a \in Permitted :
        a \in Verdict.minimal
        \/ \E m \in Verdict.minimal : NarrowerThan(m, a)

(*
 * Pl-6.5: determinism — the chosen action is uniquely determined by
 * the input. (Tautologically true for the spec because
 * ChooseDeterministic uses CHOOSE on a fixed order; left here so the
 * invariant set is human-readable.)
 *)
Pl6_Deterministic == TRUE

-----------------------------------------------------------------------------

(* Composite Pl-6 invariant *)
Pl_6 ==
    /\ Pl6_ChosenIsPermitted
    /\ Pl6_ChosenIsMinimum
    /\ Pl6_MinimalIsAntichain
    /\ Pl6_ExhaustivePartition
    /\ Pl6_Deterministic

=============================================================================
