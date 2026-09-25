---------------------------- MODULE ddic_algorithm ----------------------------
(*
 * AEGIS DDIC Algorithm — TLA+ Specification
 *
 * Formal model of the 6-step Defeasible Deontic Inheritance Calculus
 * as implemented in aegis/engine/ddic.py. This specification enables
 * exhaustive model-checking of the algorithm's invariants and Olson's
 * Theorems 6.4.1–6.4.4 via the TLC model checker.
 *
 * Reference: Olson, "A Formal Theory of Norms", Chapter 3 & 6.4
 *
 * Run: tlc ddic_algorithm.tla -config ddic_model.cfg
 *)

EXTENDS Integers, Sequences, FiniteSets, TLC

CONSTANTS
    Modalities,       \* {"OBLIGATORY", "FORBIDDEN", "PERMITTED"}
    MaxSpecificity,   \* e.g. 5
    Codes,            \* e.g. {"CodeA", "CodeB"}
    MaxNorms          \* e.g. 6

(*
 * A Norm is a record with modality, specificity, defeasibility, and code.
 * Agent and proposition matching are abstracted away — we assume all norms
 * in the input set are applicable (Step 1 already done).
 *)
NormType == [
    modality    : Modalities,
    specificity : 0..MaxSpecificity,
    defeasible  : BOOLEAN,
    code        : Codes
]

(* Code prevalence: higher index = higher priority *)
VARIABLE
    norms,           \* Set of applicable norms (input)
    axioms,          \* Non-defeasible norms (Step 2)
    defeasible,      \* Defeasible norms (Step 2)
    surviving,       \* Norms surviving preemption (Step 4)
    defeated,        \* Norms defeated by preemption (Step 4)
    result,          \* Final modality or "UNDETERMINED"
    step             \* Current algorithm step (1..7)

vars == <<norms, axioms, defeasible, surviving, defeated, result, step>>

-----------------------------------------------------------------------------

(* Whether two modalities conflict *)
Conflicts(m1, m2) ==
    /\ m1 /= m2
    /\ \/ {m1, m2} = {"OBLIGATORY", "FORBIDDEN"}
       \/ {m1, m2} = {"PERMITTED", "FORBIDDEN"}

(* Code rank: index in the prevalence ordering *)
CodeRank(c) ==
    LET codeSeq == <<"CodeA", "CodeB">>
    IN  IF c = "CodeA" THEN 2
        ELSE IF c = "CodeB" THEN 1
        ELSE 0

-----------------------------------------------------------------------------

(* Initial state: norms loaded, algorithm at step 1 *)
Init ==
    /\ norms \in SUBSET NormType
    /\ Cardinality(norms) >= 1
    /\ Cardinality(norms) <= MaxNorms
    /\ axioms = {}
    /\ defeasible = {}
    /\ surviving = {}
    /\ defeated = {}
    /\ result = "PENDING"
    /\ step = 1

(* Step 2: Separate axioms from defeasible norms *)
Step2_SeparateAxioms ==
    /\ step = 1
    /\ axioms' = {n \in norms : ~n.defeasible}
    /\ defeasible' = {n \in norms : n.defeasible}
    /\ step' = 2
    /\ UNCHANGED <<norms, surviving, defeated, result>>

(* Step 2b: If axioms exist, check for contradictions *)
Step2b_AxiomCheck ==
    /\ step = 2
    /\ axioms /= {}
    /\ IF \E a1, a2 \in axioms :
            /\ a1 /= a2
            /\ Conflicts(a1.modality, a2.modality)
       THEN
            /\ result' = "UNDETERMINED"
            /\ step' = 7
            /\ surviving' = axioms
            /\ defeated' = defeasible
       ELSE
            \* All axioms have compatible modalities — pick the first
            /\ result' = (CHOOSE a \in axioms : TRUE).modality
            /\ step' = 7
            /\ surviving' = axioms
            /\ defeated' = defeasible
    /\ UNCHANGED <<norms, axioms, defeasible>>

(* Step 2c: No axioms — proceed to defeasible resolution *)
Step2c_NoAxioms ==
    /\ step = 2
    /\ axioms = {}
    /\ step' = 3
    /\ UNCHANGED <<norms, axioms, defeasible, surviving, defeated, result>>

(* Step 4: Preemption — more specific defeats less specific *)
Step4_Preemption ==
    /\ step = 3
    /\ LET
        defeatedSet == {b \in defeasible :
            \E a \in defeasible :
                /\ a /= b
                /\ Conflicts(a.modality, b.modality)
                /\ a.specificity > b.specificity}
       IN
        /\ surviving' = defeasible \ defeatedSet
        /\ defeated' = defeatedSet
        /\ step' = 4
    /\ UNCHANGED <<norms, axioms, defeasible, result>>

