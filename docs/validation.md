# Validation

The test suite checks modeled policy behavior. Passing tests do not establish
universal agent safety or verify natural-language interpretation.

## Local commands

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest tests/formal tests/test_import_boundary.py -q
npm --prefix aegis/editor/frontend run build
npm --prefix aegis/editor/frontend run lint
npm --prefix aegis/editor/frontend test
AEGIS_TEST_PYTHON="$PWD/.venv/bin/python" npm --prefix aegis/editor/frontend run test:e2e
```

Browser tests use the fixture server in `tests/editor/serve_web_e2e.py`; they do
not establish live cloud-provider behavior. Live LLM tests require the explicit
`AEGIS_LIVE_LLM=1` opt-in. Tests requiring the excluded OpenCyc reference archive
skip when it is absent. Tests for the separate worldmodel and the old
repository-specific documentation linter are outside this distribution.

## OpenCode process evidence

The [OpenCode integration](../integrations/opencode/README.md) has its own
setup and test command, separate from the default Python suite. It starts the
pinned upstream executable and the actual Guard sidecar, injects tool calls
through a deterministic model endpoint, and checks resulting file contents
and correlated audit records. Optional local-model cases use
`AEGIS_OPENCODE_LIVE=1`. Reports separate these from deterministic tests.

The [validation record](../integrations/opencode/evidence/README.md) identifies
the verified release, scope and actual runs. The archived fork patch is a
separate source artifact; results are not transferred between host versions.

## Formal models

The TLA+ sources and small model configurations are in [spec/formal](../spec/formal/README.md).
Run TLC separately with a locally installed TLA+ toolchain. The models abstract
parts of the implementation; a model check is not a mechanized proof of the
Python implementation. Historical verification/conformance notes remain under
`docs/spec/`; consult [known limitations](limitations.md) for this snapshot.

## Release verification

The initial extraction verification is recorded in [release preparation](release.md).
CI repeats Python tests and frontend checks on future changes. No live-model,
production deployment or new TLC result is implied by those checks.
