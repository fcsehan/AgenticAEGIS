# AgenticAEGIS contributor instructions

All effective modeled action and information paths must be mediated by a
fail-closed, auditable guard. Unmodeled paths must be blocked or explicitly
documented as residual risks.

- Python 3.12+, typed code; React/TypeScript frontend in `aegis/editor/frontend`.
- MELD is the normative source; `DDICModule` is the compiled representation.
- Core packages (`aegis.deontic`, `aegis.engine`, `aegis.kb`) never import Guard.
- AEGIS evaluates actions and caller-supplied plans; it does not generate plans.
- Preserve three verdicts and document their actual operational semantics.
- Keep secrets, runtime data and generated dependencies out of Git.
- Run relevant tests and `git diff --check` before committing.
- Read `CONTRIBUTING.md` and `docs/limitations.md` before changing behavior.
- Do not claim that a TLA+ model proves the Python implementation correct.
