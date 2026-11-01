# AgenticAEGIS

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23084277.svg)](https://doi.org/10.5281/zenodo.23084277)

AgenticAEGIS checks structured actions and plans against policy rules before a
host executes them. The guard returns a deterministic decision, `PERMITTED`,
`FORBIDDEN` or `UNDECIDABLE`, with a justification. An agent, workflow or service
can call the guard. Its host must submit every relevant action for evaluation
and allow execution only when the decision is `PERMITTED`.

AEGIS stands for *Architectural Ethics Guard for Intelligent Systems*. The
project is a research prototype, and its checks do not certify the safety of an
agent or application. The Python package is imported as `aegis` and distributed
as `agentic-aegis`.

## Rules, plans and tools

Rules are written in MELD (Modal Ethics Logic Definitions), a declarative
language. The Python reasoner uses DDIC (Defeasible Deontic Inheritance Calculus)
to resolve conflicts between action norms, which express permissions,
prohibitions and obligations.

AEGIS evaluates plans supplied by the caller, which is responsible for
generating them. Plan checks cover step order, aggregate limits, declared
timing and state preconditions. They combine with DDIC decisions for individual
actions, while the plan constraints themselves are evaluated separately from
DDIC inference.

The repository includes:

- A Python library for loading MELD rules and checking actions and plans.
- Six example domains: DevOps, IAMission, pharma, sanctions, legal and information flow.
- A local React/TypeScript web editor that saves projects, edits rules and plans,
  and runs scenario tests. Review and release refer to a specific source revision.
  The editor also supports activation and rollback.
- A REST API, audit records, information-flow controls and tools for adversarial testing.
- Automated tests and TLA+ specifications.

The editor can use a local language model or documents to propose rules.
These proposals require validation and review. MELD remains the source of
the rules that the guard evaluates.

## Run the web editor

Install Python 3.12+, Node.js 22.12+ and npm, then run these commands from the
repository root:

```sh
python3.12 -m venv .venv
npm --prefix aegis/editor/frontend ci
npm --prefix aegis/editor/frontend run build
.venv/bin/python -m pip install -e '.[editor]'
mkdir -p workspace
cp -R aegis/domains/devops workspace/devops
.venv/bin/aegis-editor --workspace "$PWD/workspace" \
  --config-dir "$PWD/.editor-config" --port 8010
```

Open http://127.0.0.1:8010 and select the workspace project. Run the editor
locally for one user. It has no multi-user authentication and must not be
exposed through a reverse proxy. You can author rules manually and run guard
checks without a model or API key.

See the [web editor guide](docs/guides/editor-web-app.md) for provider setup,
review, activation, backup and recovery. The supplied editor policy permits
model inference only through the loopback interface. Selecting a remote provider
does not authorize sending domain content to it.

## Use the Python library

```python
from pathlib import Path

from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.verdict import Decision

guard = Guard.from_meld_files(sorted(Path("aegis/domains/devops").glob("*.meld")))
action = Action(
    action_type="readFile",
    agent_id="opencodeAgent",
    proposition={"path": "sourceFile"},
)
verdict = guard.check(action)
print(verdict.decision.value)
print(verdict.justification_chain)

if verdict.decision == Decision.PERMITTED:
    # The host may now execute this exact modeled action.
    pass
```

Run this example from the repository root. Installed applications can
locate bundled domains via `importlib.resources.files("aegis") / "domains"`.
See [Python and REST usage](docs/usage.md) for plan checking and service startup.

## OpenCode integration

Follow the [OpenCode integration guide](integrations/opencode/README.md) to
install and test a pinned upstream release. The process tests run OpenCode
with the AEGIS guard as a separate service. They inspect file changes for
permitted, forbidden, undecidable and failed guard requests, and check that
execution follows the approved plan supplied by the caller.

The integration includes a plugin, MELD test fixtures and a CI workflow.
Setup verifies the downloaded OpenCode release. The
[validation record](integrations/opencode/evidence/README.md) documents the
tested version and results.

## Development

```sh
.venv/bin/python -m pip install -e '.[editor,ops,redteam,dev]'
.venv/bin/python -m pytest -q
npm --prefix aegis/editor/frontend run lint
npm --prefix aegis/editor/frontend test
```

The default Python test run excludes tests that require a running large
language model (LLM). Set `AEGIS_LIVE_LLM=1` to include them. Browser tests use a
local server with deterministic test fixtures. See the
[contributor guide](CONTRIBUTING.md) for browser tests and wheel builds.

## Scope and documentation

The guard evaluates the modeled action or plan it receives. It does not verify
that natural-language rules were translated correctly or that facts declared by
the caller are true. Execution paths that bypass the guard fall outside its
guarantee.

- [Architecture](docs/architecture.md)
- [MELD language reference](docs/_archive/MELD_SPEC.md)
- [Security boundary and known limitations](docs/limitations.md)
- [Validation and formal models](docs/validation.md)
- [Release contents and preparation](docs/release.md)
- [Research foundations and third-party notices](THIRD_PARTY_NOTICES.md)

## Citation and publication status

The DOI badge links to archived software releases. Use
[10.5281/zenodo.23084278](https://doi.org/10.5281/zenodo.23084278) to cite the
archived v0.1.0 snapshot. [CITATION.cff](CITATION.cff) contains the citation
metadata.

The `main` branch includes updates beyond that snapshot. These commits retain
software version 0.1.0 and leave the Zenodo archive unchanged. The accompanying
research manuscript is being prepared for submission and has not yet been
published.

## License

AgenticAEGIS project contributions are licensed under the
[Apache License 2.0](LICENSE). See [NOTICE](NOTICE) and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for third-party notices and terms.
