"""
Tool-Registry für den agentischen Kern.
Jedes Tool ist eine async-Funktion mit JSON-Schema. Das LLM ruft sie selbst auf.
"""
import asyncio
import inspect
import json
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable

log = logging.getLogger(__name__)


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict                      # JSON-Schema (properties)
    handler: Callable[..., Awaitable[str]]
    required: list[str] = field(default_factory=list)
    category: str = "general"


REGISTRY: dict[str, Tool] = {}


def register(
    name: str,
    description: str,
    parameters: dict | None = None,
    required: list[str] | None = None,
    category: str = "general",
):
    """Decorator zum Registrieren eines Tools."""
    def deco(fn: Callable[..., Awaitable[str]]):
        REGISTRY[name] = Tool(
            name=name,
            description=description,
            parameters=parameters or {},
            handler=fn,
            required=required or [],
            category=category,
        )
        return fn
    return deco


def ollama_schemas(only: list[str] | None = None) -> list[dict]:
    """Exportiert Tool-Schemas im Ollama/OpenAI Function-Calling-Format."""
    tools = []
    for t in REGISTRY.values():
        if only is not None and t.name not in only:
            continue
        tools.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": {
                    "type": "object",
                    "properties": t.parameters,
                    "required": t.required,
                },
            },
        })
    return tools


async def execute(name: str, args: dict) -> str:
    """Führt ein Tool aus und gibt die Beobachtung (String) zurück."""
    tool = REGISTRY.get(name)
    if not tool:
        return f"FEHLER: Tool '{name}' existiert nicht."
    try:
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {}
        result = tool.handler(**args)
        if inspect.isawaitable(result):
            result = await result
        return str(result)
    except TypeError as e:
        return f"FEHLER: ungültige Argumente für {name}: {e}"
    except Exception as e:
        log.warning(f"Tool {name} fehlgeschlagen: {e}")
        return f"FEHLER beim Ausführen von {name}: {e}"


def tool_names() -> list[str]:
    return list(REGISTRY.keys())


def catalog() -> str:
    """Menschenlesbarer Katalog aller Tools (fürs Dashboard / Debug)."""
    lines = []
    for t in sorted(REGISTRY.values(), key=lambda x: (x.category, x.name)):
        lines.append(f"[{t.category}] {t.name} – {t.description}")
    return "\n".join(lines)


# ── Schnelle Tool-Auswahl (spart Prefill: Tool-Schemas sind teuer) ────────────

import re as _re

# Aktions-/Bedarfssignale → relevante Kategorien
_CATEGORY_KEYWORDS = {
    "productivity": ["aufgabe", "task", "todo", "to-do", "erinner", "reminder",
                     "termin", "kalender", "meeting", "deadline", "fällig",
                     "lösch", "verschieb", "verlege", "ändere den termin", "streich"],
    "habits":       ["gewohnheit", "habit", "abhaken", "abgehakt", "hake", "hak ", "abhak",
                     "streak", "routine", "geschafft", "erledigt für heute"],
    "fitness":      ["training", "workout", "trainiert", "gelaufen", "lauf", "gym",
                     "sport", "übung", "sätze", "kraft", "joggen", "km"],
    "nutrition":    ["gegessen", "gegessen", "getrunken", "mahlzeit", "essen", "esse", "aß",
                     "kalorien", "protein", "snack", "frühstück", "mittag", "abendessen",
                     "ernährung", "kcal", "toast", "brötchen", "kaffee", "hatte zum",
                     "zum frühstück", "zum mittag", "zum abend", "carbs", "kohlenhydrate"],
    "journal":      ["tagebuch", "journal", "stimmung", "mood", "gefühlt", "fühle", "notier"],
    "goals":        ["ziel", "goal", "fortschritt", "vorhaben", "meilenstein"],
    "knowledge":    ["wetter", "news", "nachricht", "suche", "google", "aktuell",
                     "wer ist", "was ist", "preis", "kostet", "wie viel"],
    "memory":       ["merk dir", "merke", "behalte", "vergiss nicht", "erinnere dich"],
    "health":       ["schlaf", "schritte", "hrv", "puls", "gewicht", "gesundheit"],
}

# Generelle Aktionsverben → es soll etwas GETAN werden
_ACTION_WORDS = ["erstell", "leg ", "lege ", "anlegen", "hak", "trag", "trage", "setz",
                 "lösch", "aktualisier", "update", "plan", "notier", "füg", "add",
                 "starte", "beende", "merk", "erinner", "mach mir", "trag ein"]


def is_action(text: str) -> bool:
    """Gibt True zurück wenn die Nachricht ein Aktionswort enthält (Tool-Call erzwingen)."""
    t = text.lower()
    return any(w in t for w in _ACTION_WORDS)


def select_tools(text: str) -> list[str]:
    """
    Wählt relevante Tools basierend auf der Nachricht.
    Leere Liste = reines Gespräch (schneller Pfad ohne Tool-Prefill).
    """
    t = text.lower()
    cats = set()
    for cat, kws in _CATEGORY_KEYWORDS.items():
        if any(k in t for k in kws):
            cats.add(cat)

    has_action = any(w in t for w in _ACTION_WORDS)
    is_question = "?" in text

    # Reines Gespräch ohne Bezug → fast path, aber create_skill/calculate bleiben
    # verfügbar – sonst hat der Agent ausgerechnet bei unerwarteten/neuen Anfragen
    # (die selten in eine Keyword-Kategorie fallen) gar keine Tools zur Wahl.
    if not cats and not has_action:
        return [n for n in ("create_skill", "list_dynamic_skills", "delete_skill", "calculate")
                if n in REGISTRY]

    names = [name for name, tool in REGISTRY.items() if tool.category in cats]

    # Aktionswort ohne klare Kategorie → Produktivitäts-Tools als Default
    if has_action and not names:
        names = [n for n, tl in REGISTRY.items() if tl.category == "productivity"]

    # Bei Fragen nach externem Wissen Web-Suche/Wetter sicher dabei
    if is_question and "knowledge" in cats:
        for n in ("web_search", "get_weather"):
            if n not in names:
                names.append(n)

    names = names[:12]   # Prefill begrenzen

    # create_skill MUSS immer verfügbar sein, sobald überhaupt Tools im Spiel sind –
    # sonst fehlt es genau dann, wenn kein passendes Tool zur Kategorie passt.
    for n in ("create_skill", "list_dynamic_skills", "delete_skill"):
        if n in REGISTRY and n not in names:
            names.append(n)

    return names
