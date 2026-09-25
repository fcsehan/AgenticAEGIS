# MELD Language Specification

Unified specification for MELD (Modal Ethics Logic Definitions) in AEGIS.

Snapshot: 2026-03-23

This document replaces:
- `MELD_LANGUAGE_SPEC.md` (v1 implementation snapshot)
- `MELD_RFC_SPEC.md` (v2 RFC)
- `MELD_V2_DDIC_CANON.md` (v2 predicate catalog)

## 1. Purpose

MELD is AEGIS's declarative assertion language for deontic rules. Derived
historically from CycL, it is now a separate S-expression format with two
schema versions:

- **Schema version 1** (v1): facts and deontic assertions, used by the six
  bundled domains. Legacy evaluation uses unification and the six-step algorithm.
- **Schema version 2** (v2): testimony/belief, time, subsumption, rules and
  priorities for DDIC. Evaluation uses forward chaining and lex posterior.
  See the conformance reference for the scope of the correspondence to Olson.

## 2. Shared syntax

### 2.1 Grammar

```ebnf
meld_file       = { top_level_expr } ;
top_level_expr  = list ;
list            = "(" , element , { element } , ")" ;
element         = atom | string | integer | list ;
atom            = 1*non_delimiter_char ;
string          = '"' , { string_char } , '"' ;
integer         = [ "-" ] , digit , { digit } ;
```

- Empty lists `()` are forbidden.
- Maximum nesting depth: 1,000.
- Line comments: `;`

### 2.2 Control predicates

```lisp
(aegis-schema-version 1)  ; or 2
(case SomeMicrotheory)
```

Every non-control assertion MUST follow a `case` declaration.

## 3. Schema version 1 (Legacy)

### 3.1 Ontology predicates

`isa`, `genls`, `genlPreds`, `negationPreds`, `typeGenls`, `comment`,
`sharedNotes`, `singleEntryFormatInArgs`,
`functionCorrespondingPredicate-Canonical`, `argFormat`, `arg2Format`,
`quotedIsa`

### 3.2 Constraint predicates

`argIsa`, `arg1Isa`, `arg2Isa`, `arg2QuotedIsa`, `arg3QuotedIsa`,
`argQuotedIsa`, `arg1Genl`, `arg2Genl`, `argGenl`, `resultGenl`

These are stored, not enforced.

### 3.3 Deontic predicates

| Predicate | Arity | Modality |
|---|---:|---|
| `oughtToDo` | 2 | OBLIGATORY |
| `forbiddenToDo` | 2 | FORBIDDEN |
| `permittedToDo` | 2 | PERMITTED |
| `oughtToDo-WRT` | 3 | OBLIGATORY |
| `forbiddenToDo-WRT` | 3 | FORBIDDEN |
| `permittedToDo-WRT` | 3 | PERMITTED |
| `oughtToBe` | 1 | OBLIGATORY |
| `forbiddenToBe` | 1 | FORBIDDEN |
| `permittedToBe` | 1 | PERMITTED |

### 3.4 Action vocabulary predicates

`actionParameter`, `requiredContext`

### 3.4.1 Disambiguation predicates (AEGIS-2901, Epic 29)

Optional fields mitigate action substitution. The loader validates their structural consistency and acyclicity; the action type registry forwards them to the orchestrator prompt template. They are domain declarations exposed as disambiguation hints in the system prompt.

| Predicate | Arity | Meaning | Example |
|---|---|---|---|
| `actionDescription` | 2 | Precise natural-language action description (1–2 sentences) | `(actionDescription readDiagnosis "Reads ONLY the diagnostic conclusion section.")` |
| `actionSynonym` | 2 | Natural-language phrase usually referring to this action | `(actionSynonym readDiagnosis "View diagnosis")` (repeatable) |
| `notToBeConfusedWith` | 2 | Another action that may be confused with this one | `(notToBeConfusedWith readDiagnosis readPatientRecord)` |
| `narrowerThan` | 2 | A is a narrower form of B (subsumption) | `(narrowerThan readDiagnosis readPatientRecord)` |
| `broaderThan` | 2 | A includes B (inverse subsumption) | `(broaderThan readPatientRecord readDiagnosis)` |

**Consistency requirements** enforced by the loader:

1. **Bidirectional:** every `(narrowerThan A B)` must have a matching `(broaderThan B A)` and vice versa.
2. **Acyclic:** the graph defined by `narrowerThan` must contain no cycles.

Violations raise `MeldSyntaxError` during domain loading (fail-closed).

**Review requirement:** changes to `narrowerThan`/`broaderThan` require documented review of the declared semantic relationship. Structural checks alone do not prove it. This supports condition B1 of the candidate-selection guarantee.

### 3.5 NormFrame extraction

```
(forbiddenToDo-WRT Code agent prop) →
  NormFrame(code=Code, agent_pattern=agent, modality=FORBIDDEN,
            proposition=tuple(prop))
```

### 3.6 Evaluation

DDICEngine six-step algorithm:
1. Filter applicable (agent + unification)
2. Moral axioms win (defeasible=False)
3. Sort by specificity (genls depth)
4. Preemption (more specific defeats less specific)
5. Cross-code prevalence
6. Unresolvable → UNDETERMINED

