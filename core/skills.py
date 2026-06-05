"""
Skill-Registrierung: verbindet alle Domänen-Funktionen mit dem Agent-Tool-Registry.
Der Agent (Qwen3) ruft diese Tools selbstständig auf.

Vor Nutzung muss bind(ctx) aufgerufen werden (im Orchestrator-Start).
"""
import logging
from dataclasses import dataclass
from datetime import date, datetime

from core import tools as T
from core.timeparse import parse_datetime, parse_date
from domains import habits, fitness, nutrition, journal, goals, weather, tasks as tasks_d

log = logging.getLogger(__name__)


@dataclass
class SkillContext:
    lzg: object = None          # LZG-Instanz (Memory)
    llm: object = None          # OllamaProvider (für embed)
    search: object = None       # WebSearch
    reminders: object = None    # ReminderStore
    dashboard: object = None    # DashboardReader


CTX = SkillContext()


def bind(ctx: SkillContext) -> None:
    global CTX
    CTX = ctx
    log.info(f"Skills gebunden – {len(T.REGISTRY)} Tools verfügbar")


# ════════════════════════════════════════════════════════════════════════════
#  WISSEN & WEB
# ════════════════════════════════════════════════════════════════════════════

@T.register("web_search",
    "Sucht aktuelle Informationen im Web (News, Fakten, Preise, Wetter-Hintergründe). "
    "Nutze dies wenn du aktuelle/externe Infos brauchst die du nicht weißt.",
    {"query": {"type": "string", "description": "Suchanfrage"},
     "news": {"type": "boolean", "description": "True für aktuelle Schlagzeilen"}},
    ["query"], "knowledge")
async def _web_search(query: str, news: bool = False):
    if not CTX.search:
        return "Suche nicht verfügbar."
    results = await CTX.search.search(query, max_results=4, news=news)
    return CTX.search.format_results(results) if results else "Keine Ergebnisse."


@T.register("get_weather",
    "Aktuelles Wetter und 3-Tage-Vorhersage.",
    {"city": {"type": "string", "description": "Stadt (optional, Default aus Settings)"}},
    [], "knowledge")
async def _get_weather(city: str = None):
    w = await weather.get_weather(city)
    if w.get("error"):
        return w["error"]
    now = w["now"]
    out = [f"Wetter in {w['city']}: {now['temp']}°C ({now['desc']}), gefühlt {now['feels']}°C, Wind {now['wind']} km/h."]
    for d in w["forecast"]:
        out.append(f"  {d['date']}: {d['min']}–{d['max']}°C, {d['code']}, Regen {d['rain_prob']}%")
    return "\n".join(out)


# ════════════════════════════════════════════════════════════════════════════
#  GEDÄCHTNIS
# ════════════════════════════════════════════════════════════════════════════

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


# ════════════════════════════════════════════════════════════════════════════
#  TASKS & REMINDER & KALENDER
# ════════════════════════════════════════════════════════════════════════════

@T.register("create_task",
    "Erstellt eine Aufgabe. kind='project' für größere Vorhaben (mit Unteraufgaben), "
    "kind='checklist' für Listen, sonst 'task'.",
    {"title": {"type": "string"},
     "priority": {"type": "string", "description": "high | medium | low"},
     "kind": {"type": "string", "description": "task | project | checklist"},
     "due": {"type": "string", "description": "Fälligkeit, z.B. 'morgen 9:00' oder '15.06.2026'"}},
    ["title"], "productivity")
async def _create_task(title: str, priority: str = "medium", kind: str = "task", due: str = None):
    due_dt = parse_datetime(due) if due else None
    tasks_d.create_task(title=title, priority=priority, kind=kind, due=due_dt)
    return f"Aufgabe erstellt: {title} ({kind}, {priority})"


@T.register("add_subtask",
    "Fügt einer bestehenden Aufgabe/einem Projekt eine Unteraufgabe hinzu (sucht Eltern per Titel).",
    {"parent_query": {"type": "string", "description": "Teil des Titels der Hauptaufgabe"},
     "title": {"type": "string"}},
    ["parent_query", "title"], "productivity")
async def _add_subtask(parent_query: str, title: str):
    parent = tasks_d.find_task(parent_query)
    if not parent:
        return f"Hauptaufgabe '{parent_query}' nicht gefunden."
    tasks_d.create_task(title=title, parent_id=parent["id"])
    return f"Unteraufgabe '{title}' zu '{parent['title']}' hinzugefügt."


