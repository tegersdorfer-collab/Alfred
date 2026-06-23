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
    channel: object = None      # CommunicationChannel (Telegram) – für proaktive Hinweise


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
async def _create_task(title: str, priority: str = "medium", kind: str = "task", due: str = None, notes: str = None):
    due_dt = parse_datetime(due) if due else None
    tid = tasks_d.create_task(title=title, notes=notes, priority=priority, kind=kind, due=due_dt)
    # Auto-Klassifikation: kann Alfred diese Task erledigen?
    assignee = "user"
    if CTX.llm:
        try:
            from domains.task_executor import classify
            assignee = await classify(title, notes, CTX.llm)
            from core import db as _db
            _db.execute("UPDATE tasks SET assigned_to=%s WHERE id=%s", (assignee, tid))
        except Exception:
            pass
    who = "Alfred übernimmt das" if assignee == "alfred" else "für dich eingetragen"
    return f"Aufgabe erstellt: {title} ({priority}) – {who}"


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


@T.register("update_calendar_event",
    "Ändert einen bestehenden Kalendereintrag (Titel, Zeit, Ort). Nutze dies wenn Timo "
    "sagt 'verschieb', 'ändere', 'verlege' einen Termin. Sucht per Titel-Stichwort.",
    {"query": {"type": "string", "description": "Stichwort aus dem Termintitel"},
     "title": {"type": "string", "description": "Neuer Titel (optional)"},
     "start": {"type": "string", "description": "Neue Startzeit (optional)"},
     "end": {"type": "string", "description": "Neue Endzeit (optional)"},
     "location": {"type": "string", "description": "Neuer Ort (optional)"}},
    ["query"], "productivity")
async def _update_event(query: str, title: str = None, start: str = None,
                        end: str = None, location: str = None):
    if not CTX.dashboard:
        return "Kalender nicht verfügbar."
    s = parse_datetime(start) if start else None
    e = parse_datetime(end) if end else None
    return CTX.dashboard.update_event(query, title=title, start=s, end=e, location=location)


@T.register("delete_calendar_event",
    "Löscht einen Kalendereintrag. Nutze dies wenn Timo sagt 'lösch den Termin', "
    "'streich den Termin', 'cancel', 'absagen' o.ä. Sucht per Titel-Stichwort.",
    {"query": {"type": "string", "description": "Stichwort aus dem Termintitel, z.B. 'Zahnarzt' oder 'Alfred Test'"}},
    ["query"], "productivity")
async def _delete_event(query: str):
    if not CTX.dashboard:
        return "Kalender nicht verfügbar."
    return CTX.dashboard.delete_event(query)


@T.register("reschedule_after_overrun",
    "Verschiebt flexible Folge-Termine wenn ein Termin länger gedauert hat als geplant. "
    "Nutze dies wenn Timo sagt 'das Meeting hat X Minuten länger gedauert', "
    "'wir sind überzogen', 'hat länger als geplant gedauert' o.ä.",
    {
        "event_title": {"type": "string", "description": "Titel des Termins der überzogen hat"},
        "overrun_minutes": {"type": "integer", "description": "Wie viele Minuten länger als geplant"},
    },
    ["event_title", "overrun_minutes"], "productivity")
async def _reschedule_overrun(event_title: str, overrun_minutes: int):
    if not CTX.dashboard:
        return "Kalender nicht verfügbar."
    from domains.calendar_optimizer import reschedule_after_overrun
    events = CTX.dashboard.get_upcoming_events(days=1)
    return await reschedule_after_overrun(event_title, overrun_minutes, events, CTX.dashboard, CTX.llm)


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
    hid = _db.insert_returning(
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


# ════════════════════════════════════════════════════════════════════════════
#  RECHNER

@T.register("calculate",
    "Führt eine mathematische Berechnung exakt aus. "
    "Nutze dies IMMER wenn du Zahlen addierst, subtrahierst, multiplizierst, dividierst "
    "oder Durchschnitte, Prozente, Verhältnisse berechnest — niemals im Kopf rechnen.",
    {"expression": {"type": "string", "description": "Mathematischer Ausdruck z.B. '111 / 36' oder '(80 + 90) / 2'"}},
    ["expression"], "utility")
async def _calculate(expression: str) -> str:
    import ast
    import math
    import operator
    import statistics

    _OPS = {
        ast.Add: operator.add, ast.Sub: operator.sub,
        ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.Mod: operator.mod,
        ast.FloorDiv: operator.floordiv,
        ast.USub: operator.neg, ast.UAdd: operator.pos,
    }
    _NAMES = {k: v for k, v in vars(math).items() if not k.startswith("_")}
    _NAMES["statistics"] = statistics

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](_eval(node.operand))
        if isinstance(node, ast.Name) and node.id in _NAMES:
            return _NAMES[node.id]
        if isinstance(node, ast.Call):
            fn = _eval(node.func)
            if callable(fn):
                return fn(*[_eval(a) for a in node.args])
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "statistics":
            attr = getattr(statistics, node.attr, None)
            if callable(attr) and not node.attr.startswith("_"):
                return attr
        if isinstance(node, ast.List):
            return [_eval(e) for e in node.elts]
        raise ValueError(f"Nicht erlaubter Ausdruck: {ast.dump(node)}")

    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval(tree.body)
        return f"{expression} = {result}"
    except Exception as e:
        return f"Fehler: {e}"


