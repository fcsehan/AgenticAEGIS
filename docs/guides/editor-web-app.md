# AEGIS web editor: local operation

Implementation snapshot: September 25, 2026. The application edits MELD domains,
checks actions and plans, and manages tested, published snapshots. It is a local,
single-user editor. See [known limitations](../limitations.md) for this snapshot's
boundaries.

## Installation and startup

Requirements: Python 3.12+, Node.js 22.12+ and a writable project directory.
Build the frontend using the committed lockfile. From the repository:

```sh
python3.12 -m venv .venv
npm --prefix aegis/editor/frontend ci
npm --prefix aegis/editor/frontend run build
.venv/bin/pip install -e '.[editor,dev]'
mkdir -p /path/to/projects
.venv/bin/aegis-editor --workspace /path/to/projects --port 8010 \
  --config-dir /path/to/editor-config
```

Open `http://127.0.0.1:8010`. Only one process/worker may write the configuration
and project state. Port 8010 is separate from the common inference port 8000.
For frontend development, `npm run dev` in the frontend directory serves port
5173 and proxies API requests to 8010.

Start the editor separately from the Guard API server. Build the frontend before
building a Python wheel; `frontend/dist` is explicitly included in the wheel.
An unbuilt source checkout returns HTTP 503 for the frontend. `/api/health`
reports readiness and version; `/openapi.json` exposes the API contract. Deep
links such as `/domain/pharma` remain available after reloading.

The CLI binds exclusively to `127.0.0.1`; the application also rejects nonlocal
client addresses. A reverse proxy is **not** a supported deployment mode:
authentication, individual user roles and multiple users are not implemented.
Do not forward this port to a LAN or the internet.

## Projects and editing

Open or create a directory inside the workspace from the dashboard. Each
subdirectory containing MELD files becomes a domain. Files directly in the
project use the reserved domain ID `~root`. Nested paths use encoded IDs.
Identifiers are independent of display names.

Structure forms save roles, obligation types, codes and action parameters.
Renaming updates symbol references; deleting referenced symbols is blocked.
Edit rules in forms or in the MELD editor. The four plan predicates have a
dedicated editor in Rules. Schema 2 formulas are preserved in the MELD editor;
the legacy rule/structure editor refuses to reinterpret them. Schema 1 code
precedence is saved as `(codePrevalence HighestCode ... LowestCode)` and loaded
by the Guard. Schema 2 retains its formula priorities.

MELD package import validates the file list, compilation and name collisions
before explicit adoption. Export in the MELD panel produces a JSON package
containing all current source files, which can be imported again. Domain metadata
and reversible archiving are also available there. Archiving does not deactivate
an already active runtime version.

Saving creates complete, content-addressed revisions under
`<project>/.aegis-editor/<domain-key>/<SHA-256>/` and atomically replaces the
revision pointer only after successful compilation. Original files remain the
import baseline. Revision conflicts return HTTP 409. External changes to original
files after creating a draft are not automatically merged into it; import or
transfer those changes explicitly.

The application remembers the open project on the server. Unsaved MELD input,
rule descriptions and model proposals also have a recovery copy in the same
browser tab's `sessionStorage`. This contains domain content but no provider
secrets and is not release evidence. Close the tab after work on a shared
computer. Stale drafts are rejected on save; **Load saved version** discards
the browser copy.

## Local models and APIs

1. Install/load a suitable model in LM Studio, Ollama or vLLM outside AEGIS and
   start its compatible HTTP service. The editor does not install models or
   manage GPUs and context windows.
2. Under **Inference settings**, select or add a profile. Templates include
   LM Studio at `http://localhost:1234/v1`, Ollama at
   `http://localhost:11434/v1` and vLLM at `http://localhost:8000/v1`.
   Additional instances can be configured.
3. Save the base URL, protocol, model ID, default profile and optional temperature,
   output-token limit and timeout. `localhost` means the **backend machine**,
   not another computer running the browser.
4. Explicitly check the connection and model list. An empty list does not
   establish tool support. Model IDs can still be entered manually.
5. Run the small tool-calling test in the AI assistant. Generation is enabled
   only after that test for the current profile revision and model ID. Repeat
   after a restart, settings change or failed probe.

Only the **name** of a backend environment variable is stored as an API secret
reference. Set its value before starting the server, for example in a protected
local shell environment. Do not enter the value in a form, repository or command
argument. To replace it, restart the backend with the changed value; to remove it,
remove the reference or variable. Profile values override inherited defaults.
`AEGIS_EDITOR_CONFIG_DIR` selects the storage location only when `--config-dir`
is absent; the default is `~/.config/aegis/editor`. `providers.json` uses schema 1
and file mode 0600. Unsupported schema versions are not silently migrated.

