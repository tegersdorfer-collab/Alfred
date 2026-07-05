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

# Tool-Name → Widget-Typ.
WIDGET_MAP: dict[str, str] = {
    "get_health": "sleep",
    "recent_workouts": "training",
    "list_tasks": "tasks",
    "get_calendar": "calendar",
    "nutrition_today": "nutrition",
    "list_habits": "habits",
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


def training_widget_payload(limit: int = 8) -> dict:
    """Baut Trainings-Daten für das Training-Widget aus domains.fitness."""
    from domains import fitness
    workouts = fitness.recent_workouts(limit=limit)
    return {
        "workouts": [
            {
                "date": w["date"].isoformat(),
                "title": w["title"],
                "duration_min": w.get("duration_min"),
                "distance_km": w.get("distance_km"),
            }
            for w in workouts
        ],
    }


def tasks_widget_payload(limit: int = 8) -> dict:
    """Baut die offenen Aufgaben für das Tasks-Widget aus domains.tasks."""
    from domains import tasks as tasks_d
    rows = tasks_d.list_tasks("open")[:limit]
    return {
        "tasks": [
            {
                "title": t["title"],
                "priority": t.get("priority"),
                "progress_pct": t.get("progress_pct") or 0,
            }
            for t in rows
        ],
    }


def calendar_widget_payload(dashboard: Any, days: int = 7) -> dict:
    """Baut anstehende Termine für das Calendar-Widget aus DashboardReader."""
    events = dashboard.get_upcoming_events(days=days)
    return {
        "events": [
            {
                "title": e.title,
                "start": e.start.isoformat(),
                "all_day": e.all_day,
                "location": e.location,
            }
            for e in events
        ],
    }


def nutrition_widget_payload() -> dict:
    """Baut die heutigen Makro-Summen für das Nutrition-Widget aus domains.nutrition."""
    from domains import nutrition
    t = nutrition.day_totals()
    return {
        "kcal": t.get("kcal", 0),
        "protein": t.get("protein", 0),
        "carbs": t.get("carbs", 0),
        "fat": t.get("fat", 0),
    }


def habits_widget_payload() -> dict:
    """Baut die Gewohnheiten-Übersicht für das Habits-Widget aus domains.habits."""
    from domains import habits
    overview = habits.habit_overview()
    return {
        "habits": [
            {
                "emoji": h["emoji"],
                "name": h["name"],
                "today_done": h["today_done"],
                "streak": h["streak"],
            }
            for h in overview
        ],
    }


def _ollama_reachable() -> bool:
    """Schneller Erreichbarkeits-Check für Ollama (kurzer Timeout, kein Crash bei Ausfall)."""
    try:
        import httpx
        import config
        resp = httpx.get(f"{config.OLLAMA_BASE_URL}/api/tags", timeout=1.5)
        return resp.status_code == 200
    except Exception:
        return False


def system_widget_payload() -> dict:
    """Baut System-Status (CPU/RAM/Ollama) fürs System-Widget — 'Jarvis sieht
    den eigenen Gesundheitszustand', kein Domain-Modul nötig."""
    import psutil
    return {
        "cpu_pct": psutil.cpu_percent(),
        "ram_pct": psutil.virtual_memory().percent,
        "ollama_ok": _ollama_reachable(),
    }


def brain_widget_payload(limit: int = 8) -> dict:
    """Baut die zuletzt bearbeiteten Second-Brain-Notizen fürs Brain-Widget."""
    from domains import second_brain
    notes = second_brain.get_all(limit=limit * 4)  # unsortiert nach Aktualität, daher grob überziehen
    notes = sorted(notes, key=lambda n: n.updated_at, reverse=True)[:limit]
    return {
        "notes": [
            {
                "title": n.title,
                "category": n.category,
                "updated_at": n.updated_at.isoformat(),
            }
            for n in notes
        ],
    }


def skills_widget_payload() -> dict:
    """Baut den Skill-Factory-Status fürs Skills-Widget — welche Tools sich
    Alfred selbst zur Laufzeit gebaut hat, plus Gesamt-Tool-Anzahl."""
    from core import skill_factory, tools as T
    return {
        "dynamic_skills": skill_factory.list_dynamic_skills(),
        "total_tools": len(T.REGISTRY),
    }


# Widget-Typen, die eine Dashboard-Instanz brauchen (services.get("dashboard")).
_DASHBOARD_BUILDERS = {
    "sleep": sleep_widget_payload,
    "calendar": calendar_widget_payload,
}

# Widget-Typen, die keine externe Abhängigkeit brauchen (holen sich ihre Daten
# selbst aus den passenden domains-Modulen).
_STANDALONE_BUILDERS = {
    "training": training_widget_payload,
    "tasks": tasks_widget_payload,
    "nutrition": nutrition_widget_payload,
    "habits": habits_widget_payload,
    "system": system_widget_payload,
    "brain": brain_widget_payload,
    "skills": skills_widget_payload,
}

WIDGET_TYPES = set(_DASHBOARD_BUILDERS) | set(_STANDALONE_BUILDERS)


def build_widget_payload(widget_type: str) -> dict | None:
    """Einzige Stelle, die weiß wie man Daten für einen Widget-Typ baut. Gibt
    None zurück wenn der Typ unbekannt ist oder seine Datenquelle (aktuell
    nur 'dashboard') nicht verfügbar ist."""
    if widget_type in _DASHBOARD_BUILDERS:
        from core.container import services
        dash = services.get("dashboard")
        if dash is None:
            return None
        return _DASHBOARD_BUILDERS[widget_type](dash)
    builder = _STANDALONE_BUILDERS.get(widget_type)
    if builder is None:
        return None
    return builder()


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
            payload = build_widget_payload(widget_type)
            if payload is None:
                return
            UI_BUS.show_widget(widget_type, payload, slot="main")
            return  # erstes Match gewinnt
        except Exception as e:
            log.debug(f"maybe_update_ui fehlgeschlagen für '{tool_name}': {e}")
            return
    if any(t in EXPLICIT_UI_TOOLS for t in tools_used):
        return
    try:
        UI_BUS.clear()
    except Exception as e:
        log.debug(f"maybe_update_ui: clear() fehlgeschlagen: {e}")