#  SELF-MODIFICATION

@T.register("read_own_code",
    "Liest eine Datei aus Alfred' eigener Codebase. Nutze dies bevor du Code änderst "
    "um den aktuellen Stand zu verstehen.",
    {"path": {"type": "string", "description": "Relativer Pfad z.B. 'domains/health.py' oder 'web/index.html'"}},
    ["path"], "system")
async def _read_own_code(path: str):
    from domains.self_modify import read_file
    return read_file(path)


@T.register("list_own_files",
    "Listet Dateien in Alfred' Codebase. Nutze dies zur Orientierung.",
    {"directory": {"type": "string", "description": "Verzeichnis z.B. 'domains' oder 'web' (leer = alles)"}},
    [], "system")
async def _list_own_files(directory: str = ""):
    from domains.self_modify import list_files
    files = list_files(directory)
    return "\n".join(files) if files else "Keine Dateien gefunden."


@T.register("write_own_code",
    "Schreibt oder überschreibt eine Datei in Alfred' Codebase. "
    "Erstellt automatisch ein Git-Backup und triggert einen gesicherten Neustart. "
    "Bei Fehler wird automatisch zur alten Version zurückgerollt. "
    "Nutze dies für Bugfixes, neue Features, UI-Änderungen. "
    "IMMER zuerst read_own_code aufrufen um den aktuellen Stand zu lesen!",
    {
        "path": {"type": "string", "description": "Relativer Pfad z.B. 'domains/health.py'"},
        "content": {"type": "string", "description": "Vollständiger neuer Inhalt der Datei"},
        "description": {"type": "string", "description": "Kurze Beschreibung was geändert wurde und warum"},
    },
    ["path", "content", "description"], "system")
async def _write_own_code(path: str, content: str, description: str):
    from domains.self_modify import write_file
    result = write_file(path, content, description)
    if result["ok"]:
        return f"✅ {result['message']}\nAlfred startet neu und prüft ob alles funktioniert. Bei Fehler: automatischer Rollback zu {result['backup_commit'][:8]}."
    return f"❌ {result['message']}"


#  SKILL-FACTORY – Alfred baut sich selbst neue Tools, statt "kann ich nicht" zu sagen

@T.register("create_skill",
    "Erstellt UND AKTIVIERT SOFORT ein komplett neues Tool für dich selbst, wenn für eine "
    "Anfrage kein passendes Tool existiert. NUTZE DIES bevor du sagst 'das kann ich nicht' "
    "oder 'dafür habe ich keine Funktion' – baue dir die Fähigkeit stattdessen selbst. "
    "Schreibe EINE einzige 'async def <skill_name>(...)'-Funktion, dekoriert mit "
    "@T.register(name, beschreibung, parameter_schema, required, kategorie) – exakt im "
    "selben Stil wie die anderen Tools in core/skills.py. Erlaubte Imports: asyncio, json, "
    "re, math, statistics, datetime, time, uuid, httpx, config, core.* (z.B. core.db), "
    "domains.* (bestehende Domain-Funktionen wiederverwenden!), llm.*, memory.*, tools.*. "
    "KEIN os/subprocess/socket/eval/exec/open – wird automatisch geprüft und sonst abgelehnt. "
    "Die Funktion muss einen String zurückgeben (wie alle anderen Tools).",
    {
        "skill_name": {"type": "string", "description": "snake_case Tool-Name, z.B. 'convert_currency'"},
        "description": {"type": "string", "description": "Kurze Beschreibung wofür das Skill gut ist"},
        "source_code": {"type": "string", "description": "Vollständiger Python-Code: Decorator @T.register(...) + 'async def <skill_name>(...): ...'"},
    },
    ["skill_name", "description", "source_code"], "system")
