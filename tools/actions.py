"""
Action-Parser – erkennt Alfred-Befehle in Antworten und führt sie aus.
Format: [[ACTION:create_task|title=...|priority=...]]
        [[ACTION:complete_task|query=...]]
"""
import logging
import re
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

ACTION_RE = re.compile(r'\[\[ACTION:(\w+)\|(.*?)\]\]', re.DOTALL)


@dataclass
class ParsedAction:
    action: str
    params: dict[str, str]


def parse_actions(text: str) -> tuple[str, list[ParsedAction]]:
    """
    Extrahiert Aktionen aus dem Text.
    Gibt (bereinigter_text, aktionen) zurück.
    """
    actions = []
    def replacer(m):
        action = m.group(1)
        param_str = m.group(2)
        params = {}
        for part in param_str.split('|'):
            if '=' in part:
                k, v = part.split('=', 1)
                params[k.strip()] = v.strip()
        actions.append(ParsedAction(action=action, params=params))
        return ''  # Aus Text entfernen

    clean_text = ACTION_RE.sub(replacer, text).strip()
    return clean_text, actions


def build_action_instructions(tasks: list) -> str:
    """Erklärt Alfred wie er Task- und Reminder-Aktionen auslöst."""
    task_list = ""
    if tasks:
        task_list = "\nBekannte offene Tasks (für complete_task):\n"
        for t in tasks[:8]:
            task_list += f"  - ID: {t.id} | {t.title}\n"

    return f"""
## Aktionen
Du kannst Tasks und Reminders direkt setzen. Füge am Ende deiner Antwort einen Befehl ein:

Task erstellen:
[[ACTION:create_task|title=Titel hier|priority=high]]
(priority: high / medium / low)

Task abhaken:
[[ACTION:complete_task|query=Teil des Titels]]

Reminder setzen (Format: DD.MM.YYYY HH:MM oder HH:MM für heute):
[[ACTION:set_reminder|text=Erinnerungstext|at=15:30]]
[[ACTION:set_reminder|text=Erinnerungstext|at=08.06.2026 09:00]]
{task_list}
Nutze Befehle NUR wenn Timo explizit darum bittet. Kein Befehl = kein Problem.
"""
