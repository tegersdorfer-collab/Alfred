"""
Insight Engine – generiert sinnvolle Aufgaben aus DB-Daten.

Analysiert Health, Goals, Tasks und Memories und erstellt proaktiv
Aufgaben die echten Mehrwert für Timo liefern.
"""
import logging
from datetime import date

from core import db
from llm.base import LLMProvider, Message

log = logging.getLogger(__name__)

INSIGHT_PROMPT = """Du bist Mantis. Analysiere Timos Daten und generiere EINE sinnvolle, konkrete Aufgabe.

## Gesundheitsdaten (letzte 14 Tage):
{health_summary}

## Muster & Metriken:
{metrics}

## Bekannte Ziele & Memories:
{memories}

## Aktuell offene Aufgaben (nicht wiederholen):
{open_tasks}

## Bereits abgelehnte Vorschläge (NIEMALS ähnliches):
{rejections}

## Regeln:
- Genau EINE Aufgabe
- Direkt aus einem KONKRETEN Datenmuster abgeleitet (benenne das Muster)
- Kein "Python-Skript" – lieber: Trainingsplan, Ernährungsanalyse, Recherche, Strategie, Text
- Nicht zu technisch, nicht zu abstrakt
- MANTIS übernimmt alles was möglich ist

Antworte im Format:
TITEL | KURZE BEGRÜNDUNG (Datenmuster) | MANTIS_ODER_USER"""


def _parse_insight_line(resp: str) -> tuple[str, str | None, str] | None:
    """Parst die LLM-Antwort 'TITEL | BEGRÜNDUNG | MANTIS/USER'.

    Gibt (title, notes, assignee) zurück oder None, wenn leer/ohne Titel.
    Fehlt der Assignee-Teil oder enthält er 'MANTIS' → 'mantis', sonst 'user'.
    """
    stripped = (resp or "").strip()
    if not stripped:
        return None
    line = stripped.splitlines()[0].strip()
    parts = [p.strip() for p in line.split("|")]
    if not parts or not parts[0]:
        return None
    title = parts[0]
    notes = parts[1] if len(parts) > 1 else None
    assignee = "mantis" if len(parts) < 3 or "MANTIS" in parts[2].upper() else "user"
    return title, notes, assignee


