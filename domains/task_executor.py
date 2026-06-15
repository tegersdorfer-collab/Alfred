"""
Alfred Deep Task Executor
- Planning: Bricht Tasks in Unteraufgaben auf, überlegt Strategie
- Research: DuckDuckGo + Claude Haiku für komplexe Analyse
- Clarification: Stellt Rückfragen via Telegram, hält Task in Hold
- Resume: Macht bei der nächsten offenen Unteraufgabe weiter
- Learning: Lernt aus abgelehnten Vorschlägen
"""
import json
import logging
from datetime import datetime

from core import db
from llm.base import LLMProvider, Message

log = logging.getLogger(__name__)

# ── Prompts ──────────────────────────────────────────────────────────────────

CLASSIFY_PROMPT = """Du bist Alfred. Eine neue Aufgabe wurde erstellt:

"{title}"
{notes_line}

Entscheide: Soll ich (Alfred) diese Aufgabe übernehmen oder Timo selbst?

Standard: ALFRED – ich übernehme alles was ich auch nur ansatzweise erledigen kann.
Im Zweifel immer ALFRED.

Nur USER wenn die Aufgabe ZWINGEND physische Präsenz erfordert:
- Einkaufen, Pakete abholen, irgendwo hinfahren
- Jemanden persönlich anrufen oder treffen
- Physische Objekte bedienen (Gerät kaufen, reparieren lassen)

Alles andere gehört zu ALFRED:
- Recherche, Analyse, Texte, Pläne, Entwürfe
- Daten auswerten (Training, Gesundheit, Finanzen)
- Strategien, Empfehlungen, Zusammenfassungen ausarbeiten
- Events, Erinnerungen, Notizen anlegen
- Entscheidungsgrundlagen vorbereiten

Antworte NUR mit: ALFRED oder USER"""

PLAN_PROMPT = """Du bist Alfred. Du sollst diese Aufgabe gründlich erledigen:

Aufgabe: {title}
{notes_line}

Was du über Timo weißt:
{memories}

Erstelle einen Ausführungsplan. Überlege:
1. Was ist das beste Ergebnis?
2. Welche Schritte sind nötig?
3. Brauchst du eine Rückfrage an Timo um die Aufgabe wirklich gut zu erledigen?
4. Welche Schritte benötigen Webrecherche?

Antworte im JSON-Format:
{{
  "clarification_needed": true/false,
  "clarification_question": "Frage an Timo falls nötig, sonst null",
  "subtasks": [
    {{"title": "Schritt 1", "needs_research": true/false, "research_query": "Suchanfrage falls nötig"}},
    {{"title": "Schritt 2", "needs_research": false, "research_query": null}}
  ]
}}"""

EXECUTE_SUBTASK_PROMPT = """Du bist Alfred. Erledige diesen Schritt einer größeren Aufgabe:

Hauptaufgabe: {main_title}
Aktueller Schritt: {subtask_title}
{research_section}
Bisherige Ergebnisse:
{previous_results}

Liefere ein konkretes, präzises Ergebnis für diesen Schritt.
Kein "ich könnte..." – direkt das Ergebnis."""

SYNTHESIZE_PROMPT = """Du bist Alfred. Du hast eine Aufgabe Schritt für Schritt erledigt.

Aufgabe: {title}
{notes_line}

Ergebnisse der einzelnen Schritte:
{step_results}

Fasse alles zu einer klaren, strukturierten Gesamtantwort zusammen.
Das ist das finale Ergebnis das Timo sieht."""

SUGGEST_PROMPT = """Du bist Alfred. Basierend auf einem neuen Impuls/neuen Daten überlege dir EINE einzige sinnvolle Aufgabe für Timo.

Neuer Impuls/Kontext:
{trigger}

Was du über Timo weißt:
{memories}

Offene Tasks (nicht doppeln):
{open_tasks}

Bereits abgelehnte Vorschläge – NIEMALS ähnliches vorschlagen:
{rejections}

Regeln:
- Genau EINE Aufgabe, nicht mehrere
- Konkreter Mehrwert, direkt aus dem Impuls abgeleitet
- Nicht etwas das bereits offen ist oder abgelehnt wurde
- Klar formuliert, umsetzbar
- Standard: ALFRED – nur USER wenn die Aufgabe zwingend physische Präsenz erfordert

Antworte im Format:
TITEL | KURZE BEGRÜNDUNG | ALFRED_ODER_USER"""

EVALUATE_SUGGESTION_PROMPT = """Du bist Alfred. Du möchtest Timo diese Aufgabe vorschlagen:

"{title}"
Begründung: {notes}

Ist dieser Vorschlag wirklich sinnvoll und wertvoll genug um ihn zu stören?

Kriterien für JA (alle erfüllt):
- Direkt aus echten Daten/Ereignissen abgeleitet
- Timo würde das wahrscheinlich wollen
- Nicht zu trivial oder offensichtlich
- Nicht ähnlich wie bestehende offene Tasks

Kriterien für NEIN (eines reicht):
- Zu generisch oder vage
- Kein echter Mehrwert
- Timo könnte es als unnötig empfinden

Antworte NUR mit: JA oder NEIN"""