async def _create_skill(skill_name: str, description: str, source_code: str):
    from core.skill_factory import create_skill
    result = create_skill(skill_name, description, source_code)
    if result["ok"]:
        if CTX.channel:
            try:
                await CTX.channel.send(f"🛠️ Neues Skill erstellt: **{skill_name}**\n_{description}_")
            except Exception:
                pass
        try:
            from core import push
            import asyncio as _asyncio
            await _asyncio.to_thread(push.send_push, "🛠️ Neues Skill", f"{skill_name}: {description}", "/?view=settings")
        except Exception:
            pass
    return f"✅ {result['message']}" if result["ok"] else f"❌ {result['message']}"


@T.register("delete_skill",
    "Entfernt ein zuvor von dir selbst erstelltes Skill (z.B. wenn es fehlerhaft ist oder "
    "nicht mehr gebraucht wird). Funktioniert nur für Skills, die über create_skill entstanden sind.",
    {"skill_name": {"type": "string", "description": "Name des zu entfernenden Skills"}},
    ["skill_name"], "system")
async def _delete_skill(skill_name: str):
    from core.skill_factory import delete_skill
    result = delete_skill(skill_name)
    return f"✅ {result['message']}" if result["ok"] else f"❌ {result['message']}"


@T.register("list_dynamic_skills",
    "Listet alle Skills auf, die du dir selbst zur Laufzeit erstellt hast.",
    {}, [], "system")
async def _list_dynamic_skills():
    from core.skill_factory import list_dynamic_skills
    names = list_dynamic_skills()
    return "\n".join(names) if names else "Noch keine selbst erstellten Skills."


# ── Second Brain ──────────────────────────────────────────────────────────────

@T.register("brain_save",
    "Speichert eine Notiz, Erkenntnis, Entscheidung oder Information im Second Brain. "
    "Kategorien: context (über Timo), inbox (unsortiert), project (aktives Projekt), "
    "area (laufende Verantwortlichkeit), resource (Wissen/Recherche), daily (Tageslog), archive.",
    {
        "title":    {"type": "string",  "description": "Kurzer Titel der Notiz"},
        "content":  {"type": "string",  "description": "Inhalt der Notiz (Markdown, [[Wiki-Links]] unterstützt)"},
        "category": {"type": "string",  "description": "Kategorie: inbox | context | project | area | resource | daily | archive"},
        "tags":     {"type": "array",   "items": {"type": "string"}, "description": "Optionale Tags"},
    },
    ["title", "content"], "knowledge")
async def _brain_save(title: str, content: str, category: str = "inbox", tags: list = None):
    from domains.second_brain import brain_tool_save
    return brain_tool_save(title, content, category, tags)


@T.register("brain_search",
    "Durchsucht das Second Brain nach gespeichertem Wissen, Notizen, Projekten oder Entscheidungen.",
    {"query": {"type": "string", "description": "Suchbegriff oder Thema"}},
    ["query"], "knowledge")
async def _brain_search(query: str):
    from domains.second_brain import brain_tool_search
    return brain_tool_search(query)


@T.register("brain_inbox",
    "Wirft schnell einen Gedanken, eine Idee oder einen Brain-Dump in die Inbox des Second Brains. "
    "Alfred sortiert die Inbox regelmäßig automatisch ein.",
    {"content": {"type": "string", "description": "Der Gedanke oder die Idee die gespeichert werden soll"}},
    ["content"], "knowledge")
async def _brain_inbox(content: str):
    from domains.second_brain import brain_tool_inbox_add
    return brain_tool_inbox_add(content)


@T.register("brain_daily_log",
    "Schreibt einen Eintrag in die heutige Daily Note des Second Brains. "
    "Ideal für Tagesrückblicke, Entscheidungen, erledigte Dinge.",
    {"entry": {"type": "string", "description": "Was heute passiert ist oder entschieden wurde"}},
    ["entry"], "knowledge")
