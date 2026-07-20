"""Skilltree-Tools — Voice-Zugriff auf Level & nächste Quest."""
import logging
from datetime import date, timedelta

from core import tools as T
from core.skill_context import CTX

log = logging.getLogger("core.skills")


@T.register("get_skilltree",
    "Timos Skilltree-Status: Level je Lebens-Achse + nächste Quest. Für 'wie ist "
    "mein level / was soll ich als nächstes tun / skilltree'.", {}, [], "skilltree")
async def _get_skilltree():
    if not CTX.dashboard:
        return "Skilltree nicht verfügbar."
    from domains.skilltree.service import build_skilltree_state
    today = date.today()
    since = (today - timedelta(days=today.weekday())).isoformat()
    st = build_skilltree_state(CTX.dashboard, today, quest_since=since)
    levels = ", ".join(f"{a['label']} Lv{a['level']}" for a in st["axes"])
    quest = st["quests"][0]["label"] if st["quests"] else "keine offene Quest"
    return f"{levels}. Nächste Quest: {quest}."
