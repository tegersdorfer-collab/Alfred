"""
core/status.py

Globaler Status-Bus – Jarvis-Aktivitäten in Echtzeit.

Jede Komponente kann Status-Updates emittieren:
    from core.status import BUS
    BUS.emit("thinking", "Analysiere deine Frage...")
    BUS.emit("tool", "Wetter abrufen", detail="München")
    BUS.emit("memory", "Neue Erinnerung gespeichert")
    BUS.emit("idle", "Bereit")

Das Dashboard subscribt via SSE und zeigt alles live an.
"""
import asyncio
import time
from dataclasses import asdict, dataclass, field
from typing import Optional


# ── Event-Typ ──────────────────────────────────────────────────────────────────

@dataclass
class StatusEvent:
    type: str              # "thinking" | "tool" | "memory" | "learning" | "idle" | "autopilot" | "error"
    text: str              # kurze Beschreibung für den User
    detail: Optional[str] = None   # optionaler Zusatz (Tool-Name, Model, etc.)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "text": self.text,
            "detail": self.detail,
            "ts": self.ts,
        }


# ── Bus ────────────────────────────────────────────────────────────────────────

class StatusBus:
    """
    Zentrale Schaltstelle für Echtzeit-Status-Events.
    Thread-sicher über asyncio.Queue (alle Komponenten laufen im gleichen Event-Loop).
    """

    def __init__(self, history_size: int = 30):
        self._current  = StatusEvent(type="idle", text="Bereit")
        self._history: list[StatusEvent] = []
        self._history_size = history_size
        self._listeners: list[asyncio.Queue] = []

    # ── Schreiben ──────────────────────────────────────────────────────────────

    def emit(self, type_: str, text: str, detail: str | None = None) -> None:
        """Status-Update aussenden. Kann aus jedem asyncio-Kontext aufgerufen werden."""
        evt = StatusEvent(type=type_, text=text, detail=detail)
        self._current = evt
        self._history.append(evt)
        if len(self._history) > self._history_size:
            self._history = self._history[-self._history_size:]
        for q in self._listeners[:]:
            try:
                q.put_nowait(evt)
            except asyncio.QueueFull:
                pass  # Langsamer Client – Event überspringen, kein Absturz

    # ── Lesen ──────────────────────────────────────────────────────────────────

    @property
    def current(self) -> StatusEvent:
        return self._current

    @property
    def history(self) -> list[StatusEvent]:
        return list(self._history)

    # ── Subscriber-Verwaltung ──────────────────────────────────────────────────

    def subscribe(self) -> asyncio.Queue:
        """Registriert einen neuen Listener. Gibt Queue zurück."""
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._listeners.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._listeners.remove(q)
        except ValueError:
            pass


# ── Globaler Singleton ─────────────────────────────────────────────────────────

BUS = StatusBus()
