# AgenticAEGIS

**A deterministic policy guard for structured actions and plans, with a local web editor for MELD rule authoring.**

AEGIS stands for *Architectural Ethics Guard for Intelligent Systems*. An agent,
workflow or service proposes an action; the guard evaluates it against a compiled
rule base and returns `PERMITTED`, `FORBIDDEN` or `UNDECIDABLE`, with a justification.
Only `PERMITTED` should authorize execution. The host must enforce that contract.

The Python import remains `aegis`; the distribution is named `agentic-aegis`.
This is a research prototype, not a certification of an agent or application.

## Included

- Python DDIC reasoning, MELD loading, action and plan checking.
- Six example domains: DevOps, IAMission, pharma, sanctions, legal and information flow.
- A React/TypeScript web editor with persistent projects, rule and plan editors,
  scenario tests, revision-bound review, release, activation and rollback.
- Optional local model integration and document-assisted rule proposals. Proposed
  rules require validation and review; the model is not the normative authority.
- Guard REST API, audit, information-flow components and red-team tooling.
- Automated tests and TLA+ specifications.

AEGIS evaluates plans; it does not generate them. Plan constraints cover order,
aggregate limits, declared timing and state preconditions. They compose with
DDIC-resolved action verdicts; they are not themselves DDIC inference rules.

## Run the web editor

Requirements: Python 3.12+, Node.js 22.12+ and npm. From this repository:

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

Open **http://127.0.0.1:8010** and open the workspace project. The editor is
restricted to local, single-user operation. It does not provide a multi-user
authentication service and must not be exposed through a reverse proxy.
Manual authoring and guard checks do not require a model or API key.

See the [web editor guide](docs/guides/editor-web-app.md) for provider setup,
review, activation, backup and recovery. The supplied editor policy permits
loopback inference only; choosing a remote provider does not grant permission
to transmit domain content to it.

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

The example paths are relative to a source checkout. Installed applications can
locate bundled domains via `importlib.resources.files("aegis") / "domains"`.
See [Python and REST usage](docs/usage.md) for plan checking and service startup.

## OpenCode integration

[Install and test the OpenCode integration](integrations/opencode/README.md)
against a pinned upstream release. The reproducible process tests run the real
OpenCode host and AEGIS sidecar, checking file effects for permitted, forbidden,
undecidable and failed guard requests, plus declared-plan enforcement.
The integration includes a verified download, plugin, MELD fixtures, CI workflow
and [recorded evidence](integrations/opencode/evidence/README.md).

## Development

```sh
.venv/bin/python -m pip install -e '.[editor,ops,redteam,dev]'
.venv/bin/python -m pytest -q
npm --prefix aegis/editor/frontend run lint
npm --prefix aegis/editor/frontend test
```

The default Python run excludes tests that require a live LLM; use
`AEGIS_LIVE_LLM=1` to opt in. Browser tests use a deterministic local fixture
server. See [contributing](CONTRIBUTING.md) for browser tests and wheel builds.

## Scope and documentation

- [Architecture](docs/architecture.md)
- [MELD language reference](docs/_archive/MELD_SPEC.md)
- [Security boundary and known limitations](docs/limitations.md)
- [Validation and formal models](docs/validation.md)
- [Release contents and preparation](docs/release.md)
- [Research foundations and third-party notices](THIRD_PARTY_NOTICES.md)

The guarantee starts with the modeled action or plan submitted to the guard.
It does not establish that natural-language rules were translated correctly,
that caller-declared facts are true, or that an unmediated host path is safe.

## License

AgenticAEGIS project contributions are licensed under the
[Apache License 2.0](LICENSE). Retained third-party notices and terms are listed
in [NOTICE](NOTICE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