async def _brain_daily_log(entry: str):
    from domains.second_brain import brain_tool_daily_log
    return brain_tool_daily_log(entry)


@T.register("suggest_next_weight",
    "Schlägt das optimale Trainingsgewicht für eine Übung vor basierend auf den letzten Sessions (AlphaProgression).",
    {"exercise": {"type": "string", "description": "Name der Übung (z.B. 'Bench Press', 'Squat')"},
     "reps_target": {"type": "integer", "description": "Ziel-Wiederholungen pro Satz (default 8)"}},
    ["exercise"], "fitness")
def _suggest_next_weight(exercise: str, reps_target: int = 8):
    from domains.fitness import suggest_next_weight
    r = suggest_next_weight(exercise, reps_target=reps_target)
    if not r.get("suggestion_kg"):
        return r.get("reason", "Keine Daten.")
    return (f"{exercise}: zuletzt {r['last_weight_kg']}kg ({r['last_date']}) → "
            f"empfohlen **{r['suggestion_kg']}kg**\nGrund: {r['reason']}")


@T.register("progression_report",
    "Zeigt Progressionsbericht für alle Übungen der letzten N Tage.",
    {"days": {"type": "integer", "description": "Zeitraum in Tagen (default 30)"}},
    [], "fitness")
def _progression_report(days: int = 30):
    from domains.fitness import progression_report
    items = progression_report(days)
    if not items:
        return "Keine Progressionsdaten gefunden."
    lines = [f"**{r['exercise']}**: {r.get('last_weight_kg')}kg → {r.get('suggestion_kg')}kg ({r.get('reason','')})"
             for r in items]
    return f"Progressionsbericht ({days} Tage):\n" + "\n".join(lines)


@T.register("import_kindle_highlights",
    "Importiert Kindle-Highlights aus dem 'My Clippings.txt'-Format ins Second Brain als Quotes. "
    "Pfad zur Clippings-Datei oder Text direkt einfügen.",
    {
        "file_path": {"type": "string", "description": "Pfad zur My Clippings.txt"},
        "raw_text":  {"type": "string", "description": "Inhalt direkt als Text (Alternative zu file_path)"},
        "limit":     {"type": "integer","description": "Max. Highlights importieren (default 50)"},
    },
    [], "knowledge")
def _import_kindle_highlights(file_path: str = "", raw_text: str = "", limit: int = 50):
    import re
    from domains.second_brain import add_quote

    if file_path:
        try:
            text = open(file_path, encoding="utf-8-sig", errors="replace").read()
        except Exception as e:
            return f"Datei nicht lesbar: {e}"
    elif raw_text:
        text = raw_text
    else:
        # Suche Standard-Kindle-Pfade
        from pathlib import Path
        candidates = [
            Path.home() / "Documents" / "My Clippings.txt",
            Path("/Volumes/Kindle/documents/My Clippings.txt"),
        ]
        found = next((p for p in candidates if p.exists()), None)
        if not found:
            return "Keine Clippings.txt gefunden. Pfad angeben oder Text direkt einfügen."
        text = found.read_text(encoding="utf-8-sig", errors="replace")

    # Kindle-Format: ========== \n Titel (Autor)\n Deine Markierung | ...\n\n Text\n=====
    blocks = [b.strip() for b in text.split("==========") if b.strip()]
    imported = 0
    for block in blocks[:limit]:
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if len(lines) < 3:
            continue
        book = lines[0]
        # Highlight-Text ist alles ab Zeile 3
        highlight = " ".join(lines[2:]).strip()
        if len(highlight) < 15:
            continue
        author_match = re.search(r'\(([^)]+)\)\s*$', book)
        author = author_match.group(1) if author_match else ""
        title  = re.sub(r'\s*\([^)]+\)\s*$', '', book).strip()
        source = f"{title} — {author}" if author else title
        add_quote(text=highlight, source=source, tags=["kindle", "highlight"])
        imported += 1

    return f"✅ {imported} Kindle-Highlights als Quotes importiert."