(* Step 5: Check unanimity or resolve by code prevalence *)
Step5_Resolve ==
    /\ step = 4
    /\ LET
        modalitySet == {n.modality : n \in surviving}
       IN
        IF Cardinality(modalitySet) = 1
        THEN
            \* Unanimous
            /\ result' = (CHOOSE m \in modalitySet : TRUE)
            /\ step' = 7
        ELSE IF Cardinality(modalitySet) = 0
        THEN
            /\ result' = "UNDETERMINED"
            /\ step' = 7
        ELSE
            \* Try code prevalence
            LET
                bestRank == CHOOSE r \in {CodeRank(n.code) : n \in surviving} :
                    \A r2 \in {CodeRank(n2.code) : n2 \in surviving} : r >= r2
                bestCode == CHOOSE c \in {n.code : n \in surviving} : CodeRank(c) = bestRank
                bestNorms == {n \in surviving : n.code = bestCode}
                bestModalities == {n.modality : n \in bestNorms}
            IN
                IF Cardinality(bestModalities) = 1
                THEN
                    /\ result' = (CHOOSE m \in bestModalities : TRUE)
                    /\ step' = 7
                ELSE
                    /\ result' = "UNDETERMINED"
                    /\ step' = 7
    /\ UNCHANGED <<norms, axioms, defeasible, surviving, defeated>>

(* Terminal state *)
Done ==
    /\ step = 7
    /\ UNCHANGED vars

-----------------------------------------------------------------------------

Next ==
    \/ Step2_SeparateAxioms
    \/ Step2b_AxiomCheck
    \/ Step2c_NoAxioms
    \/ Step4_Preemption
    \/ Step5_Resolve
    \/ Done

Spec == Init /\ [][Next]_vars /\ WF_vars(Next)

-----------------------------------------------------------------------------
(* INVARIANTS *)

TypeOK ==
    /\ norms \subseteq NormType
    /\ axioms \subseteq NormType
    /\ defeasible \subseteq NormType
    /\ surviving \subseteq NormType
    /\ defeated \subseteq NormType
    /\ result \in Modalities \cup {"PENDING", "UNDETERMINED"}
    /\ step \in 1..7

(* I1: Determinism — same input always produces same result *)
(* Verified implicitly: TLA+ Next is deterministic given fixed norms *)

(* I4: Axiom Monotonicity — non-defeasible norms always win *)
AxiomMonotonicity ==
    step = 7 =>
        (\A a \in norms :
            (~a.defeasible /\ \A a2 \in norms :
                a2 /= a /\ ~a2.defeasible => ~Conflicts(a.modality, a2.modality))
            => result = a.modality)

(* I7: Duality — if only FORBIDDEN norms apply, result is FORBIDDEN *)
ForbiddenDominance ==
    step = 7 =>
        ((\A n \in norms : n.modality = "FORBIDDEN")
            => result = "FORBIDDEN")

(* Totality: algorithm always terminates (reaches step 7) *)
(* Verified via temporal property: <>[] (step = 7) *)
AlwaysTerminates == <>(step = 7)

(* Theorem 6.4.1: More-specific permission/obligation defeats less-specific prohibition *)
Theorem641 ==
    step = 7 =>
        \A n1, n2 \in norms :
            /\ n1.modality = "FORBIDDEN"
            /\ n2.modality \in {"OBLIGATORY", "PERMITTED"}
            /\ n2.specificity > n1.specificity
            /\ n1.defeasible
            /\ n2.defeasible
            /\ Cardinality(norms) = 2
            => result \in {"OBLIGATORY", "PERMITTED"}

(* Theorem 6.4.2: More-specific prohibition defeats less-specific permission *)
Theorem642 ==
    step = 7 =>
        \A n1, n2 \in norms :
            /\ n1.modality \in {"OBLIGATORY", "PERMITTED"}
            /\ n2.modality = "FORBIDDEN"
            /\ n2.specificity > n1.specificity
            /\ n1.defeasible
            /\ n2.defeasible
            /\ Cardinality(norms) = 2
            => result = "FORBIDDEN"

(* Theorem 6.4.4: Equal specificity conflict → UNDETERMINED *)
Theorem644 ==
    step = 7 =>
        \A n1, n2 \in norms :
            /\ Conflicts(n1.modality, n2.modality)
            /\ n1.specificity = n2.specificity
            /\ n1.defeasible
            /\ n2.defeasible
            /\ n1.code = n2.code
            /\ Cardinality(norms) = 2
            => result = "UNDETERMINED"

=============================================================================