OpenAI-compatible and Anthropic Messages protocols are supported. Global keys are
not forwarded to arbitrary compatible servers. Redirects are rejected, TLS
certificates are verified, and connections are pinned to checked DNS addresses.
Link-local and metadata-service destinations are blocked. Private addresses
require profile opt-in. The MELD editor policy **also** decides authorization:
the supplied policy allows only loopback inference and prohibits remote targets.
LAN opt-in alone is not formal authorization. Load an administratively reviewed
alternative policy with `--policy-dir`. Profiles are also associated with the
model-list, capability-test, authoring or DIP channel. Domain content uses its
stored classification, confidential by default; DIP content is confidential.
The supplied policy explicitly allows these classifications only on the local
backend machine. Authorizing specific external recipients requires an extended,
reviewed policy. There is no cloud fallback. Container deployment requires
appropriate host addresses, trust boundaries and policy; `localhost` inside a
container refers to that container.

Jobs run in the background and have bounded execution. Cancellation prevents
adoption of late results; computation already running at the provider may
continue until its timeout. Jobs are session records discarded on backend
restart. Successful results identify the profile revision, model and parameters.
Paid inference is not retried automatically. Invalid or unverified model output
is not published as rules.

## Testing, review, release and runtime

Guard tests check the saved draft. Network errors are not `UNDECIDABLE` verdicts.
Scenarios store an expected result and exactly one action or plan. A plan uses
`steps` containing `action_type`, `agent_id`, `proposition` and optional state or
timing fields. AEGIS evaluates supplied plans; it does not generate them.

Release requires successful compilation, passing positive and negative scenarios,
current diagnostics and explicit review of the exact same revision. Reviews,
scenarios, tests and documentation are bound by hashes. Changes invalidate older
evidence. Repeated proposal verification does not increase coverage. Diagnostics
check concrete action instances and existing plan checks; they do not claim a
complete conflict proof for every symbolic context.

A published snapshot is activated separately. The target is exclusively
**editor-runtime**, `/api/domains/{id}/runtime/check`. This changes neither an
external Guard server nor the current draft. Without an active version, the
runtime returns an error. Rollback activates an earlier published revision after
rerunning its stored scenarios. The actor is `localOperator`; this operating
profile does not demonstrate independent review by a second person.

The web DIP accepts text and HTML, recording language, source title and source
hash. After reviewing the pipeline report, explicitly adopt generated files as a
new `generated-…` domain. The D-015 authoring path is used; existing domains are
not overwritten. PDF and URL ingestion are not implemented in this web flow.

## Backup, restore and updates

Stop the editor before backup or restore. To create a backup:

```sh
.venv/bin/aegis-editor --workspace /path/to/project \
  --config-dir /path/to/editor-config --backup /path/to/backup.zip
```

The archive contains MELD, snapshots, scenarios, review/version records, profiles
with secret references, audit files and checksums. It excludes credential
environment-variable values. Archives are limited to 100 MB; larger audit archives
need a separate archival process. Symbolic links are rejected.

Restore writes only to empty, separate target directories:

```sh
.venv/bin/aegis-editor --workspace /path/to/restored-project \
  --config-dir /path/to/restored-config --restore /path/to/backup.zip
.venv/bin/aegis-editor --workspace /path/to/restored-project \
  --config-dir /path/to/restored-config --port 8010
```

All archive names and checksums are checked before the first write. The stored
project path is remapped. Supply credential variables separately. An operating
system or disk failure during writing can leave incomplete targets; the original
and backup remain intact. Before updates, back up, install locked dependencies,
rebuild, run tests and restart. Multiple writer processes are unsupported.
Neither these features nor laboratory E2E tests automatically increase the TRL.

## Verification commands

```sh
.venv/bin/pytest tests/editor tests/formal tests/test_import_boundary.py
.venv/bin/mypy aegis/editor --ignore-missing-imports
.venv/bin/ruff check aegis/editor tests/editor/test_web_foundation.py
npm --prefix aegis/editor/frontend run build
npm --prefix aegis/editor/frontend run lint
npm --prefix aegis/editor/frontend test
npm --prefix aegis/editor/frontend exec -- playwright install chromium
AEGIS_TEST_PYTHON="$PWD/.venv/bin/python" npm --prefix aegis/editor/frontend run test:e2e
```

`test_authoring_e2e.py` is an optional live-inference test requiring
`AEGIS_LIVE_LLM=1`. Passing fixture tests do not replace it with a live success
claim. Full lint/type checks have inherited findings; see [contributing](../../CONTRIBUTING.md).
Current results and remaining acceptance boundaries: [validation](../validation.md).
