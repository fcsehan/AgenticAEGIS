"""AEGIS runtime hardening — Epics 15 & 16.

Closes the three runtime gaps identified by red-team testing:
1. Text leaks (OutputFilter + TaintTracker)
2. Unbound permits (PermitStore)
3. Schema drift (ActionCatalog + normalize_action)
"""

from aegis.hardening.action_catalog import ActionCatalog
from aegis.hardening.normalize import NormalizationResult, normalize_action
from aegis.hardening.output_guard import OutputCheckResult, OutputFilter
from aegis.hardening.permit import PermitStore, PermitToken
from aegis.hardening.refusal import RefusalRegistry, RefusalTemplate
from aegis.hardening.taint import TaintLevel, TaintMarker, TaintTracker

__all__ = [
    "ActionCatalog",
    "NormalizationResult",
    "OutputCheckResult",
    "OutputFilter",
    "PermitStore",
    "PermitToken",
    "RefusalRegistry",
    "RefusalTemplate",
    "TaintLevel",
    "TaintMarker",
    "TaintTracker",
    "normalize_action",
]
