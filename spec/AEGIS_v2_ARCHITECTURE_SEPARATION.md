> Imported technical reference. Historical test counts
> and roadmap references describe earlier development states; see
> `docs/limitations.md` and `docs/validation.md` for the public snapshot.

# AEGIS v2.0 — architecture separation: Core × Guard

Status: working draft. Original date: 2026-03-21.

## 1. Diagnosis

AEGIS combines two different responsibilities in one project:

| | DDIC core | Guard infrastructure |
|---|---|---|
| Question | Given these norms and this action, what is its deontic status? | Does every byte pass through the checkpoint? |
| Expertise | Formal logic, norm theory, knowledge representation | Security engineering, IFC, host integration |
| Distinctive contribution | Olson's calculus, MELD and BPS architecture | Channel registry, broker and taint tracking use established security patterns |
| Rate of change | Low: the calculus changes rarely | High: each new host or channel adds work |
| Users | Domain modelers and norm authors | Platform engineers and security teams |
| Testing | Formal verification: soundness, totality, invariants | Adversarial testing: red teams and bypass attempts |
| Value | Research contribution and differentiation | Product maturity and operational deployment |

Mixing these responsibilities burdens the core with infrastructure work and
burdens infrastructure with norm-theory requirements outside its responsibility.

## 2. Separation

```text
aegis-guard (product)
  API · Broker · OutputFilter · TaintTracker
  ChannelRegistry · HostContracts · Audit
  Orchestrator · RedTeam · Scorecard · Editor
  Copilot hooks · OpenCode plugin
       |
       Guard.check(action) -> Verdict
       |
       aegis-core (library)
         MELD · KB · DDIC · NormFrames
         Inheritance · Conflicts · PatternMatcher
         -> NormStatus
```

The conceptual evaluation interface is a pure function:

```text
ddic.evaluate(proposition, agent, norms)
  -> NormStatus(modality, winning_norms, defeated_norms, reason, justification_chain)
```

Everything surrounding this function belongs to the Guard. The core reasoning
has no knowledge of HTTP, files, taint, channels or hosts. This draft describes
the logical separation; current loading and compiled representations are
explained in `docs/architecture.md`.

## 3. aegis-core — area of responsibility

A Python library for deontic norm evaluation, intended to be embeddable in any
process with no network or nonstandard reasoning dependencies.

### Packages

```text
aegis/
  deontic/
    modality.py        # OBLIGATORY, FORBIDDEN, PERMITTED
    norm_frame.py      # code, agent, modality, proposition, specificity, defeasible
    norm_status.py     # Evaluation result
    conflicts.py       # Norm conflict detection
  engine/
    ddic.py            # Olson's DDIC algorithm
    inheritance.py     # Specificity through genls/isa
    pattern_matcher.py # Proposition unification
  kb/
    knowledge_base.py  # Fact store
    meld_loader.py     # MELD -> KB and norm frames
    builtins.py        # Transitive closure and reasoning
    microtheory.py     # Contextual knowledge collections
    vocabulary_loader.py # Action type schemas from the KB
```

### Questions the core must answer

- How are conflicts between defeasible and non-defeasible norms resolved?
- How is specificity computed through inheritance hierarchies?
- How are domain norms represented in MELD?
- When does evaluation terminate (totality)?
- Does the implementation conform to Olson's calculus (soundness)?
- Is the closed-world assumption applied consistently?
- Is deontic duality preserved (invariant I7)?

### Original v2.0 core roadmap

| Topic | Description |
|---|---|
| Temporal norms | Obligations with deadlines: an agent ought to do X before T |
| Conditional obligations | Reading classified content can prohibit later disclosure |
| Priorities beyond specificity | Explicit norm priorities, beyond code precedence |
| Multiple-agent inheritance | Agent hierarchies and inherited norms, such as team to member |
| Abductive reasoning | Minimal sets of norms explaining a prohibition |
| MELD extensions | Quantified norms, contextual conditions and temporal operators |
| Incremental evaluation | Reevaluate affected propositions after a norm change |
| Formal specification | TLA+ or Alloy model of the DDIC algorithm |

Quality targets: strict typing, tests for all Olson examples, Hypothesis tests
for invariants I1–I7, no I/O dependencies in pure reasoning, and independent
PyPI packaging. These are architectural targets, not claims that every check
passes in the public snapshot.