@T.register("complete_task", "Markiert eine Aufgabe als erledigt (sucht per Titel).",
    {"query": {"type": "string"}}, ["query"], "productivity")
async def _complete_task(query: str):
    task = tasks_d.find_task(query)
    if not task:
        return f"Keine offene Aufgabe gefunden für '{query}'."
    tasks_d.complete_task(task["id"])
    return f"Erledigt: {task['title']}"


@T.register("set_task_progress", "Setzt den Fortschritt einer Aufgabe in Prozent (sucht per Titel).",
    {"query": {"type": "string"}, "progress_pct": {"type": "integer", "description": "0-100"}},
    ["query", "progress_pct"], "productivity")
async def _set_task_progress(query: str, progress_pct: int):
    task = tasks_d.find_task(query)
    if not task:
        return f"Aufgabe '{query}' nicht gefunden."
    tasks_d.set_progress(task["id"], progress_pct)
    return f"'{task['title']}' auf {progress_pct}% gesetzt."


@T.register("list_tasks", "Listet Timos offene Aufgaben (mit Unteraufgaben & Fortschritt).",
    {}, [], "productivity")
async def _list_tasks():
    return tasks_d.context_summary(15) or "Keine offenen Aufgaben."


@T.register("set_reminder",
    "Setzt eine zeitgesteuerte Erinnerung.",
    {"text": {"type": "string"},
     "at": {"type": "string", "description": "Zeitpunkt, z.B. '15:30', 'morgen 8:00', 'in 2 stunden'"}},
    ["text", "at"], "productivity")
async def _set_reminder(text: str, at: str):
    if not CTX.reminders:
        return "Reminder nicht verfügbar."
    dt = parse_datetime(at)
    if not dt:
        return f"Konnte Zeit '{at}' nicht verstehen."
    CTX.reminders.add(text, dt)
    return f"Erinnerung gesetzt: '{text}' am {dt.strftime('%d.%m. %H:%M')}"


@T.register("create_calendar_event",
    "Erstellt einen Kalendereintrag.",
    {"title": {"type": "string"},
     "start": {"type": "string", "description": "Startzeit, z.B. 'morgen 14:00'"},
     "end": {"type": "string", "description": "Endzeit (optional)"},
     "location": {"type": "string"}},
    ["title", "start"], "productivity")
async def _create_event(title: str, start: str, end: str = None, location: str = None):
    if not CTX.dashboard:
        return "Kalender nicht verfügbar."
    s = parse_datetime(start)
    if not s:
        return f"Konnte Startzeit '{start}' nicht verstehen."
    e = parse_datetime(end) if end else None
    CTX.dashboard.create_event(title=title, start=s, end=e, location=location)
    return f"Termin erstellt: {title} am {s.strftime('%d.%m. %H:%M')}"


@T.register("get_calendar", "Zeigt anstehende Termine.",
    {"days": {"type": "integer", "description": "Anzahl Tage voraus"}}, [], "productivity")
async def _get_calendar(days: int = 7):
    if not CTX.dashboard:
        return "Kalender nicht verfügbar."
    events = CTX.dashboard.get_upcoming_events(days=days)
    return "\n".join(e.format() for e in events) if events else "Keine Termine."


# ════════════════════════════════════════════════════════════════════════════
#  HEALTH
# ════════════════════════════════════════════════════════════════════════════

@T.register("get_health", "Timos Gesundheitsdaten der letzten Tage (Schlaf, Schritte, HRV, Gewicht).",
    {"days": {"type": "integer"}}, [], "health")
async def _get_health(days: int = 3):
    if not CTX.dashboard:
        return "Health nicht verfügbar."
    health = CTX.dashboard.get_recent_health(days=days)
    return "\n".join(h.format() for h in health) if health else "Keine Gesundheitsdaten."


# ════════════════════════════════════════════════════════════════════════════
#  HABITS
# ════════════════════════════════════════════════════════════════════════════

@T.register("log_habit", "Hakt eine Gewohnheit für heute ab (sucht per Name).",
    {"name": {"type": "string"}}, ["name"], "habits")