### 3.7 v1-to-DDICModule bridge

V1 norm frames are compiled to DDIC formulas during Guard initialization
(`aegis/engine/normframe_compile.py`):

| NormFrame | DDICFormula |
|---|---|
| modality | mode (PERMITTED→OPTIONAL) |
| — | layer = TESTIMONY |
| — | polarity = POSITIVE |
| agent_pattern | agent = DDICSymbol |
| proposition | behavior = DDICCompound/DDICSymbol |
| — | context = DDICSymbol("Top") |
| — | time = DDICSymbol("t0") |
| code | metadata(key="code") |
| defeasible=False | metadata(key="is_axiom") |

The resulting DDICModule uses `resolution_strategy="legacy"`.

## 4. Schema version 2 (DDIC)

### 4.1 Normative formula predicates

All have arity 4: `(pred Agent Behavior Context Time)`

| Predicate | Layer | Polarity | Mode |
|---|---|---|---|
| `testimony-obligatory` | testimony | positive | obligatory |
| `testimony-forbidden` | testimony | positive | forbidden |
| `testimony-optional` | testimony | positive | optional |
| `belief-obligatory` | belief | positive | obligatory |
| `belief-forbidden` | belief | positive | forbidden |
| `belief-optional` | belief | positive | optional |
| `not-testimony-obligatory` | testimony | negative | obligatory |
| `not-testimony-forbidden` | testimony | negative | forbidden |
| `not-belief-obligatory` | belief | negative | obligatory |
| `not-belief-forbidden` | belief | negative | forbidden |

### 4.2 Structural relations

| Predicate | Arity | Meaning |
|---|---:|---|
| `before` | 2 | Strict temporal ordering |
| `before-or-equal` | 2 | Nonstrict temporal ordering |
| `between-inclusive` | 3 | t <= tx <= tn |
| `behavior-subsumes` | 2 | Declared behavior subsumption |
| `context-subsumes` | 2 | More specific context |
| `behavior-intersects` | 3 | Canonical intersection |
| `context-intersects` | 3 | Canonical context intersection |

### 4.3 Rule declarations

```lisp
(default-rule D1a
  (iff (testimony-optional ?A ?B ?C ?T)
       (and (not-testimony-obligatory ?A ?B ?C ?T)
            (not-testimony-forbidden ?A ?B ?C ?T))))

(defeasible-rule R1
  :from (testimony-obligatory ?A ?B ?Phi ?T)
  :to   (belief-obligatory ?A ?C ?Delta ?Tn)
  :when ((behavior-subsumes ?B ?C)
         (context-subsumes ?Delta ?Phi))
  :justification (...)
  :defeat-mode complete)
```

### 4.4 Priority

```lisp
(priority D1b R1)
```

Transitive. Higher priority wins in a conflict.

### 4.5 Identity and provenance

```lisp
(norm-id n1 (testimony-forbidden AgentA Cook Top t1))
(source-id n1 OlsonExample3_3_1)
```

### 4.6 Legacy compatibility

V1 predicates such as `oughtToDo` are allowed in v2 files as compatibility
syntax. They MUST be normalized to canonical `testimony-*` forms before
DDIC evaluation.

### 4.7 Evaluation

Forward-Chaining:
1. Materialize asserted formulas
2. Apply categorical defaults (D1a–D1d)
3. Apply defeasible rules (R1–R4)
4. Classify conflicts (direct/indirect/overlapping)
5. Priority defeat
6. Lex Posterior defeat

## 5. Unified Pipeline

```
.meld files
    │
    ├─ v1: MeldLoader → NormFrame → compile_norms_to_module()
    │       → DDICModule(strategy="legacy")
    │       → DDICEngine.evaluate() [Unification + six steps]
    │
    └─ v2: parse_meld_module() → compile_meld_module()
            → DDICModule(strategy="ddic")
            → evaluate_ddic_module() [Forward-Chaining + Defeat]
    │
    └─ EvaluationPipeline.run() → Verdict
```

Use `Guard.from_meld_files()` as the loading entry point. The schema version
is detected automatically. DDICModule is the unified internal representation.

## 6. Conformance

### 6.1 v1 conformance

The parser accepts v1 syntax, extracts nine deontic predicates, stores facts
in the KB and creates norm frames.

### 6.2 v2 DDIC conformance

V2 adds testimony/belief separation, explicit time and contexts, declared
D1a–D1d and R1–R4 rules, priority relations, Olson conflict classes and
auditable justification chains.

## 7. Implementation sources

| Component | File |
|---|---|
| v1 Loader | `aegis/kb/meld_loader.py` (MeldLoader) |
| v2 Parser | `aegis/kb/meld_loader.py` (parse_meld_module) |
| v2 AST | `aegis/deontic/ddic_ast.py` |
| v1→IR Compiler | `aegis/engine/normframe_compile.py` |
| v2→IR Compiler | `aegis/engine/ddic_ir.py` |
| v2 Evaluator | `aegis/engine/ddic_eval.py` |
| v1 Evaluator | `aegis/engine/ddic.py` (DDICEngine) |
| Unified Pipeline | `aegis/guard/pipeline.py` |
| Guard | `aegis/guard/guard.py` |