@T.register("speak",
    "Liest Text laut vor via macOS Text-to-Speech (Stimme: Lucía/Anna). "
    "Ideal für Voice-Antworten wenn Timo das Dashboard offen hat.",
    {
        "text":  {"type": "string",  "description": "Vorzulesender Text (max. 500 Zeichen)"},
        "voice": {"type": "string",  "description": "Stimme: 'anna' (DE) oder 'alex' (EN), default 'anna'"},
    },
    ["text"], "system")
def _speak(text: str, voice: str = "anna"):
    import subprocess, re
    clean = re.sub(r'[*_`#\[\]()]', '', text)[:500]
    voice_map = {"anna": "Anna", "alex": "Alex", "lucía": "Lucía", "lucia": "Lucía"}
    v = voice_map.get(voice.lower(), "Anna")
    try:
        subprocess.Popen(["say", "-v", v, clean])
        return f"🔊 Spreche: \"{clean[:60]}…\"" if len(clean) > 60 else f"🔊 Spreche: \"{clean}\""
    except Exception as e:
        return f"TTS fehlgeschlagen: {e}"


@T.register("add_research_query",
    "Speichert ein Thema für die wöchentliche Recherche (jeden Montag automatisch). "
    "Beispiel: 'KI-News', 'Roblox-Entwicklung', 'Fitness-Wissenschaft'.",
    {"topic": {"type": "string", "description": "Thema das wöchentlich recherchiert werden soll"}},
    ["topic"], "knowledge")
def _add_research_query(topic: str):
    from domains.second_brain import add_note
    add_note(title=topic, content=f"Wöchentliche Recherche-Query: {topic}",
             category="resource", tags=["research_query"])
    return f"Recherche-Query gespeichert: '{topic}'. Jeden Montag wird dazu automatisch recherchiert."


@T.register("fetch_and_summarize_url",
    "Lädt eine URL (Artikel, YouTube-Seite, Blogpost), extrahiert den Text, "
    "bewertet Kernaussagen und speichert Insights ins Second Brain.",
    {
        "url":      {"type": "string",  "description": "URL des Artikels oder der YouTube-Seite"},
        "save":     {"type": "boolean", "description": "In Second Brain speichern (default true)"},
        "category": {"type": "string",  "description": "brain_notes Kategorie (default 'resource')"},
    },
    ["url"], "knowledge")
async def _fetch_and_summarize_url(url: str, save: bool = True, category: str = "resource"):
    import httpx, re
    from llm import fast as _fast

    # Fetch
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True,
                                      headers={"User-Agent": "Mozilla/5.0 Alfred/1.0"}) as c:
            r = await c.get(url)
        html = r.text
    except Exception as e:
        return f"Fetch fehlgeschlagen: {e}"

    # Einfache Text-Extraktion (kein BeautifulSoup nötig)
    text = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    excerpt = text[:6000]

    if len(excerpt) < 200:
        return "Zu wenig Text extrahiert – Seite könnte JavaScript-only sein."

    prompt = (
        "Analysiere diesen Web-Inhalt. Antworte auf Deutsch.\n"
        "1. KERNAUSSAGEN: 3-5 Bullet Points (was ist wichtig/neu/interessant)\n"
        "2. BEWERTUNG: Was ist gut, was ist fragwürdig oder oberflächlich?\n"
        "3. RELEVANZ FÜR TIMO: Konkrete Anwendung oder nächster Schritt.\n\n"
        f"URL: {url}\nInhalt:\n{excerpt}"
    )
    summary = await _fast.ask(prompt, max_tokens=400)

    if save:
        from domains.second_brain import add_note
        # Titel aus URL ableiten
        title = url.split("/")[-1][:60].replace("-", " ").replace("_", " ") or url[:60]
        content = f"**Quelle:** {url}\n\n{summary}"
        add_note(title=title, content=content, category=category, tags=["web", "import"])
        return f"✅ Zusammenfassung gespeichert:\n\n{summary[:600]}"
    return summary


@T.register("log_body_measurement",
    "Speichert Körpermessungen (Umfänge, Gewicht, Körperfett). Alle Werte optional.",
    {
        "weight_kg": {"type": "number", "description": "Gewicht in kg"},
        "waist_cm":  {"type": "number", "description": "Taillenumfang in cm"},
        "chest_cm":  {"type": "number", "description": "Brustumfang in cm"},
        "hips_cm":   {"type": "number", "description": "Hüftumfang in cm"},
        "bicep_cm":  {"type": "number", "description": "Bizepsumfang in cm"},
        "thigh_cm":  {"type": "number", "description": "Oberschenkelumfang in cm"},
        "neck_cm":   {"type": "number", "description": "Halsumfang in cm"},
        "body_fat":  {"type": "number", "description": "Körperfett in %"},
        "notes":     {"type": "string", "description": "Notizen"},
    },
    [], "fitness")
