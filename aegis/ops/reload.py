"""AEGIS-1308: Domain Hot-Reload.

Provides atomic domain reload for the Guard without request interruption.
Three triggers: API call, file watch, SIGHUP.
"""

from __future__ import annotations

import logging
from pathlib import Path

from aegis.errors import LoadError
from aegis.guard.guard import Guard
from aegis.kb.builtins import BuiltinEngine
from aegis.kb.knowledge_base import KnowledgeBase
from aegis.kb.meld_loader import MeldLoader

logger = logging.getLogger(__name__)


def reload_guard(guard: Guard, meld_paths: list[Path]) -> bool:
    """Reload a Guard with new .meld files. Atomic swap per D-006.

    Returns True on success, False on failure (Guard continues with old KB).
    """
    try:
        kb = KnowledgeBase()
        loader = MeldLoader(kb)

        for path in meld_paths:
            loader.load_file(path)

        kb.freeze()

        reasoner = BuiltinEngine(kb)
        reasoner.compute()

        guard.reload(kb, loader.norms)
        logger.info(
            "Domain reload successful: %d facts, %d norms",
            kb.fact_count,
            len(loader.norms),
        )
        return True

    except LoadError as e:
        logger.error("Domain reload failed (LoadError): %s", e)
        return False
    except Exception as e:
        logger.exception("Domain reload failed (unexpected): %s", e)
        return False
