"""AEGIS exception hierarchy (D-004).

Three categories:
- LoadError: Startup failures → Guard does not start.
- EvaluationError: Runtime failures → Guard returns UNDECIDABLE.
- AuditWriteError: Infrastructure failures → Guard continues, operator alerted.
"""


class AegisError(Exception):
    """Base for all AEGIS errors."""


# ── Load-time errors (startup → Guard fails to start) ──────────────


class LoadError(AegisError):
    """Failed to load .meld files or build knowledge base."""


class MeldSyntaxError(LoadError):
    """Syntax error in .meld file."""

    def __init__(self, file: str, line: int, message: str) -> None:
        self.file = file
        self.line = line
        super().__init__(f"{file}:{line}: {message}")


class MeldReferenceError(LoadError):
    """Undeclared symbol or missing dependency in .meld file."""


class InheritanceCycleError(LoadError):
    """Circular inheritance detected in the inheritance network."""


class AxiomContradictionError(LoadError):
    """Contradictory moral axioms detected at load time."""


# ── Runtime errors (Guard.check() → UNDECIDABLE) ───────────────────


class EvaluationError(AegisError):
    """Error during norm evaluation. Mapped to UNDECIDABLE verdict."""


class EngineError(EvaluationError):
    """Internal error in the DDIC engine."""


class EvaluationTimeout(EvaluationError):
    """Evaluation exceeded its time limit."""


# ── Infrastructure errors (Guard continues, but reports) ────────────


class AuditWriteError(AegisError):
    """Audit trail could not be written. Non-fatal."""