def _log_body_measurement(weight_kg=None, waist_cm=None, chest_cm=None, hips_cm=None,
                           bicep_cm=None, thigh_cm=None, neck_cm=None, body_fat=None, notes=None):
    from domains.body import log_measurement
    mid = log_measurement(weight_kg=weight_kg, waist_cm=waist_cm, chest_cm=chest_cm,
                          hips_cm=hips_cm, bicep_cm=bicep_cm, thigh_cm=thigh_cm,
                          neck_cm=neck_cm, body_fat=body_fat, notes=notes)
    return f"Körpermessung gespeichert (ID {mid})."


@T.register("body_progress",
    "Zeigt Fortschritt der Körpermessungen über die letzten Wochen.",
    {"weeks": {"type": "integer", "description": "Anzahl Wochen (default 8)"}},
    [], "fitness")
def _body_progress(weeks: int = 8):
    from domains.body import progress_summary
    return progress_summary(weeks)


@T.register("save_quote",
    "Speichert ein Zitat ins Second Brain. Gedanken dazu können später mit add_thought_to_quote ergänzt werden.",
    {
        "text":   {"type": "string", "description": "Das Zitat"},
        "source": {"type": "string", "description": "Autor oder Quelle"},
        "tags":   {"type": "array",  "items": {"type": "string"}, "description": "Themen-Tags"},
    },
    ["text"], "knowledge")
def _save_quote(text: str, source: str = "", tags: list = None):
    from domains.second_brain import add_quote
    q = add_quote(text, source, tags)
    return f"Zitat gespeichert (ID {q.get('id', '?')}): \"{text[:60]}\""


@T.register("add_thought_to_quote",
    "Fügt einen neuen Gedanken zu einem gespeicherten Zitat hinzu.",
    {
        "note_id": {"type": "integer", "description": "ID des Zitat-Eintrags im Second Brain"},
        "thought": {"type": "string",  "description": "Dein aktueller Gedanke dazu"},
    },
    ["note_id", "thought"], "knowledge")
def _add_thought_to_quote(note_id: int, thought: str):
    from domains.second_brain import add_thought_to_quote
    ok = add_thought_to_quote(note_id, thought)
    return "Gedanke hinzugefügt." if ok else "Zitat nicht gefunden."


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


@T.register("nutrition_advice",
    "Gibt kontextuellen Ernährungs-Rat basierend auf aktuellem Tagesstand (Kalorien, Protein, "
    "Mahlzeiten) + heutige Health-Daten (Schritte, HRV, Schlaf). Ideal für Fragen wie "
    "'Soll ich Pizza essen?', 'Wie viel Kalorien habe ich noch?', 'Reicht mein Protein?'.",
    {"question": {"type": "string", "description": "Die Frage zu Ernährung oder Essen"}},
    ["question"], "nutrition")
async def _nutrition_advice(question: str):
    from domains import nutrition, health as health_d
    from core import db as _db
    from datetime import date

    totals = nutrition.day_totals()
    meals = nutrition.meals_for()

    goal_cal = _db.get_setting("calorie_goal", 2200)
    goal_prot = _db.get_setting("protein_goal", 150)

    remaining_cal = goal_cal - (totals.get("calories") or 0)
    remaining_prot = goal_prot - (totals.get("protein_g") or 0)

    health_row = _db.query_one(
        "SELECT steps, hrv, sleep_total_h, resting_hr FROM health_data ORDER BY date DESC LIMIT 1"
    )

    lines = [
        f"Frage: {question}",
        f"\nHeutiger Ernährungs-Stand:",
        f"  Kalorien: {int(totals.get('calories') or 0)} / {goal_cal} kcal (noch {int(remaining_cal)} übrig)",
        f"  Protein: {int(totals.get('protein_g') or 0)} / {goal_prot}g (noch {int(remaining_prot)}g übrig)",
    ]
    if meals:
        lines.append(f"  Mahlzeiten heute: {', '.join(m['description'] for m in meals[:4])}")
    if health_row:
        lines.append(f"\nHeutige Health-Daten:")
        if health_row.get("steps"):
            lines.append(f"  Schritte: {health_row['steps']}")
        if health_row.get("hrv"):
            lines.append(f"  HRV: {health_row['hrv']} ms")
        if health_row.get("sleep_total_h"):
            lines.append(f"  Schlaf: {health_row['sleep_total_h']:.1f}h")

    return "\n".join(lines)


