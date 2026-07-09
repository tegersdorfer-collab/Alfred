"""
Habits-Tools — aus core/skills.py extrahiert (verhaltensgleich).
Registriert sich via @T.register beim Import (durch core/skills/__init__.py).
"""
import logging

from core import tools as T
from domains import habits

log = logging.getLogger("core.skills")


@T.register("log_habit", "Hakt eine Gewohnheit für heute ab (sucht per Name).",
    {"name": {"type": "string"}}, ["name"], "habits")
async def _log_habit(name: str):
    h = habits.find_habit(name)
    if not h:
        return f"Gewohnheit '{name}' nicht gefunden."
    habits.log_habit(h["id"])
    return f"{h['emoji']} '{h['name']}' für heute abgehakt (Streak: {habits.streak(h['id'])} Tage)."

@T.register("create_habit", "Legt eine neue Gewohnheit an.",
    {"name": {"type": "string"},
     "emoji": {"type": "string"},
     "category": {"type": "string", "description": "morning | day | evening (Standard: day)"}},
    ["name"], "habits")
async def _create_habit(name: str, emoji: str = "✅", category: str = "day"):
    # Kategorie normalisieren: deutsche Begriffe → englische Keys
    cat_map = {
        "morgen": "morning", "morgens": "morning", "morgenroutine": "morning", "morning routine": "morning",
        "abend": "evening", "abends": "evening", "abendroutine": "evening", "evening routine": "evening",
        "tag": "day", "tagsüber": "day", "mittag": "day",
    }
    category = cat_map.get(category.lower().strip(), category.lower().strip())
    if category not in ("morning", "day", "evening"):
        category = "day"
    from core import db as _db
    _db.insert_returning(
        "INSERT INTO habits (name, emoji, category) VALUES (%s, %s, %s) RETURNING id",
        (name, emoji, category)
    )
    cat_label = {"morning": "Morgenroutine", "day": "Tagsüber", "evening": "Abendroutine"}[category]
    return f"Gewohnheit angelegt: {emoji} {name} ({cat_label})"

@T.register("list_habits", "Listet alle Gewohnheiten mit Streak und Status heute.", {}, [], "habits")
async def _list_habits():
    ov = habits.habit_overview()
    if not ov:
        return "Keine Gewohnheiten angelegt."
    return "\n".join(
        f"{h['emoji']} {h['name']}: {'✓ heute' if h['today_done'] else '○ offen'}, Streak {h['streak']}"
        for h in ov
    )
