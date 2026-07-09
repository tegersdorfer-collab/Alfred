"""
Kalender-Optimierer: analysiert den Tagesplan, erkennt Konflikte und
verschiebt/komprimiert Termine bei Bedarf.
"""
import logging
from datetime import datetime, timedelta, date

from llm.base import LLMProvider, Message

log = logging.getLogger(__name__)

# Typen die Mantis frei verschieben darf (keine externen Teilnehmer)
FLEXIBLE_KEYWORDS = [
    "deep work", "deep-work", "fokus", "lernen", "coding", "lesen",
    "sport", "gym", "training", "lauf", "workout", "meditation",
    "routine", "admin", "planung", "review", "journal",
]

def _is_flexible(title: str) -> bool:
    t = title.lower()
    return any(k in t for k in FLEXIBLE_KEYWORDS)

def _fmt(dt: datetime) -> str:
    return dt.strftime("%H:%M")

def _fmt_full(dt: datetime) -> str:
    return dt.strftime("%A %d.%m. %H:%M")


async def analyze_day(events: list, llm: LLMProvider, date_str: str = None) -> dict:
    """
    Analysiert den Tagesplan.
    Gibt zurück: {conflicts, suggestions, summary}
    """
    if not events:
        return {"conflicts": [], "suggestions": [], "summary": "Keine Termine heute."}

    today = date_str or date.today().isoformat()
    today_events = [e for e in events if hasattr(e, "start") and
                    (e.start.date() if hasattr(e.start, "date") else e.start) == date.fromisoformat(today)]

    if not today_events:
        return {"conflicts": [], "suggestions": [], "summary": "Keine Termine heute."}

    today_events.sort(key=lambda e: e.start)

    # Konflikte finden
    conflicts = []
    for i in range(len(today_events) - 1):
        a = today_events[i]
        b = today_events[i + 1]
        if a.end and b.start < a.end:
            conflicts.append({
                "a": a.title, "b": b.title,
                "overlap_min": int((a.end - b.start).total_seconds() / 60)
            })
        elif a.end and (b.start - a.end).total_seconds() < 300:  # <5min Puffer
            conflicts.append({
                "a": a.title, "b": b.title, "gap_min": 0, "note": "kein Puffer"
            })

    # LLM-Analyse für Vorschläge
    event_lines = []
    for e in today_events:
        end_str = f"–{_fmt(e.end)}" if e.end else ""
        flex = " [flexibel]" if _is_flexible(e.title) else " [fix]"
        event_lines.append(f"  {_fmt(e.start)}{end_str}: {e.title}{flex}")

    conflict_lines = ""
    if conflicts:
        conflict_lines = "\nKonflikte:\n" + "\n".join(
            f"  - '{c['a']}' überschneidet '{c['b']}' um {c.get('overlap_min', 0)} Min"
            if "overlap_min" in c else f"  - kein Puffer zwischen '{c['a']}' und '{c['b']}'"
            for c in conflicts
        )

    prompt = f"""Du bist Mantis, Timos persönlicher Assistent. Analysiere seinen heutigen Tagesplan.

Termine heute ({today}):
{chr(10).join(event_lines)}
{conflict_lines}

Aufgabe: Identifiziere Probleme und schlage konkrete Verbesserungen vor.
Termine mit [flexibel] dürfen verschoben werden. Termine mit [fix] nicht.

Antworte auf Deutsch, max 3-4 Sätze, direkt und konkret.
Falls alles passt: "Plan sieht gut aus."
Falls Anpassungen nötig: Nenne genau welcher Termin wohin verschoben werden soll (mit Uhrzeit)."""

    try:
        summary = await llm.chat(
            messages=[Message(role="user", content=prompt)],
            temperature=0.3, max_tokens=200
        )
    except Exception as e:
        summary = f"Analyse fehlgeschlagen: {e}"

    return {
        "conflicts": conflicts,
        "summary": summary.strip(),
        "today_events": [(e.title, _fmt(e.start), _fmt(e.end) if e.end else "") for e in today_events]
    }


async def reschedule_after_overrun(
    overrun_event_title: str,
    overrun_minutes: int,
    events: list,
    dashboard,
    llm: LLMProvider,
) -> str:
    """
    Wird aufgerufen wenn ein Termin länger dauerte als geplant.
    Verschiebt flexible Folge-Termine automatisch.
    """
    now = datetime.now()
    today_events = sorted(
        [e for e in events if hasattr(e, "start") and
         (e.start.date() if hasattr(e.start, "date") else e.start) == now.date() and
         e.start > now],
        key=lambda e: e.start
    )

    moved = []
    for ev in today_events:
        if not _is_flexible(ev.title):
            continue
        if not ev.end:
            continue
        new_start = ev.start + timedelta(minutes=overrun_minutes)
        new_end = ev.end + timedelta(minutes=overrun_minutes)
        # Nicht über Mitternacht schieben
        if new_end.date() > now.date():
            # Auf nächsten Tag verschieben
            next_day = now.date() + timedelta(days=1)
            duration = (ev.end - ev.start)
            new_start = datetime.combine(next_day, ev.start.time())
            new_end = new_start + duration
            action = f"auf morgen {_fmt(new_start)} verschoben"
        else:
            action = f"auf {_fmt(new_start)} verschoben"

        try:
            dashboard.update_event(ev.title, start=new_start, end=new_end)
            moved.append(f"'{ev.title}' {action}")
            log.info(f"📅 Kalender-Anpassung: {ev.title} → {action}")
        except Exception as e:
            log.warning(f"update_event fehlgeschlagen: {e}")

    if not moved:
        return f"Keine flexiblen Termine nach '{overrun_event_title}' zum Verschieben."

    return "Angepasst: " + "; ".join(moved)
