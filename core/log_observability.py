"""Fehler-Observability: leitet WARNING/ERROR-Logs automatisch ins events_log,
damit sie im Dashboard-Fehler-Widget ("Was ist heute schiefgelaufen") auftauchen.

Motivation: Im Qualitäts-Pass wurden viele stille `except: pass` in `log.warning(...)`
umgewandelt. Ohne diese Brücke bleiben sie im Logfile verborgen. Jetzt werden sie
sichtbar — mit Dedup/Rate-Limit pro Fehlersignatur, damit ein in einer Schleife
wiederholter Fehler das Widget nicht flutet.

Robustheit: Fehler IM Handler werden verschluckt (niemals Logging-Rekursion oder
Start-Absturz), und Logs der DB-Schicht selbst werden nicht zurückgeschrieben.
"""
from __future__ import annotations

import logging
import time

_DEDUP_WINDOW_S = 300   # gleiche Fehlersignatur höchstens alle 5 min in die DB
_MAX_TRACKED = 512      # Obergrenze für den Dedup-Speicher


class DBLogHandler(logging.Handler):
    """Schreibt Log-Records ab WARNING ins events_log (dedupliziert)."""

    def __init__(self, level: int = logging.WARNING):
        super().__init__(level)
        self._last_seen: dict[str, float] = {}

    @staticmethod
    def _signature(record: logging.LogRecord) -> str:
        return f"{record.name}:{record.levelno}:{str(record.msg)[:80]}"

    def _is_duplicate(self, sig: str, now: float) -> bool:
        last = self._last_seen.get(sig)
        if last is not None and (now - last) < _DEDUP_WINDOW_S:
            return True
        if len(self._last_seen) > _MAX_TRACKED:
            self._last_seen.clear()  # simpler Überlauf-Reset statt echtem LRU
        self._last_seen[sig] = now
        return False

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if record.levelno < logging.WARNING:
                return
            # DB-Schicht-Logs NICHT zurückschreiben (Rekursions-/Sturm-Schutz)
            if record.name.startswith("core.db"):
                return
            if self._is_duplicate(self._signature(record), time.monotonic()):
                return
            from core import db
            db.log_event(
                "error",
                f"[{record.name}] {record.getMessage()}"[:500],
                {"logger": record.name, "level": record.levelname, "module": record.module},
            )
        except Exception:
            pass  # Observability darf niemals selbst crashen


def install(level: int = logging.WARNING) -> DBLogHandler:
    """Hängt den DB-Handler an den Root-Logger. Idempotent."""
    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, DBLogHandler):
            return h
    handler = DBLogHandler(level=level)
    root.addHandler(handler)
    return handler