## 4. aegis-guard — area of responsibility

The Guard embeds the DDIC core in an operational security architecture and
mediates channels between a caller and its effects.

> Every effective action, information and disclosure path must pass through a
> formal, fail-closed, auditable Guard instance.

### Packages

```text
aegis/
  guard/
    guard.py           # Guard.check(): bridge between core and infrastructure
    pipeline.py        # Enrichment, normalization, registry -> DDIC -> verdict
    registry.py        # Action type registry derived from the KB
    action.py          # Action data structure
    verdict.py         # PERMITTED / FORBIDDEN / UNDECIDABLE and justification
  api/
    server.py          # FastAPI: /v1/check, /v1/broker/*, /v1/output/*
    tool_schema.py     # OpenAI tool schema generation
    rate_limit.py      # Request throttling
  ifc/
    broker.py          # Retrieval mediation: readDocument, searchCorpus
    provenance.py      # Source provenance
    transform_policy.py # Transformation rules
    channel_registry.py # Channel registry
    classification.py  # Workspace classification manifest
    host_contract.py   # HC-001 through HC-009
  hardening/
    output_guard.py    # Final-response pattern filter, defense in depth
    taint.py           # Session taint tracking
    permit.py          # Single-use permit tokens
  orchestrator/        # Prompt -> tool use -> verdict -> response
  audit/               # Hash-chain audit trail
  ops/                 # Configuration, reload and observability
  redteam/             # Adversarial pipeline, scorecard, coverage, certification
  editor/              # Domain editor web UI
```

The original architecture also included standalone Copilot CLI hooks and an
OpenCode plugin under `packages/`. Those host packages are not distributed in
this public snapshot.

### Questions the Guard must answer

- Which information channels connect the LLM and the outside world?
- Is every sensitive channel mediated?
- Can tainted content reach an unauthorized recipient?
- Can the Guard be bypassed?
- How is a new host integrated?
- Is the final text channel formally checked as disclosure?
- Does a deployment meet its declared Guard coverage criterion?

### Original v2.0 Guard roadmap

| Epic | Topic | Dependency |
|---|---|---|
| 18 | Channel closure and mandatory mediation | Epic 17 |
| 19 | Formal disclosure and transformation enforcement | Epic 18 |
| 20 | Guard coverage, proof and release governance | Epic 19 |

Quality targets: zero bypasses in red-team scenarios, passing host contracts,
a coverage report as a release gate, and at most 30 ms per fully mediated request.
These targets do not establish complete coverage of an arbitrary deployment.

## 5. The bridge: Guard.check()

```text
Guard.check(action: Action) -> Verdict

  1. Pipeline: enrichment, normalization, validation      [Guard]
  2. Registry: is the action type known?                  [Guard]
  3. DDIC: evaluate(proposition, agent, norms)             [Core]
  4. Verdict: decision, reason type, justification        [Guard]
  5. Permit: issue token for PERMITTED                    [Guard]
  6. Audit: append hash-chain record                      [Guard]
```

The core handles step 3: it receives norms and a proposition and returns a
modality. The Guard coordinates norm loading, proposition construction and
verdict handling. The later plan API composes action checks and plan constraints
through the same separation of responsibilities.

## 6. When to publish separate packages

The initial approach is logical package separation in one repository. Core must
never import Guard; Guard may import Core. The import-boundary test enforces this.

Separate distributions become useful when another project needs only DDIC,
when the layers have different release cycles, or when different teams own them.
At that point, use a monorepo with `aegis-core` and `aegis-guard` packages or two
repositories. The public snapshot currently publishes one `agentic-aegis`
distribution with a stable `aegis.core` import surface.

## 7. Comparison

| | aegis-core | aegis-guard |
|---|---|---|
| Metaphor | Judge | Courthouse |
| Task | Evaluate norms | Control channels |
| Input | Norms and proposition | Request or tool call |
| Output | NormStatus and modality | Verdict and enforcement |
| Research foundations | Olson's DDIC, MELD, BPS | Established security patterns |
| Rate of change | Lower | Higher |
| Roadmap focus | Norm theory, temporal logic, MELD | Channel closure, disclosure, coverage |
| Evidence | Formal models and conformance tests | Adversarial and integration tests |
