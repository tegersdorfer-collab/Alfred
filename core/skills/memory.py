"""
Memory-Tools — aus core/skills.py extrahiert (verhaltensgleich).
Registriert sich via @T.register beim Import (durch core/skills/__init__.py).
"""
import logging
from datetime import date, datetime

from core import tools as T
from core.timeparse import parse_datetime, parse_date
from core.skill_context import CTX
from domains import habits, fitness, nutrition, journal, goals, weather, tasks as tasks_d

log = logging.getLogger("core.skills")


@T.register("remember",
    "Speichert eine wichtige Information dauerhaft über Timo im Langzeitgedächtnis.",
    {"content": {"type": "string", "description": "Die zu merkende Information"},
     "category": {"type": "string", "description": "fact | goal | pattern | preference | context"}},
    ["content"], "memory")
async def _remember(content: str, category: str = "fact"):
    if not (CTX.lzg and CTX.llm):
        return "Gedächtnis nicht verfügbar."
    emb = await CTX.llm.embed(content)
    similar = CTX.lzg.find_similar(emb, threshold=0.30)
    if similar:
        CTX.lzg.update_confidence(similar[0][0].id, 0.95)
        return f"Bereits bekannt, bestätigt: {content}"
    CTX.lzg.save(content=content, embedding=emb, category=category, confidence=0.9)
    return f"Gemerkt: {content}"

@T.register("recall",
    "Durchsucht das Langzeitgedächtnis nach Informationen über Timo.",
    {"query": {"type": "string", "description": "Wonach gesucht wird"}},
    ["query"], "memory")
async def _recall(query: str):
    if not (CTX.lzg and CTX.llm):
        return "Gedächtnis nicht verfügbar."
    emb = await CTX.llm.embed(query)
    mems = CTX.lzg.search(emb, top_k=5)
    return CTX.lzg.format_for_context(mems)

@T.register("add_directive",
    "Speichert eine stehende Anweisung von Timo die Alfred ab sofort IMMER beachten soll. "
    "Beispiel: 'Antworte immer auf Englisch wenn ich Englisch schreibe', "
    "'Erinnere mich immer an X wenn ich Y erwähne', 'Nutze nie Gedankenstriche'. "
    "Diese Anweisung wird bei jeder Antwort automatisch injiziert.",
    {
        "name":        {"type": "string", "description": "Kurzer Name der Anweisung"},
        "description": {"type": "string", "description": "Was Alfred immer tun/lassen soll"},
    },
    ["name", "description"], "memory")
async def _add_directive(name: str, description: str):
    from memory.knowledge import KnowledgeGraph
    kg = KnowledgeGraph()
    kg.add_directive(name, description)
    return f"Stehende Anweisung gespeichert: '{name}' — gilt ab sofort bei jeder Antwort."
