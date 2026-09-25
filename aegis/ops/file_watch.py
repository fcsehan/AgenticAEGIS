"""AEGIS-1308: File Watcher for Domain Hot-Reload.

Watches a directory for .meld file changes and triggers Guard reload.
Debounces changes (2 seconds after last change).
"""

from __future__ import annotations

import contextlib
import logging
import threading
from pathlib import Path

from aegis.guard.guard import Guard
from aegis.ops.reload import reload_guard

logger = logging.getLogger(__name__)

_DEBOUNCE_SECONDS = 2.0


class MeldFileWatcher:
    """Watches a directory for .meld changes and triggers Guard reload.

    Usage::

        watcher = MeldFileWatcher(guard, Path("./domains"))
        watcher.start()
        # ... later ...
        watcher.stop()
    """

    def __init__(self, guard: Guard, watch_dir: Path) -> None:
        self._guard = guard
        self._watch_dir = watch_dir
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_mtimes: dict[str, float] = {}

    def start(self) -> None:
        """Start watching in a background thread."""
        self._scan_mtimes()
        self._thread = threading.Thread(
            target=self._watch_loop, daemon=True, name="meld-watcher"
        )
        self._thread.start()
        logger.info("File watcher started for %s", self._watch_dir)

    def stop(self) -> None:
        """Stop watching."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("File watcher stopped")

    def _scan_mtimes(self) -> dict[str, float]:
        """Scan all .meld files and record modification times."""
        mtimes: dict[str, float] = {}
        for meld_file in self._watch_dir.rglob("*.meld"):
            with contextlib.suppress(OSError):
                mtimes[str(meld_file)] = meld_file.stat().st_mtime
        self._last_mtimes = mtimes
        return mtimes

    def _watch_loop(self) -> None:
        """Poll for changes with debounce."""
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=_DEBOUNCE_SECONDS)
            if self._stop_event.is_set():
                break

            current = {}
            for meld_file in self._watch_dir.rglob("*.meld"):
                with contextlib.suppress(OSError):
                    current[str(meld_file)] = meld_file.stat().st_mtime

            if current != self._last_mtimes:
                logger.info("Detected .meld file changes, reloading...")
                meld_paths = sorted(
                    Path(p) for p in current
                )
                success = reload_guard(self._guard, meld_paths)
                if success:
                    self._last_mtimes = current
                else:
                    logger.warning("Reload failed, keeping current domain version")
