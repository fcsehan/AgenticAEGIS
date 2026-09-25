# Python and REST usage

## Action checks

Run the example in the root README from the repository root. In an installed
package, bundled domains are available through `importlib.resources`:

```python
from importlib.resources import files
from pathlib import Path
from aegis.guard.guard import Guard

domain = Path(str(files("aegis") / "domains" / "devops"))
guard = Guard.from_meld_files(sorted(domain.glob("*.meld")))
```

Domains use ontology, action vocabulary and deontic rule files. Plan-enabled
domains also include plan norms. Modify a copy of a bundled domain rather than
the installed package. Examples use modeled categories such as `sourceFile`;
mapping actual filesystem paths to categories is a host responsibility.

## Plan checks

The repository contains complete plan fixtures in `tests/fixtures/devops_plans`.
For example:

```sh
.venv/bin/aegis plan-check --help
```

The Python interface is `Guard.plan_check(Plan)`. `Plan.from_action(action)`
constructs a one-step plan and preserves the underlying step's action verdict;
applicable plan constraints can still affect the overall plan verdict.

A forbidden step or a blocking plan violation makes the plan forbidden. With no
blocking violation, an undecidable step prevents the plan from being permitted.
The caller must not execute a rejected or undecidable plan.

## REST service

Install the `api` extra (already included in the editor setup) and start:

```sh
.venv/bin/aegis serve --domains aegis/domains/devops --host 127.0.0.1 --port 8420
```

Use `/openapi.json` for the exact request schemas and `/v1/health` for health.
Core endpoints are `/v1/check` and `/v1/plan_check`.

```sh
curl -sS http://127.0.0.1:8420/v1/check \
  -H 'Content-Type: application/json' \
  -d '{"action_type":"readFile","agent_id":"opencodeAgent","proposition":{"path":"sourceFile"}}'
```

This service is separate from the local editor. No general public-network
authorization boundary is claimed by these startup instructions.

## Red-team and document tools

Install `.[redteam]` for YAML scenario support, then use `aegis-redteam --help`.
`aegis --help` also lists domain generation and document-intelligence commands.
Manual checks do not require an LLM; model-assisted workflows need an explicitly
configured provider. The editor governs its own inference paths through MELD.
