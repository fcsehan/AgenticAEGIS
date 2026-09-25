# Architecture

The caller proposes a structured action or complete finite plan. AEGIS evaluates
it against compiled MELD rules. The host interprets the verdict and permits an
effect only when the result is `PERMITTED`.

```text
MELD sources -> loader -> DDICModule -> DDIC action reasoning
                                      + plan constraints
Caller -> Guard.check / Guard.plan_check -> verdict + justification
Host   -> permit exact checked effect / block / escalate
```

`aegis.core` exposes the reasoning library. `aegis.deontic`, `aegis.engine` and
`aegis.kb` implement the data model, reasoning and knowledge base. Guard, API,
audit, information flow, orchestration and editor packages provide infrastructure.
The import boundary has its own regression test.

DDIC resolves conflicting action norms. Legacy schema-1 domains and schema-2
DDIC domains compile into a common representation but select different resolution
strategies. Schema 2 includes time-sensitive conflict handling. The plan evaluator
adds sequence, aggregate, timing and precondition checks around action verdicts;
it does not apply a new DDIC calculus to conflicts between plan constraints.

The local editor stores immutable source revisions and binds tests, review and
release to a specific revision. Activation affects its own `editor-runtime`;
it does not deploy policies automatically to an external agent host.

Python integration adapters and a [versioned OpenCode plugin](../integrations/opencode/README.md)
are included. Its process tests exercise the host's execution hooks against the
real sidecar. The full upstream checkout is downloaded separately. The guard
library alone does not intercept an arbitrary agent's tools; integration requires
an actual enforcement point in the host. See [limitations](limitations.md).
