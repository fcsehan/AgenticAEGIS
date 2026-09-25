# Contributing

Use Python 3.12+ and Node.js 22.12+. Follow the README installation instructions,
then install the `editor,ops,redteam,dev` extras. Contributions are submitted
under Apache-2.0; preserve existing attribution and third-party notices.

## Design rules

- MELD is the source of normative rules. Do not embed domain norms in Python.
- Keep `aegis.deontic`, `aegis.engine` and `aegis.kb` independent of guard/host code.
- A failed or undecidable check must not authorize execution.
- Preserve the distinction between formal modeled-input guarantees and host assumptions.
- Add focused regression tests for semantic changes. Explain changes to verdicts.

## Checks

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest tests/test_import_boundary.py tests/formal -q
npm --prefix aegis/editor/frontend run build
npm --prefix aegis/editor/frontend run lint
npm --prefix aegis/editor/frontend test
git diff --check
```

For browser tests:

```sh
npm --prefix aegis/editor/frontend exec -- playwright install chromium
AEGIS_TEST_PYTHON="$PWD/.venv/bin/python" npm --prefix aegis/editor/frontend run test:e2e
```

Use `ruff check` and `mypy --strict` on changed Python code. The inherited codebase
has outstanding lint/type findings; these tools are not represented as a clean
whole-repository baseline. CI checks fatal Python errors, the Python tests and
the frontend build/lint/tests.

Live model tests require an explicitly configured local model and
`AEGIS_LIVE_LLM=1`. They are not part of offline CI. Never put provider credentials,
real confidential documents or runtime workspaces in a contribution.

## Build distributable packages

```sh
npm --prefix aegis/editor/frontend ci
npm --prefix aegis/editor/frontend run build
.venv/bin/python -m build
```

The frontend must be built before packaging. The wheel includes its static assets,
MELD domains and editor policy. Neither npm dependencies nor frontend test sources
belong in the wheel. The source archive includes the source and built frontend,
so it can also be used to build a wheel without Node.
