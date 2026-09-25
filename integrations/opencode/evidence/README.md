# Recorded validation

On 2026-09-25, the integration was exercised locally on macOS ARM64 with the
official **OpenCode v1.18.32** executable, upstream commit
`545f51d26cc39a907d2867492d498d9607ea5fa4`.

| Suite | Result | Scope |
| --- | --- | --- |
| Plugin contract tests | 17 passed | Transport failures, verdict handling, argument binding, audit and plan lifecycle |
| Deterministic process tests | 10 passed | Real OpenCode executable, real AEGIS sidecar and controlled model transport |
| Local live-model process tests | 2 passed | Permitted and forbidden writes proposed by `qwen/qwen3.8-27b` through OpenCode |
| Historical fork restoration | Passed | Patch applied to its exact upstream source; all three resulting files match the archived fork hashes |

The local server reported the loaded Qwen model as a 4-bit model. The live
cases used the OpenAI-compatible endpoint of the existing local LM Studio
server and OpenCode's default generation settings. These two observed runs
are not a statistical model evaluation or a determinism claim.

The machine-readable [run report](2026-09-25-macos-arm64.json) contains the
executable identity, source hashes, test counts, per-case verdicts, argument
hashes and filesystem observations. Generated case and repository paths are
replaced with `<case>` and `<repository>`. Case traces record whether a file
exists; the corresponding test assertions additionally verify its content
(including preservation of an existing protected file).

Reproduce with the [documented setup and test commands](../README.md#reproduce).
The standard command skips the two live-model cases unless explicitly enabled.
Reports from new runs go to `.runs/`; they do not overwrite this recorded result.

The current plugin was validated with the official release executable. Source
archive extraction and checksum verification were checked separately; a local
rebuild of the upstream executable was not part of this validation. Linux CI
is configured but has not yet run on GitHub.

The [enforcement boundary](../README.md#enforcement-boundary) is part of this
evidence. In particular, sidecar-outage tests assume a loaded plugin and do
not establish fail-closed behavior if the host skips plugin initialization.