async def generate_insight_task(llm: LLMProvider, lzg=None) -> bool:
    """Analysiert DB-Daten und erstellt eine sinnvolle Aufgabe."""

    # Health-Zusammenfassung aus DB
    health_rows = db.query(
        "SELECT date, steps, active_calories, sleep_duration, hrv, resting_hr, weight "
        "FROM health_data ORDER BY date DESC LIMIT 14"
    )
    if not health_rows:
        return False

    health_lines = []
    for r in health_rows:
        parts = [str(r["date"])]
        if r["steps"]:
            parts.append(f"{r['steps']} Schritte")
        if r["sleep_duration"]:
            parts.append(f"{r['sleep_duration']:.1f}h Schlaf")
        if r["hrv"]:
            parts.append(f"HRV {r['hrv']:.0f}")
        if r["resting_hr"]:
            parts.append(f"HR {r['resting_hr']}")
        if r["weight"]:
            parts.append(f"{r['weight']:.1f}kg")
        health_lines.append(" | ".join(parts))

    # Berechnete Metriken + Muster
    all_steps = [r["steps"] for r in health_rows if r["steps"]]
    all_hrv = [r["hrv"] for r in health_rows if r["hrv"]]
    all_sleep = [r["sleep_duration"] for r in health_rows if r["sleep_duration"]]
    weekday_steps = [r["steps"] for r in health_rows
                     if r["steps"] and date.fromisoformat(str(r["date"])).weekday() < 5]
    weekend_steps = [r["steps"] for r in health_rows
                     if r["steps"] and date.fromisoformat(str(r["date"])).weekday() >= 5]

    metrics = []
    if all_steps:
        avg = sum(all_steps) // len(all_steps)
        metrics.append(f"Ø Schritte: {avg}")
    if weekday_steps and weekend_steps:
        wd_avg = sum(weekday_steps) // len(weekday_steps)
        we_avg = sum(weekend_steps) // len(weekend_steps)
        diff_pct = round((wd_avg - we_avg) / max(1, wd_avg) * 100)
        metrics.append(f"Wochentag Ø: {wd_avg} / Wochenende Ø: {we_avg} Schritte ({diff_pct}% Unterschied)")
    if all_hrv:
        avg_hrv = sum(all_hrv) / len(all_hrv)
        min_hrv = min(all_hrv)
        metrics.append(f"Ø HRV: {avg_hrv:.0f} (min: {min_hrv:.0f}, max: {max(all_hrv):.0f})")
        # HRV-Trend
        if len(all_hrv) >= 4:
            recent_avg = sum(all_hrv[:3]) / 3
            older_avg = sum(all_hrv[3:6]) / min(3, len(all_hrv[3:6]))
            if recent_avg < older_avg * 0.85:
                metrics.append(f"⚠️ HRV-Abfall: zuletzt {recent_avg:.0f} vs. davor {older_avg:.0f}")
            elif recent_avg > older_avg * 1.1:
                metrics.append(f"✅ HRV-Erholung: zuletzt {recent_avg:.0f} vs. davor {older_avg:.0f}")
    if all_sleep:
        avg_sleep = sum(all_sleep) / len(all_sleep)
        metrics.append(f"Ø Schlaf: {avg_sleep:.1f}h")
        # Schlafvariabilität
        if len(all_sleep) >= 3:
            variance = max(all_sleep) - min(all_sleep)
            if variance > 2:
                metrics.append(f"⚠️ Hohe Schlafvariabilität: {min(all_sleep):.1f}h – {max(all_sleep):.1f}h")

    # Gewichtstrend
    weights = [(str(r["date"]), r["weight"]) for r in health_rows if r["weight"]]
    if len(weights) >= 2:
        first, last = weights[-1], weights[0]
        diff = last[1] - first[1]
        metrics.append(f"Gewicht: {first[1]}kg ({first[0]}) → {last[1]}kg ({last[0]}), Änderung: {diff:+.1f}kg")

    # Memories
    mem_str = "Keine"
    if lzg:
        try:
            mems = lzg.get_all()
            mem_str = "\n".join(f"- {m.content}" for m in mems[:10]) or "Keine"
        except Exception:
            pass

    # Open tasks & rejections
    open_rows = db.query(
        "SELECT title FROM tasks WHERE status NOT IN ('done','archived') ORDER BY created_at DESC LIMIT 15"
    )
    open_str = "\n".join(f"- {r['title']}" for r in open_rows) or "Keine"

    rejected_rows = db.query(
        "SELECT title, rejection_reason FROM tasks "
        "WHERE suggestion_status='rejected' AND rejection_reason IS NOT NULL "
        "ORDER BY created_at DESC LIMIT 10"
    )
    rej_str = "\n".join(f"- '{r['title'][:60]}' → {r['rejection_reason']}" for r in rejected_rows) or "Keine"

    # Direkt LLM aufrufen statt suggest_one, um bessere Kontrolle zu haben
    try:
        resp = await llm.chat(
            messages=[Message(role="user", content=INSIGHT_PROMPT.format(
                health_summary="\n".join(health_lines),
                metrics="\n".join(metrics),
                memories=mem_str,
                open_tasks=open_str,
                rejections=rej_str,
            ))],
            temperature=0.7,
            max_tokens=150,
        )
        parsed = _parse_insight_line(resp)
        if parsed is None:
            return False
        title, notes, assignee = parsed
    except Exception as e:
        log.warning(f"Insight-Generierung fehlgeschlagen: {e}")
        return False

    # Qualitäts- und Duplikatprüfung via suggest_one-Logik
    from domains.task_executor import EVALUATE_SUGGESTION_PROMPT
    try:
        verdict = await llm.chat(
            messages=[Message(role="user", content=EVALUATE_SUGGESTION_PROMPT.format(
                title=title, notes=notes or ""
            ))],
            temperature=0.1,
            max_tokens=5,
        )
        if not verdict.strip().upper().startswith("JA"):
            log.debug(f"Insight-Task verworfen: {title[:60]}")
            return False
    except Exception:
        pass

    # Dedup
    from core.dedup import is_duplicate_title
    recent = db.query("SELECT title FROM tasks WHERE status != 'archived' ORDER BY created_at DESC LIMIT 50")
    if is_duplicate_title(title, [r["title"] for r in recent]):
        log.debug(f"Insight-Task als Duplikat verworfen: {title[:60]}")
        return False

    db.execute(
        "INSERT INTO tasks (title, notes, assigned_to, suggestion_status, priority) VALUES (%s,%s,%s,'proposed','high')",
        (title, notes, assignee),
    )
    log.info(f"💡 Insight-Task erstellt: {title[:60]} ({assignee})")
    return True