# ── Classifier ────────────────────────────────────────────────────────────────

async def classify(title: str, notes: str | None, llm: LLMProvider) -> str:
    """Gibt 'alfred' oder 'user' zurück."""
    notes_line = f"Notiz: {notes}" if notes else ""
    try:
        resp = await llm.chat(
            messages=[Message(role="user", content=CLASSIFY_PROMPT.format(
                title=title, notes_line=notes_line
            ))],
            temperature=0.2, max_tokens=10,
        )
        return "alfred" if resp.strip().upper().startswith("ALFRED") else "user"
    except Exception as e:
        log.warning(f"Task-Klassifikation fehlgeschlagen: {e}")
        return "user"


# ── Planning ──────────────────────────────────────────────────────────────────

async def plan_task(task: dict, llm: LLMProvider, lzg=None) -> dict:
    """
    Plant die Ausführung: erstellt Unteraufgaben, erkennt ob Rückfrage nötig.
    Gibt den Plan als dict zurück.
    """
    notes_line = f"Details: {task['notes']}" if task.get("notes") else ""
    memories = []
    if lzg:
        try:
            mems = lzg.get_all()
            memories = [m.content for m in mems[:10]]
        except Exception:
            pass
    mem_str = "\n".join(f"- {m}" for m in memories) or "Keine"

    # Zuerst Claude Haiku versuchen (besser für komplexes Reasoning)
    from llm.claude import ClaudeProvider
    import config
    planner_llm = llm
    if config.ANTHROPIC_API_KEY:
        try:
            planner_llm = ClaudeProvider()
        except Exception:
            pass

    try:
        resp = await planner_llm.chat(
            messages=[Message(role="user", content=PLAN_PROMPT.format(
                title=task["title"],
                notes_line=notes_line,
                memories=mem_str,
            ))],
            temperature=0.4, max_tokens=800,
        )
        # JSON aus Antwort extrahieren (robuster Parser)
        import re
        # Finde den ersten { und den zugehörigen schließenden }
        start = resp.find('{')
        if start >= 0:
            depth, end = 0, start
            in_str, escape = False, False
            for i, ch in enumerate(resp[start:], start):
                if escape:
                    escape = False
                elif ch == '\\' and in_str:
                    escape = True
                elif ch == '"':
                    in_str = not in_str
                elif not in_str:
                    if ch == '{':
                        depth += 1
                    elif ch == '}':
                        depth -= 1
                        if depth == 0:
                            end = i
                            break
            try:
                return json.loads(resp[start:end+1])
            except json.JSONDecodeError:
                # Letzter Versuch: Trailing-Kommas und häufige Fehler beheben
                cleaned = re.sub(r',\s*([}\]])', r'\1', resp[start:end+1])
                return json.loads(cleaned)
    except Exception as e:
        log.warning(f"Planning fehlgeschlagen: {e}")

    # Fallback: einfacher Plan ohne Unteraufgaben
    return {
        "clarification_needed": False,
        "clarification_question": None,
        "subtasks": [{"title": task["title"], "needs_research": False, "research_query": None}]
    }


# ── Execution ─────────────────────────────────────────────────────────────────