async def _log_habit(name: str):
    h = habits.find_habit(name)
    if not h:
        return f"Gewohnheit '{name}' nicht gefunden."
    habits.log_habit(h["id"])
    return f"{h['emoji']} '{h['name']}' für heute abgehakt (Streak: {habits.streak(h['id'])} Tage)."


@T.register("create_habit", "Legt eine neue Gewohnheit an.",
    {"name": {"type": "string"}, "emoji": {"type": "string"}}, ["name"], "habits")
async def _create_habit(name: str, emoji: str = "✅"):
    habits.create_habit(name=name, emoji=emoji)
    return f"Gewohnheit angelegt: {emoji} {name}"


@T.register("list_habits", "Listet alle Gewohnheiten mit Streak und Status heute.", {}, [], "habits")
async def _list_habits():
    ov = habits.habit_overview()
    if not ov:
        return "Keine Gewohnheiten angelegt."
    return "\n".join(
        f"{h['emoji']} {h['name']}: {'✓ heute' if h['today_done'] else '○ offen'}, Streak {h['streak']}"
        for h in ov
    )


# ════════════════════════════════════════════════════════════════════════════
#  FITNESS
# ════════════════════════════════════════════════════════════════════════════

@T.register("log_workout", "Protokolliert ein absolviertes Training.",
    {"title": {"type": "string"},
     "type": {"type": "string", "description": "strength | run | mobility | other"},
     "duration_min": {"type": "integer"},
     "distance_km": {"type": "number"},
     "notes": {"type": "string"}},
    ["title"], "fitness")
async def _log_workout(title: str, type: str = "strength", duration_min: int = None,
                       distance_km: float = None, notes: str = None):
    fitness.log_workout(title=title, type_=type, duration_min=duration_min,
                        distance_km=distance_km, notes=notes)
    extra = f", {distance_km}km" if distance_km else ""
    return f"Training protokolliert: {title} ({type}{extra})."


@T.register("log_workout_detailed",
    "Protokolliert ein Krafttraining MIT einzelnen Übungen und Sätzen. "
    "Nutze dies wenn Timo Übungen/Sätze/Gewichte nennt oder einen Trainings-Dump liefert.",
    {"title": {"type": "string"},
     "exercises": {"type": "array", "description": "Liste von Übungen mit Sätzen",
        "items": {"type": "object", "properties": {
            "name": {"type": "string"},
            "sets": {"type": "array", "items": {"type": "object", "properties": {
                "reps": {"type": "integer"}, "weight_kg": {"type": "number"}}}}}}}},
    ["title", "exercises"], "fitness")
async def _log_workout_detailed(title: str, exercises: list):
    flat_sets = []
    for ex in exercises or []:
        name = ex.get("name")
        for i, s in enumerate(ex.get("sets", []), 1):
            flat_sets.append({"exercise": name, "set_index": i,
                              "reps": s.get("reps"), "weight_kg": s.get("weight_kg")})
    fitness.log_workout(title=title, type_="strength", sets=flat_sets)
    n_ex = len(exercises or [])
    return f"Training '{title}' mit {n_ex} Übungen und {len(flat_sets)} Sätzen protokolliert."


@T.register("recent_workouts", "Zeigt die letzten Trainings.", {}, [], "fitness")
async def _recent_workouts():
    ws = fitness.recent_workouts(limit=8)
    if not ws:
        return "Noch keine Trainings protokolliert."
    return "\n".join(
        f"{w['date']}: {w['title']} ({w['type']}"
        + (f", {w['distance_km']}km" if w['distance_km'] else "")
        + (f", {w['duration_min']}min" if w['duration_min'] else "") + ")"
        for w in ws
    )


# ════════════════════════════════════════════════════════════════════════════
#  ERNÄHRUNG
# ════════════════════════════════════════════════════════════════════════════

@T.register("log_meal",
    "Protokolliert eine Mahlzeit. SCHÄTZE die Makros (Kalorien, Protein, Kohlenhydrate, "
    "Fett) realistisch selbst, wenn Timo sie nicht nennt (z.B. 'zwei Marmeladentoasts' "
    "≈ 300 kcal, 8g Protein, 50g Carbs, 8g Fett). Gib immer geschätzte Werte mit.",
    {"description": {"type": "string"},
     "meal_type": {"type": "string", "description": "breakfast | lunch | dinner | snack"},
     "calories": {"type": "integer", "description": "geschätzte Kalorien"},
     "protein_g": {"type": "number", "description": "geschätztes Protein in g"},
     "carbs_g": {"type": "number", "description": "geschätzte Kohlenhydrate in g"},
     "fat_g": {"type": "number", "description": "geschätztes Fett in g"}},
    ["description"], "nutrition")
