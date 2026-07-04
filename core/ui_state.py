"""
UI-State — Grundlage des generativen UI.

Phase 2: Tool-Aufrufe werden deterministisch Widget-Typen zugeordnet (kein
Extra-LLM-Call), ein einzelner Slot hielt den aktiven Widget-Zustand.
Phase 3: Mehrere gleichzeitig sichtbare Widgets über ein begrenztes Set an
Layout-Vorlagen (LAYOUT_PRESETS) — Alfred wählt selbst, wann mehrere Dinge
gleichzeitig sichtbar sein sollen (explizite Tools in core/skills/ui.py),
während einfache Anfragen weiterhin automatisch (maybe_update_ui) ins
"main"-Slot der Standard-Vorlage gehen.
"""
import asyncio
import logging
import time
from typing import Any

log = logging.getLogger(__name__)

# Tool-Name → Widget-Typ. Erweitert sich mit der Widget-Bibliothek (Phase 4).
WIDGET_MAP: dict[str, str] = {
    "get_health": "sleep",
}

# Begrenztes Set an Layout-Vorlagen — jede definiert ihre verfügbaren Slots.
LAYOUT_PRESETS: dict[str, list[str]] = {
    "single": ["main"],
    "split2": ["main", "side"],
}

DEFAULT_LAYOUT = "single"

# Explizite UI-Tools (core/skills/ui.py) setzen den Bus bereits selbst korrekt —
# maybe_update_ui darf deren Ergebnis in diesem Turn nicht mit clear() überschreiben.
EXPLICIT_UI_TOOLS = {"show_widget", "arrange_screen", "close_widget"}


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
    """Hält den aktuell aktiven Layout-Zustand (Vorlage + belegte Slots) und
    pusht Änderungen an SSE-Subscriber. `current` ist NIE None — der
    Ruhezustand wird durch `layout: None, slots: {}` repräsentiert, damit
    Bus und Frontend eine einzige, immer gültige Struktur teilen."""

    def __init__(self) -> None:
        self._layout: str | None = None
        self._slots: dict[str, dict] = {}
        self._ts: float = 0.0
        self._listeners: list[asyncio.Queue] = []

    @property
    def current(self) -> dict:
        return {"layout": self._layout, "slots": dict(self._slots), "ts": self._ts}

    def show_widget(self, widget_type: str, payload: dict, slot: str = "main") -> None:
        """Zeigt ein Widget in einem Slot. Wenn noch keine Vorlage aktiv ist,
        wird die Standard-Vorlage (DEFAULT_LAYOUT) automatisch gesetzt."""
        if self._layout is None:
            self._layout = DEFAULT_LAYOUT
        self._slots[slot] = {"widget": widget_type, "payload": payload}
        self._broadcast()

    def close_widget(self, slot: str) -> None:
        """Entfernt ein Widget aus einem Slot. Sind danach keine Slots mehr
        belegt, kehrt der Bus vollständig in den Ruhezustand zurück."""
        self._slots.pop(slot, None)
        if not self._slots:
            self._layout = None
        self._broadcast()

    def arrange_screen(self, layout: str) -> None:
        """Wechselt die Layout-Vorlage. Slots, die in der neuen Vorlage nicht
        existieren, werden verworfen; passende Slot-Belegungen bleiben erhalten."""
        if layout not in LAYOUT_PRESETS:
            raise ValueError(f"Unbekannte Layout-Vorlage: '{layout}'")
        allowed = set(LAYOUT_PRESETS[layout])
        self._layout = layout
        self._slots = {k: v for k, v in self._slots.items() if k in allowed}
        self._broadcast()

    def clear(self) -> None:
        """Zurück in den vollständigen Ruhezustand (kein Layout, keine Slots)."""
        self._layout = None
        self._slots = {}
        self._broadcast()

    def _broadcast(self) -> None:
        self._ts = time.time()
        evt = self.current
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
    Widget zugeordnet ist, baut bei Treffer die Daten und zeigt sie im
    'main'-Slot. Wenn der Turn stattdessen ein explizites UI-Tool genutzt hat
    (show_widget/arrange_screen/close_widget), hat der Bus bereits den
    korrekten Zustand — die automatische Zuordnung darf ihn dann NICHT
    überschreiben/zurücksetzen. Fehler werden geschluckt — UI-Updates dürfen
    nie einen Chat-Turn brechen."""
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
                UI_BUS.show_widget("sleep", payload, slot="main")
            return  # erstes Match gewinnt
        except Exception as e:
            log.debug(f"maybe_update_ui fehlgeschlagen für '{tool_name}': {e}")
            return
    # Ein explizites UI-Tool hat den Bus bereits selbst korrekt gesetzt — nicht überschreiben.
    if any(t in EXPLICIT_UI_TOOLS for t in tools_used):
        return
    # Kein Tool in diesem Turn einem Widget zugeordnet → zurück zum Ruhezustand
    try:
        UI_BUS.clear()
    except Exception as e:
        log.debug(f"maybe_update_ui: clear() fehlgeschlagen: {e}")