async def execute_next_subtask(task: dict, llm: LLMProvider, search=None) -> bool:
    """
    Führt die nächste offene Unteraufgabe aus.
    Gibt True zurück wenn noch weitere ausstehen, False wenn alle fertig.
    """
    # Nächste offene Unteraufgabe holen
    subs = db.query(
        "SELECT * FROM tasks WHERE parent_id=%s AND status NOT IN ('done','archived') ORDER BY sort_order ASC, id ASC LIMIT 1",
        (task["id"],)
    )
    if not subs:
        return False  # Alle fertig

    sub = subs[0]

    # Bisherige Ergebnisse sammeln
    done_subs = db.query(
        "SELECT title, notes FROM tasks WHERE parent_id=%s AND status='done' ORDER BY id ASC",
        (task["id"],)
    )
    previous = "\n".join(
        f"- {s['title']}: {s['notes'][:200] if s.get('notes') else '✓'}"
        for s in done_subs
    ) or "Noch keine"

    # Webrecherche falls nötig
    research_section = ""
    _notes = sub.get("notes") or ""
    payload = json.loads(_notes) if _notes.startswith("{") else {}
    needs_research = payload.get("needs_research", False)
    research_query = payload.get("research_query")

    if needs_research and research_query and search:
        try:
            log.info(f"🔍 Recherchiere: {research_query}")
            results = await search.search(research_query, max_results=5)
            if results:
                formatted = search.format_results(results)
                research_section = f"Recherche-Ergebnisse:\n{formatted}\n"
        except Exception as e:
            log.warning(f"Websuche fehlgeschlagen: {e}")

    # Claude Haiku für Ausführung nutzen
    from llm.claude import ClaudeProvider
    import config
    exec_llm = llm
    if config.ANTHROPIC_API_KEY:
        try:
            exec_llm = ClaudeProvider()
        except Exception:
            pass

    subtask_title = sub["title"] if not _notes.startswith("{") else payload.get("title", sub["title"])

    try:
        result = await exec_llm.chat(
            messages=[Message(role="user", content=EXECUTE_SUBTASK_PROMPT.format(
                main_title=task["title"],
                subtask_title=subtask_title,
                research_section=research_section,
                previous_results=previous,
            ))],
            temperature=0.6, max_tokens=1000,
        )
        # Unteraufgabe als erledigt markieren, Ergebnis in notes
        db.execute(
            "UPDATE tasks SET status='done', completed_at=NOW(), notes=%s WHERE id=%s",
            (result[:2000], sub["id"])
        )
        log.info(f"✓ Unteraufgabe erledigt: {subtask_title}")
    except Exception as e:
        log.error(f"Unteraufgabe fehlgeschlagen: {e}")
        db.execute("UPDATE tasks SET status='archived' WHERE id=%s", (sub["id"],))

    # Prüfen ob noch weitere offen
    remaining = db.query(
        "SELECT id FROM tasks WHERE parent_id=%s AND status NOT IN ('done','archived')",
        (task["id"],)
    )
    return len(remaining) > 0


async def finalize_task(task: dict, llm: LLMProvider) -> str:
    """Fasst alle Unteraufgaben-Ergebnisse zum finalen Ergebnis zusammen."""
    done_subs = db.query(
        "SELECT title, notes FROM tasks WHERE parent_id=%s AND status='done' ORDER BY id ASC",
        (task["id"],)
    )

    if not done_subs:
        return "Aufgabe erledigt (keine Unteraufgaben)."

    # Wenn nur eine Unteraufgabe → direkt das Ergebnis
    if len(done_subs) == 1:
        return done_subs[0].get("notes") or "Erledigt."

    step_results = "\n\n".join(
        f"**{s['title']}**\n{s.get('notes', '')[:500]}"
        for s in done_subs
    )
    notes_line = f"Details: {task['notes']}" if task.get("notes") else ""

    from llm.claude import ClaudeProvider
    import config
    synth_llm = llm
    if config.ANTHROPIC_API_KEY:
        try:
            synth_llm = ClaudeProvider()
        except Exception:
            pass

    try:
        return await synth_llm.chat(
            messages=[Message(role="user", content=SYNTHESIZE_PROMPT.format(
                title=task["title"],
                notes_line=notes_line,
                step_results=step_results,
            ))],
            temperature=0.5, max_tokens=1500,
        )
    except Exception as e:
        log.warning(f"Synthese fehlgeschlagen: {e}")
        return step_results


# ── Älterer einfacher Executor (Fallback) ─────────────────────────────────────

async def execute_task(task: dict, llm: LLMProvider, lzg=None) -> str:
    """Legacy: einfache Ausführung ohne Unteraufgaben."""
    notes_line = f"Details: {task['notes']}" if task.get("notes") else ""
    from llm.claude import ClaudeProvider
    import config
    exec_llm = llm
    if config.ANTHROPIC_API_KEY:
        try:
            exec_llm = ClaudeProvider()
        except Exception:
            pass
    try:
        return await exec_llm.chat(
            messages=[Message(role="user", content=f"Erledige diese Aufgabe vollständig:\n\nAufgabe: {task['title']}\n{notes_line}\n\nLiefere ein konkretes, verwertbares Ergebnis. Kein 'ich könnte...' – direkt das Ergebnis.")],
            temperature=0.7, max_tokens=1200,
        )
    except Exception as e:
        log.error(f"Task-Ausführung fehlgeschlagen: {e}")
        return f"❌ Fehler: {e}"


# ── Suggestions ───────────────────────────────────────────────────────────────

