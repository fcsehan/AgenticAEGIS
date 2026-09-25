# OpenCode integration and reproducible evidence

This package runs **OpenCode v1.18.32** with an AEGIS plugin and a real AEGIS
HTTP sidecar. Tests inspect actual filesystem effects. A deterministic model
endpoint supplies tool calls through OpenCode's normal model interface; it
does not invoke the plugin or execute tools itself.

The current integration uses the release's `tool.execute.before` and
`tool.execute.after` hooks. No host patch is required for this tested path.
The original fork is preserved separately as a reproducible historical patch.

## Reproduce

Requirements: Python 3.12+, Node.js 22.12+ with npm, and macOS or Linux on
ARM64/x64. Setup needs access to GitHub and npm. It installs into `.cache/`
and does not replace a globally installed OpenCode.

From the repository root:

```sh
python3.12 -m venv .venv
npm --prefix aegis/editor/frontend ci
npm --prefix aegis/editor/frontend run build
.venv/bin/python -m pip install -e '.[api,ops,dev]'
export AEGIS_TEST_PYTHON="$PWD/.venv/bin/python"
integrations/opencode/scripts/setup.sh
integrations/opencode/scripts/test.sh
```

Setup verifies the release archive's SHA-256 and executable version against
[upstream.lock.json](upstream.lock.json). The runtime plugin dependency tree
is installed with `npm ci` from [runtime/package-lock.json](runtime/package-lock.json).
The test suite verifies the installed executable hash before starting it.

Each run writes a new `.runs/run.*/report.json`, JUnit reports and sanitized
case traces. The report records the upstream commit, executable identity,
test counts, platform, source checksums, verdicts and observed file effects.
Raw logs and isolated workspaces stay in the ignored run directory.

The [OpenCode CI workflow](../../.github/workflows/opencode.yml) repeats the
deterministic suites on Linux and uploads their reports. A configured workflow
is not evidence of a successful GitHub run; see the checked-in
[validation record](evidence/README.md) for actual local results.

## What the tests establish

| Scenario | Required observable result |
| --- | --- |
| Explicit permission | OpenCode writes the requested content; decision and execution records share the call ID and argument hash. |
| Read followed by edit | OpenCode reads a permitted file and applies the checked edit. |
| Explicit prohibition | Existing protected content stays unchanged. |
| Contradictory norms | The real guard returns `UNDECIDABLE`; no file is created. |
| Guard unavailable | No file is created. |
| Guard response exceeds deadline | No file is created, even when the delayed guard response would permit it. |
| Unmodeled shell tool | No shell marker file is created. |
| Rejected declared plan | Neither of two individually permitted writes executes when their aggregate violates the plan rule. |
| Permitted declared plan | The matching step executes after plan approval and an individual action check. |
| Changed plan arguments | A different target is blocked before execution. |

Plugin tests additionally exercise malformed and mismatched responses, HTTP
errors, frozen arguments, fresh checks after argument changes, path traversal,
symlinks escaping the workspace and audit-write failure.

The conflict fixture deliberately preserves the existing guard behavior:
`UNDECIDABLE` may carry `CWA_NO_PERMISSION` as its reason type. The integration
retains the original verdict and authorizes only `PERMITTED`.

## Optional local model run

Start an OpenAI-compatible local model server with a model capable of tool use.
Use its actual model identifier:

```sh
AEGIS_OPENCODE_LIVE=1 \
AEGIS_OPENCODE_LIVE_URL=http://127.0.0.1:1234/v1 \
AEGIS_OPENCODE_LIVE_MODEL=your-loaded-model-id \
AEGIS_TEST_PYTHON="$PWD/.venv/bin/python" \
integrations/opencode/scripts/test.sh
```

This adds permitted and forbidden write scenarios through the same real
OpenCode process. Live model behavior is not deterministic. Without the
explicit opt-in, these two cases are reported as skipped. A refusal without an
attempted guarded tool call does not satisfy the live enforcement test.

## Use the plugin

The mapping currently supports OpenCode's `read`, `write` and `edit` tools.
They become `readFile` or `modifyFile` with a workspace-relative `path`.
Author policy in MELD for those paths. The bundled fixture domain grants
writes to `allowed.txt` and `second.txt`, prohibits `protected.txt`, and limits
a declared plan to one write. It is a demonstration policy.

Start the guard in one terminal, from the repository root:

```sh
AEGIS_AUDIT_PATH=/tmp/aegis-opencode-guard.jsonl \
.venv/bin/aegis serve \
  --domains integrations/opencode/fixtures/domain \
  --host 127.0.0.1 --port 8000
```

In your OpenCode configuration, add the absolute file URL of
`integrations/opencode/plugin/index.mjs` to the `plugin` array. Python can
print the URL from the repository root:

