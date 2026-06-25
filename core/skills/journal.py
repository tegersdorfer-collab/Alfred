"""
Journal-Tools — aus core/skills.py extrahiert (verhaltensgleich).
Registriert sich via @T.register beim Import (durch core/skills/__init__.py).
"""
import logging
from datetime import date, datetime

from core import tools as T
from core.timeparse import parse_datetime, parse_date
from core.skill_context import CTX
from domains import habits, fitness, nutrition, journal, goals, weather, tasks as tasks_d

log = logging.getLogger("core.skills")


@T.register("add_journal", "Fügt einen Tagebucheintrag hinzu (mit optionaler Stimmung 1-5).",
    {"content": {"type": "string"},
     "mood": {"type": "integer", "description": "Stimmung 1-5"},
     "energy": {"type": "integer", "description": "Energie 1-5"}},
    ["content"], "journal")
async def _add_journal(content: str, mood: int = None, energy: int = None):
    journal.add_entry(content=content, mood=mood, energy=energy)
    return "Tagebucheintrag gespeichert."