async def suggest_one(trigger: str, llm: LLMProvider, lzg=None) -> bool:
    """Generiert EINE Aufgabe aus einem Impuls, mit Qualitätsprüfung."""
    from core import db as _db
    memories, open_tasks, rejections = [], [], []
    try:
        if lzg:
            mems = lzg.get_all()
            memories = [m.content for m in mems[:12]]
        open_tasks = [t["title"] for t in _db.query(
            "SELECT title FROM tasks WHERE status NOT IN ('done','archived') "
            "ORDER BY created_at DESC LIMIT 20"
        )]
        rejected_rows = _db.query(
            "SELECT title, rejection_reason FROM tasks "
            "WHERE suggestion_status='rejected' AND rejection_reason IS NOT NULL "
            "ORDER BY created_at DESC LIMIT 15"
        )
        rejections = [f"'{r['title'][:60]}' → {r['rejection_reason']}" for r in rejected_rows]
    except Exception:
        pass

    mem_str = "\n".join(f"- {m}" for m in memories) or "Keine bekannt"
    tasks_str = "\n".join(f"- {t}" for t in open_tasks) or "Keine"
    rejections_str = "\n".join(f"- {r}" for r in rejections) or "Keine bisherigen Ablehnungen"

    try:
        resp = await llm.chat(
            messages=[Message(role="user", content=SUGGEST_PROMPT.format(
                trigger=trigger, memories=mem_str, open_tasks=tasks_str,
                rejections=rejections_str
            ))],
            temperature=0.75, max_tokens=120,
        )
        line = resp.strip().splitlines()[0].strip()
        parts = [p.strip() for p in line.split("|")]
        if not parts or not parts[0]:
            return False
        title = parts[0]
        notes = parts[1] if len(parts) > 1 else None
        assignee = "alfred" if len(parts) > 2 and "ALFRED" in parts[2].upper() else "user"
    except Exception as e:
        log.warning(f"Suggestion-Generierung fehlgeschlagen: {e}")
        return False

    # Qualitätsprüfung
    try:
        verdict = await llm.chat(
            messages=[Message(role="user", content=EVALUATE_SUGGESTION_PROMPT.format(
                title=title, notes=notes or ""
            ))],
            temperature=0.1, max_tokens=5,
        )
        if not verdict.strip().upper().startswith("JA"):
            log.debug(f"Suggestion verworfen: {title}")
            return False
    except Exception as e:
        log.warning(f"Suggestion-Bewertung fehlgeschlagen: {e}")
        return False

    # Duplikat-Check: ähnliche Titel erkennen (Wort-Jaccard + Thema-Keywords)
    try:
        recent = _db.query(
            "SELECT title FROM tasks WHERE status != 'archived' ORDER BY created_at DESC LIMIT 50"
        )
        title_lower = title.lower()
        # Stopwörter herausfiltern, nur echte Inhaltswörter
        _stopwords = {"python", "skript", "einer", "einen", "eines", "basierend", "durch",
                      "durch", "sowie", "oder", "dass", "nicht", "werden", "können",
                      "diese", "dieses", "diese", "beim", "nach", "über", "unter", "vor",
                      "analyse", "erstellung", "generierung", "berechnung", "validierung",
                      "erstellen", "berechnen", "validieren", "identifikation", "isolierung"}
        new_kw = {w for w in title_lower.split() if len(w) > 5 and w not in _stopwords}
        for r in recent:
            existing = r["title"].lower()
            existing_kw = {w for w in existing.split() if len(w) > 5 and w not in _stopwords}
            if not new_kw or not existing_kw:
                continue
            overlap = len(new_kw & existing_kw) / max(1, len(new_kw | existing_kw))
            if overlap >= 0.30:
                log.debug(f"Suggestion als Duplikat verworfen (overlap={overlap:.2f}): {title[:60]}")
                return False
    except Exception as e:
        log.debug(f"Duplikat-Check fehlgeschlagen: {e}")

    try:
        _db.execute(
            """INSERT INTO tasks (title, notes, assigned_to, suggestion_status, priority)
               VALUES (%s, %s, %s, 'proposed', %s)""",
            (title, notes, assignee, "high" if assignee == "alfred" else "medium"),
        )
        log.info(f"💡 Neuer Task-Vorschlag: {title} ({assignee})")
        return True
    except Exception as e:
        log.warning(f"Suggestion-Speicherung fehlgeschlagen: {e}")
        return False


async def learn_from_rejection(task_id: int, reason: str, lzg=None, llm=None) -> None:
    """Speichert Ablehnungsgrund als Vermeidungsregel im Langzeitgedächtnis."""
    if not reason:
        return
    try:
        task = db.query_one("SELECT title FROM tasks WHERE id = %s", (task_id,))
        if task:
            rule = f"Aufgaben-Vermeidung: Schlage Timo NICHT vor '{task['title'][:80]}' (oder Ähnliches) – Grund: {reason}"
            if lzg and llm:
                try:
                    import numpy as np
                    emb = await llm.embed(rule)
                    lzg.save(content=rule, embedding=np.array(emb), category="preference", confidence=0.95)
                except Exception as _e:
                    log.debug(f"Rejection-Memory embed fehlgeschlagen: {_e}")
            log.info(f"Rejection gelernt: {task['title'][:60]} → {reason}")
    except Exception as e:
        log.warning(f"learn_from_rejection: {e}")
