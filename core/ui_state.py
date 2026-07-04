"""
UI-State — Grundlage des generativen UI (Phase 2, erster Durchstich).

Ordnet Tool-Aufrufe aus dem Agent-Trace deterministisch Widget-Typen zu (kein
Extra-LLM-Call) und hält den aktuell aktiven Widget-Slot. Publish/Subscribe
im selben Stil wie core/status.py::StatusBus — ein neuer, eigener Bus statt
Wiederverwendung von StatusBus, weil UI-State ein MATERIALISIERTER Zustand
ist (ein neu verbindender Client braucht den aktuellen Slot sofort), nicht
nur ein Ereignis-Strom.
"""
import asyncio
import logging
import time
from typing import Any

log = logging.getLogger(__name__)

# Tool-Name → Widget-Typ. Phase 2: bewusst nur ein Eintrag, Rest folgt in
# Phase 3 mit der vollen Widget-Bibliothek + Layout-Vorlagen.
WIDGET_MAP: dict[str, str] = {
    "get_health": "sleep",
}


def widget_type_for_tool(tool_name: str) -> str | None:
    return WIDGET_MAP.get(tool_name)


def sleep_widget_payload(dashboard: Any, days: int = 7) -> dict:
    """Baut strukturierte Schlaf-Daten für das Sleep-Widget — unabhängig vom
    LLM-Text-Ergebnis von get_health, direkt aus DashboardReader."""
    rows = dashboard.get_recent_health(days=days)
    return {
        "widget": "sleep",
        "nights": [
            {
                "date": r.date.isoformat(),
                "hours": r.sleep_duration,
                "deep_hours": r.sleep_deep,
            }
            for r in rows
        ],
    }


class UIStateBus:
    """Hält den aktuell aktiven Widget-Slot + Live-Updates für SSE-Subscriber."""

    def __init__(self) -> None:
        self._current: dict | None = None
        self._listeners: list[asyncio.Queue] = []

    @property
    def current(self) -> dict | None:
        return self._current

    def show_widget(self, widget_type: str, payload: dict) -> None:
        evt = {"widget": widget_type, "payload": payload, "ts": time.time()}
        self._current = evt
        self._broadcast(evt)

    def clear(self) -> None:
        self._current = None
        self._broadcast({"widget": None})

    def _broadcast(self, evt: dict) -> None:
        for q in self._listeners[:]:
            try:
                q.put_nowait(evt)
            except asyncio.QueueFull:
                pass  # langsamer Client — Event überspringen, kein Absturz

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._listeners.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._listeners.remove(q)
        except ValueError:
            pass


UI_BUS = UIStateBus()


def maybe_update_ui(tools_used: list[str]) -> None:
    """Nach einem Agent-Turn aufgerufen: prüft ob ein genutztes Tool einem
    Widget zugeordnet ist, baut bei Treffer die Daten und pusht sie.
    Fehler werden geschluckt — UI-Updates dürfen nie einen Chat-Turn brechen."""
    for tool_name in tools_used:
        widget_type = widget_type_for_tool(tool_name)
        if widget_type is None:
            continue
        try:
            from core.container import services
            dash = services.get("dashboard")
            if dash is None:
                return
            if widget_type == "sleep":
                payload = sleep_widget_payload(dash)
                UI_BUS.show_widget("sleep", payload)
            return  # Phase 2: genau ein Slot — erstes Match gewinnt
        except Exception as e:
            log.debug(f"maybe_update_ui fehlgeschlagen für '{tool_name}': {e}")
            return
    # Kein Tool in diesem Turn einem Widget zugeordnet → zurück zum Ruhezustand
    try:
        UI_BUS.clear()
    except Exception as e:
        log.debug(f"maybe_update_ui: clear() fehlgeschlagen: {e}")