async def _log_meal(description: str, meal_type: str = "snack",
                    calories: int = None, protein_g: float = None,
                    carbs_g: float = None, fat_g: float = None):
    nutrition.log_meal(description=description, meal_type=meal_type,
                       calories=calories, protein_g=protein_g,
                       carbs_g=carbs_g, fat_g=fat_g)
    macro = []
    if calories: macro.append(f"{int(calories)} kcal")
    if protein_g: macro.append(f"{int(protein_g)}g P")
    if carbs_g: macro.append(f"{int(carbs_g)}g C")
    if fat_g: macro.append(f"{int(fat_g)}g F")
    return f"Mahlzeit erfasst: {description}" + (f" ({', '.join(macro)})" if macro else "")


@T.register("nutrition_today", "Zeigt heutige Mahlzeiten und Makro-Summen.", {}, [], "nutrition")
async def _nutrition_today():
    t = nutrition.day_totals()
    meals = nutrition.meals_for()
    head = f"Heute: {int(t['kcal'])} kcal, {int(t['protein'])}g Protein, {int(t['carbs'])}g Carbs, {int(t['fat'])}g Fett."
    body = "\n".join(f"  {m['meal_type']}: {m['description']}" for m in meals)
    return head + ("\n" + body if body else "")


# ════════════════════════════════════════════════════════════════════════════
#  JOURNAL
# ════════════════════════════════════════════════════════════════════════════

@T.register("add_journal", "Fügt einen Tagebucheintrag hinzu (mit optionaler Stimmung 1-5).",
    {"content": {"type": "string"},
     "mood": {"type": "integer", "description": "Stimmung 1-5"},
     "energy": {"type": "integer", "description": "Energie 1-5"}},
    ["content"], "journal")
async def _add_journal(content: str, mood: int = None, energy: int = None):
    journal.add_entry(content=content, mood=mood, energy=energy)
    return "Tagebucheintrag gespeichert."


# ════════════════════════════════════════════════════════════════════════════
#  ZIELE
# ════════════════════════════════════════════════════════════════════════════

@T.register("create_goal", "Legt ein neues Ziel an.",
    {"title": {"type": "string"},
     "category": {"type": "string", "description": "fitness | career | finance | personal"},
     "target_value": {"type": "number"}, "unit": {"type": "string"},
     "deadline": {"type": "string", "description": "Datum, optional"}},
    ["title"], "goals")
async def _create_goal(title: str, category: str = "general", target_value: float = None,
                       unit: str = None, deadline: str = None):
    dl = parse_date(deadline) if deadline else None
    goals.create_goal(title=title, category=category, target_value=target_value,
                      unit=unit, deadline=dl)
    return f"Ziel angelegt: {title}"


@T.register("update_goal", "Aktualisiert den Fortschritt eines Ziels (sucht per Titel).",
    {"query": {"type": "string"},
     "progress_pct": {"type": "integer", "description": "Fortschritt 0-100"},
     "current_value": {"type": "number"},
     "status": {"type": "string", "description": "active | done | paused | dropped"}},
    ["query"], "goals")
async def _update_goal(query: str, progress_pct: int = None,
                       current_value: float = None, status: str = None):
    g = goals.find_goal(query)
    if not g:
        return f"Ziel '{query}' nicht gefunden."
    goals.update_progress(g["id"], current_value=current_value,
                          progress_pct=progress_pct, status=status)
    return f"Ziel '{g['title']}' aktualisiert."


@T.register("list_goals", "Listet aktive Ziele mit Fortschritt.", {}, [], "goals")
async def _list_goals():
    gs = goals.list_goals()
    if not gs:
        return "Keine aktiven Ziele."
    return "\n".join(
        f"{g['title']} ({g['category']}): {g['progress_pct']}%"
        + (f" – {g['current_value']}/{g['target_value']} {g['unit'] or ''}" if g['target_value'] else "")
        for g in gs
    )
