# Initial public repository preparation

Prepared on 2026-09-24 as an independent source snapshot with a fresh Git root.
No prior Git objects, branches, tags, remotes or authoring history are imported.

## Included

- Current Python modules, including uncommitted source changes present at extraction.
- Current React/TypeScript editor source and npm lockfile.
- Six example MELD domains, editor policy, regression tests and red-team fixtures.
- Installation, usage, architecture, language, validation and boundary documentation.
- TLA+ source models, Apache-2.0 license and upstream notices.
- OpenCode integration source, pinned download metadata, historical patch and process tests.

## Excluded

- Research PDF collections, private correspondence, paper drafts and presentations.
- Project memory, internal epic backlog and archived planning documents.
- Worldmodel training/prototyping, full external OpenCode checkout and other standalone host packages.
- Installed dependencies, virtual environments, build outputs, screenshots and logs.
- Runtime workspaces, provider profiles and credentials.
- Legacy Docker examples that do not match the current loopback-only editor.

The Python distribution is `agentic-aegis`; imports and command names remain
`aegis`, `aegis-editor` and `aegis-redteam`. Source behavior is preserved except
for publication metadata, attribution, packaging and explicit live-test opt-in.
Known inherited behavior is documented in [limitations](limitations.md).

## Verification record

Checked locally on macOS with Python 3.12.14, Node.js 26.9.0 and npm 11.19.1:

| Check | Result |
| --- | --- |
| Python regression suite | 2,101 passed, 6 skipped |
| Frontend unit tests | 97 passed across 12 files |
| Browser workflow tests | 5 passed with deterministic HTTP model fixtures |
| Frontend TypeScript/Vite build and ESLint | Passed |
| Python fatal-error lint (`E9,F63,F7,F82`) | Passed |
| Python dependency consistency (`pip check`) | Passed |
| Source archive, then wheel rebuilt from that archive | Passed |
| Wheel installed in a separate environment outside the checkout | Passed |
| Installed guard example, editor health, HTML and license-notice endpoints | Passed |
| Tracked-file/package surface and focused credential-pattern scan | Passed |
| Local Markdown link targets and Git whitespace check | Passed |

The six skipped tests comprise two checks needing an excluded OpenCyc reference
archive and four explicitly disabled live-model orchestrator checks. Three other
live-model test modules are excluded from collection unless `AEGIS_LIVE_LLM=1`.
The Python run emits a Starlette/httpx deprecation warning; the frontend build
emits a chunk-size warning. Neither prevents the verified build or test results.
No live-model validation, new TLC run, production validation or complete
dependency-license/security audit was performed as part of this extraction.

CI is configured for Python 3.12 and Node.js 22. It has not run on GitHub yet.

## GitHub publication

The repository is prepared locally. No GitHub repository, remote or public push
is created by this preparation. Choose the owner/repository when publishing;
there are no placeholder repository URLs in package metadata.

Before tagging a release, review the snapshot and known limitations, retain
third-party notices, and build the distribution using `python -m build` after
the frontend build. `scripts/check_release.py` checks the repository surface
and package contents. It is a focused packaging check, not a comprehensive
secret scanner or license audit.
