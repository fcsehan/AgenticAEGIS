"""aegis-core — Public API surface for the DDIC reasoning engine.

This module defines the boundary between aegis-core (pure deontic reasoning)
and aegis-guard (security infrastructure). Everything importable from here
is the stable core API. Everything outside is guard-side infrastructure.

Core packages (pure computation, no I/O):
    aegis.deontic    — modality, norm_frame, norm_status, conflicts
    aegis.engine     — ddic, inheritance, pattern_matcher
    aegis.kb         — knowledge_base, meld_loader, builtins, microtheory
    aegis.errors     — exception hierarchy

Guard packages (infrastructure, I/O, hosts):
    aegis.guard      — Guard.check() bridge, pipeline, registry, verdict
    aegis.api        — HTTP server, tool schema
    aegis.ifc        — broker, provenance, taint, channels
    aegis.hardening  — output guard, taint tracker, permits
    aegis.orchestrator, aegis.audit, aegis.ops, aegis.redteam, aegis.editor

Import rule: Core NEVER imports Guard. Guard imports Core.
Enforced by CI check (see tests/test_import_boundary.py).

Usage::

    from aegis.core import DDICEngine, DeonticModality, NormFrame, KnowledgeBase, MeldLoader

    kb = KnowledgeBase()
    loader = MeldLoader(kb)
    loader.load_file(Path("domain.meld"))
    kb.freeze()

    engine = DDICEngine(InheritanceGraph(BuiltinEngine(kb)))
    status = engine.evaluate(
        proposition=("shareIntelligence", "classified"),
        agent="agent-007",
        norms=loader.norms,
    )
    # status.modality → FORBIDDEN / PERMITTED / OBLIGATORY / None
"""

# ── Deontic Logic ────────────────────────────────────────────────
from aegis.deontic.conflicts import Conflict, ConflictType, detect_conflicts
from aegis.deontic.modality import DEONTIC_PREDICATES, DeonticModality
from aegis.deontic.norm_frame import NormFrame
from aegis.deontic.norm_status import NormStatus

# ── DDIC Engine ──────────────────────────────────────────────────
from aegis.engine.ddic import DDICEngine, MAX_APPLICABLE_NORMS
from aegis.engine.inheritance import InheritanceGraph
from aegis.engine.pattern_matcher import FAIL, unify

# ── Knowledge Base ───────────────────────────────────────────────
from aegis.kb.builtins import BuiltinEngine
from aegis.kb.knowledge_base import KnowledgeBase
from aegis.kb.meld_loader import MeldLoader
from aegis.kb.microtheory import Microtheory

# ── Errors (shared) ─────────────────────────────────────────────
from aegis.errors import (
    AegisError,
    AuditWriteError,
    AxiomContradictionError,
    EngineError,
    EvaluationError,
    EvaluationTimeout,
    InheritanceCycleError,
    LoadError,
    MeldReferenceError,
    MeldSyntaxError,
)

__all__ = [
    # Deontic
    "DeonticModality",
    "DEONTIC_PREDICATES",
    "NormFrame",
    "NormStatus",
    "Conflict",
    "ConflictType",
    "detect_conflicts",
    # Engine
    "DDICEngine",
    "MAX_APPLICABLE_NORMS",
    "InheritanceGraph",
    "FAIL",
    "unify",
    # KB
    "KnowledgeBase",
    "MeldLoader",
    "BuiltinEngine",
    "Microtheory",
    # Errors
    "AegisError",
    "LoadError",
    "MeldSyntaxError",
    "MeldReferenceError",
    "InheritanceCycleError",
    "AxiomContradictionError",
    "EvaluationError",
    "EngineError",
    "EvaluationTimeout",
    "AuditWriteError",
]
