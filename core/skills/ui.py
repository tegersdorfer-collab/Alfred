"""
UI-Tools — explizite Steuerung des generativen Desktop-UI (Phase 3).
Registriert sich via @T.register beim Import (durch core/skills/__init__.py).

Ergänzt die deterministische Basis-Zuordnung aus core/ui_state.py::maybe_update_ui
um Fälle, die echtes Urteilsvermögen brauchen: mehrere Widgets gleichzeitig
anordnen, eins schließen, zwischen Layout-Vorlagen wechseln.
"""
import logging

from core import tools as T
from core.ui_state import UI_BUS, LAYOUT_PRESETS, DEFAULT_LAYOUT, WIDGET_TYPES, build_widget_payload

log = logging.getLogger("core.skills")


@T.register("show_widget",
    "Zeigt ein Daten-Widget auf dem Desktop-Bildschirm an (verfügbar: sleep, training, tasks, "
    "calendar, nutrition, habits). Nutze dies wenn du proaktiv etwas Visuelles zeigen willst, "
    "zusätzlich zu oder statt einer Textantwort — z.B. wenn Timo mehrere Dinge gleichzeitig "
    "sehen will.",
    {
        "widget_type": {"type": "string", "description": "Widget-Typ, z.B. 'sleep', 'training', 'tasks', 'calendar', 'nutrition', 'habits'"},
        "slot": {"type": "string", "description": "Ziel-Slot im aktuellen Layout, Standard 'main'"},
    },
    ["widget_type"], "ui")
async def _show_widget(widget_type: str, slot: str = "main"):
    if widget_type not in WIDGET_TYPES:
        return f"FEHLER: Unbekannter Widget-Typ '{widget_type}'. Verfügbar: {', '.join(sorted(WIDGET_TYPES))}."

    active_layout = UI_BUS.current["layout"] or DEFAULT_LAYOUT
    if slot not in LAYOUT_PRESETS[active_layout]:
        return (f"FEHLER: Slot '{slot}' existiert nicht in Layout '{active_layout}'. "
                f"Verfügbare Slots: {', '.join(LAYOUT_PRESETS[active_layout])}.")

    payload = await build_widget_payload(widget_type)
    if payload is None:
        return f"FEHLER: Konnte Daten für Widget '{widget_type}' nicht laden (Datenquelle nicht verfügbar)."
    UI_BUS.show_widget(widget_type, payload, slot=slot)
    return f"Widget '{widget_type}' wird jetzt im Slot '{slot}' angezeigt."


@T.register("arrange_screen",
    "Legt fest, welche Bildschirm-Anordnung (Layout-Vorlage) gerade genutzt wird — nutze dies "
    "wenn mehrere Dinge gleichzeitig sichtbar sein sollen, statt nacheinander.",
    {"layout": {"type": "string", "description": f"Eine von: {', '.join(LAYOUT_PRESETS)}"}},
    ["layout"], "ui")
async def _arrange_screen(layout: str):
    try:
        UI_BUS.arrange_screen(layout)
    except ValueError as e:
        return f"FEHLER: {e}"
    return f"Layout auf '{layout}' gesetzt."


@T.register("close_widget",
    "Schließt ein angezeigtes Widget wieder (z.B. wenn Timo fertig damit ist).",
    {"slot": {"type": "string", "description": "Slot der geschlossen werden soll, Standard 'main'"}},
    [], "ui")
async def _close_widget(slot: str = "main"):
    UI_BUS.close_widget(slot)
    return f"Widget im Slot '{slot}' geschlossen."