```sh
.venv/bin/python -c 'from pathlib import Path; print(Path("integrations/opencode/plugin/index.mjs").resolve().as_uri())'
```

Run the verified executable from the intended workspace with:

```sh
AEGIS_OPENCODE_GUARD_URL=http://127.0.0.1:8000 \
AEGIS_OPENCODE_AGENT_ID=opencodeAgent \
AEGIS_OPENCODE_AUDIT_PATH=/tmp/aegis-opencode-plugin.jsonl \
/absolute/path/to/AgenticAEGIS/integrations/opencode/.cache/opencode
```

The audit file's parent directory must exist and be writable. Set
`AEGIS_OPENCODE_TIMEOUT_MS` to change the default 3,000 ms deadline.
Only loopback HTTP sidecars are accepted by this adapter. Keep the plugin,
configuration, domain files and audit paths outside model-writable locations.

## Declared plans

Set `AEGIS_OPENCODE_PLAN` to an operator-controlled JSON file:

```json
{
  "plan_id": "single-write",
  "initial_state": {},
  "steps": [
    {
      "tool": "write",
      "args": {
        "filePath": "/absolute/path/to/workspace/allowed.txt",
        "content": "Reviewed content\n"
      },
      "duration_s": 0,
      "post_state": {}
    }
  ]
}
```

Before the first matching tool call, the plugin submits the whole declared
plan to `/v1/plan_check`. A rejected or undecidable plan stops before any
step executes. Each permitted step still gets a fresh `/v1/check` immediately
before execution. Tool names and complete arguments must match the declared
sequence. Concurrent steps, substitutions and calls beyond its end are blocked.

Use one dedicated process/session per declared plan. A failed tool execution
without an `after` hook leaves the plan blocked; restart with a reviewed plan.
This adapter does not infer a plan from the model's prose or automatically
aggregate an open-ended conversation. Durations and state fields remain
declarations, not observed wall-clock or filesystem state.
Keep the rulebase fixed for a declared-plan run. This adapter does not bind a
plan approval to a remotely attested rulebase revision or support hot reload.

## Enforcement boundary

- The tested surface is the modeled file tools and declared sequential plans.
  Shell, network, delegation, custom and other unmodeled tools are blocked.
  The historical shell-pattern mapper and taint heuristic are not claimed as
  verified capabilities of this current adapter.
- Norms evaluate the modeled path/action. Content hashes bind audit records
  to arguments; they do not establish that file content is safe or correct.
- The host must load the plugin and route tools through its hooks. Upstream
  plugin initialization failures can be logged and skipped; plugin absence or
  load failure is therefore **not** covered by sidecar-outage fail-closed tests.
  There is no claim of tamper resistance against the host operator or other
  trusted plugins. The tests require initialization and decision records.
- Filesystem races, hostile concurrent changes, external formatters/LSPs,
  background host activity and direct user shell commands are outside this
  demonstration's guarantee. Tests disable formatters and LSPs, isolate config
  and use a temporary workspace. Path canonicalization blocks existing symlink
  escapes but is not an operating-system sandbox.
- Plugin audit records correlate decisions and completed hooks. The sidecar
  audit has its own integrity check. A plugin `after` hook is not a transaction
  commit, and audit failure after a tool effect cannot undo that effect.

See also [the repository's limitations](../../docs/limitations.md).

## Source and historical fork

`setup.sh --source` also verifies and extracts the exact current source archive
for inspection. The tested host is the official release binary; no claim of a
locally reproduced binary build is made. Upstream declares Bun 1.3.14 for
source builds. The lock records this separately from the Node test runtime.

The historical patch includes both the original three-file integration commit
and the additional adapter changes present during extraction:

```sh
.venv/bin/python integrations/opencode/scripts/restore_legacy.py
```

This verifies [legacy.lock.json](legacy.lock.json), downloads its exact source
archive, checks patch applicability and applies
[legacy-aegis.patch](patches/legacy-aegis.patch) in `.cache/legacy/`.
It preserves the old implementation for inspection; current validation results
do not apply to it. In particular, a plan transport method alone does not prove
that OpenCode enforces complete plans.

OpenCode is MIT-licensed; its retained license is in
[patches/OPENCODE_LICENSE](patches/OPENCODE_LICENSE). New AEGIS integration code
uses the repository's Apache-2.0 license.

Upstream references: [release](https://github.com/anomalyco/opencode/releases/tag/v1.18.32),
[source commit](https://github.com/anomalyco/opencode/tree/545f51d26cc39a907d2867492d498d9607ea5fa4),
[plugin documentation](https://opencode.ai/docs/plugins/).