@T.register("claude_code_run",
    "Startet eine Claude Code Aufgabe im Hintergrund (z.B. 'Baue Feature X', "
    "'Schreibe Tests für Y', 'Refactor Z'). Alfred spawnt einen claude-Subprocess, "
    "du bekommst eine Push-Notification wenn er fertig ist.",
    {
        "task":    {"type": "string",  "description": "Was Claude Code tun soll"},
        "workdir": {"type": "string",  "description": "Arbeitsverzeichnis (Standard: ~/Alfred)"},
    },
    ["task"], "system")
async def _claude_code_run(task: str, workdir: str = "/Users/timoegersdorfer/Alfred"):
    import asyncio, subprocess, time
    from core import push as _push, db as _db

    start = time.time()

    async def _run():
        try:
            proc = await asyncio.create_subprocess_exec(
                "claude", "--print", task,
                cwd=workdir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
            elapsed = int(time.time() - start)
            result = stdout.decode()[:500] if stdout else ""
            err = stderr.decode()[:200] if stderr else ""
            summary = f"claude --print fertig nach {elapsed}s"
            if result:
                summary += f"\n{result}"
            if err and proc.returncode != 0:
                summary += f"\nFehler: {err}"
            try:
                _push.send_push("🤖 Claude Code fertig", summary[:120], "/")
            except Exception:
                pass
            if CTX.channel:
                try:
                    await CTX.channel.send(f"✅ Claude Code Aufgabe fertig ({elapsed}s):\n_{task[:80]}_")
                except Exception:
                    pass
        except asyncio.TimeoutError:
            if CTX.channel:
                try:
                    await CTX.channel.send(f"⏱ Claude Code Timeout nach 5 Minuten: _{task[:60]}_")
                except Exception:
                    pass
        except FileNotFoundError:
            if CTX.channel:
                try:
                    await CTX.channel.send("❌ `claude` CLI nicht gefunden. Ist Claude Code installiert?")
                except Exception:
                    pass

    asyncio.create_task(_run())
    return f"Claude Code gestartet für: '{task[:80]}'\nArbeitsverzeichnis: {workdir}\nDu bekommst eine Notification wenn er fertig ist."


# ── Git-History als Gedächtnis ─────────────────────────────────────────────────

@T.register(
    "git_history_import",
    "Importiert Git-Commit-History eines Repos als Wissens-Notizen ins Second Brain.",
    [
        {"name": "repos", "type": "string",
         "description": "Kommagetrennte Pfade oder 'auto' für automatische Suche in ~/Documents, ~/Developer etc."},
        {"name": "limit", "type": "integer",
         "description": "Max. Commits pro Repo (default 100)"},
    ],
)
def _git_history_import(repos: str = "auto", limit: int = 100) -> str:
    import subprocess, os
    from pathlib import Path
    from domains import second_brain as _brain

    search_roots = [Path.home() / d for d in ["Documents", "Developer", "Projects", "repos", "code", "Alfred"]]

    if repos.strip().lower() == "auto":
        found = []
        for root in search_roots:
            if not root.exists():
                continue
            for p in root.iterdir():
                if p.is_dir() and (p / ".git").exists():
                    found.append(str(p))
        repo_paths = found[:10]
    else:
        repo_paths = [r.strip() for r in repos.split(",") if r.strip()]

    if not repo_paths:
        return "Keine Git-Repos gefunden."

    total_imported = 0
    summaries = []

    for repo in repo_paths:
        if not os.path.exists(os.path.join(repo, ".git")):
            continue
        try:
            result = subprocess.run(
                ["git", "-C", repo, "log",
                 f"--max-count={limit}",
                 "--pretty=format:%ad|%s",
                 "--date=short"],
                capture_output=True, text=True, timeout=10,
            )
            lines = [l for l in result.stdout.strip().split("\n") if "|" in l]
            if not lines:
                continue

            repo_name = os.path.basename(repo)
            entries_by_month: dict[str, list[str]] = {}
            for line in lines:
                parts = line.split("|", 1)
                if len(parts) < 2:
                    continue
                date_str, subject = parts[0], parts[1]
                month = date_str[:7]
                entries_by_month.setdefault(month, []).append(f"- {date_str}: {subject}")

            for month, commits in sorted(entries_by_month.items(), reverse=True):
                title = f"Git-Log {repo_name} {month}"
                existing = _brain.search_notes(title, limit=1)
                if not existing:
                    content = f"# Git-History: {repo_name} — {month}\n\n" + "\n".join(commits[:50])
                    _brain.add_note(title=title, content=content, category="resource",
                                    tags=["git", repo_name, "history"])
                    total_imported += 1

            summaries.append(f"{repo_name}: {len(lines)} Commits → {len(entries_by_month)} Monatskarten")
        except Exception as e:
            summaries.append(f"{repo_name}: Fehler ({e})")

    if total_imported:
        return f"✅ Git-History importiert: {total_imported} Monatskarten.\n" + "\n".join(summaries)
    return "Nichts Neues importiert (bereits vorhanden).\n" + "\n".join(summaries)


# ── Tool Discovery Escape Hatch ────────────────────────────────────────────────

@T.register(
    "refresh_tools",
    "Scannt ob neue Skill-Dateien verfügbar sind und zeigt aktuelle Tool-Anzahl. Aufrufen wenn eine Fähigkeit zu fehlen scheint.",
    [],
)
def _refresh_tools() -> str:
    tools = T.all_tools() if hasattr(T, "all_tools") else []
    n = len(tools)
    return (
        f"{n} Tools aktuell verfügbar. "
        "Falls ein benötigtes Tool fehlt: create_skill nutzen um es selbst zu bauen."
    )


# ── Subagent Delegation (Hermes-Pattern) ──────────────────────────────────────

@T.register(
    "delegate_task",
    "Delegiert eine komplexe Teilaufgabe an einen isolierten Unteragenten. Ideal für umfangreiche Analysen, Reports oder mehrstufige Operationen die den Hauptkontext nicht aufblähen sollen.",
    {
        "goal": {"type": "string", "description": "Was der Unteragent erreichen soll (natürlichsprachlich, konkret)"},
        "context": {"type": "string", "description": "Zusätzlicher Kontext aus dem aktuellen Gespräch (optional)"},
        "tools": {"type": "array", "items": {"type": "string"}, "description": "Explizite Tool-Liste (optional, leer = alle erlaubten)"},
    },
    ["goal"],
    category="productivity",
)
async def _delegate_task(goal: str, context: str = "", tools: list | None = None) -> str:
    from tools.delegate import run_subagent
    return await run_subagent(
        goal=goal,
        context=context,
        allowed_tools=tools or None,
    )


# ── SKILL.md Management (Hermes-Pattern) ──────────────────────────────────────

@T.register(
    "list_skill_procedures",
    "Zeigt alle gespeicherten SKILL.md Prozeduren die Alfred über die Zeit gelernt hat.",
    [],
    category="general",
)
def _list_skill_procedures() -> str:
    from core.skill_md import list_all
    skills = list_all()
    if not skills:
        return "Noch keine Skill-Prozeduren gespeichert."
    lines = [f"**{s['name']}**: {s['description']} (Trigger: {', '.join(s['triggers'][:3])})"
             for s in skills]
    return f"{len(skills)} Prozedur-Skills:\n" + "\n".join(lines)


@T.register(
    "update_skill_procedure",
    "Aktualisiert eine bestehende SKILL.md Prozedur. Nutzen wenn Alfred eine bessere Vorgehensweise für eine bekannte Aufgabe gelernt hat.",
    {
        "name": {"type": "string", "description": "Skill-Name (snake_case)"},
        "new_body": {"type": "string", "description": "Neue Prozedur-Beschreibung"},
    },
    ["name", "new_body"],
    category="general",
)
def _update_skill_procedure(name: str, new_body: str) -> str:
    from core.skill_md import update_skill
    if update_skill(name, new_body):
        return f"✅ Skill-Prozedur '{name}' aktualisiert."
    return f"❌ Skill '{name}' nicht gefunden. Mit list_skill_procedures prüfen."

