"""
Insight Engine – generiert sinnvolle Aufgaben aus DB-Daten.

Analysiert Health, Goals, Tasks und Memories und erstellt proaktiv
Aufgaben die echten Mehrwert für Timo liefern.
"""
import json
import logging
from datetime import date, timedelta

from core import db
from llm.base import LLMProvider, Message

log = logging.getLogger(__name__)

INSIGHT_PROMPT = """Du bist Alfred, Timos persönlicher KI-Assistent.

Analysiere diese Daten und erstelle EINE sinnvolle, konkrete Aufgabe.

## Aktuelle Gesundheitsdaten (letzte 14 Tage):
{health_summary}

## Erinnerungen über Timo:
{memories}

## Aktuell offene Aufgaben (nicht doppeln):
{open_tasks}

## Kürzlich abgelehnte Vorschläge (NIEMALS ähnliches):
{rejections}

## Regeln:
- Genau EINE Aufgabe, direkt aus den Daten abgeleitet
- Klar actionable, nicht zu abstrakt
- Nicht ähnlich wie offene oder abgelehnte Tasks
- Standard: ALFRED übernimmt, nur USER wenn physische Präsenz nötig
- Keine Python-Skripte oder technische Analysen – lieber konkrete Pläne, Texte, Recherchen

Antworte im Format:
TITEL | BEGRÜNDUNG | ALFRED_ODER_USER"""


async def generate_insight_task(llm: LLMProvider, lzg=None) -> bool:
    """Analysiert DB-Daten und erstellt eine sinnvolle Aufgabe."""
    from domains.task_executor import suggest_one

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

    # Berechnete Metriken
    all_steps = [r["steps"] for r in health_rows if r["steps"]]
    all_hrv = [r["hrv"] for r in health_rows if r["hrv"]]
    all_sleep = [r["sleep_duration"] for r in health_rows if r["sleep_duration"]]
    weekday_steps = [r["steps"] for r in health_rows
                     if r["steps"] and date.fromisoformat(str(r["date"])).weekday() < 5]
    weekend_steps = [r["steps"] for r in health_rows
                     if r["steps"] and date.fromisoformat(str(r["date"])).weekday() >= 5]

    metrics = []
    if all_steps:
        metrics.append(f"Ø Schritte: {sum(all_steps)//len(all_steps)}")
    if weekday_steps and weekend_steps:
        wd_avg = sum(weekday_steps) // len(weekday_steps)
        we_avg = sum(weekend_steps) // len(weekend_steps)
        metrics.append(f"Wochentag Ø: {wd_avg} / Wochenende Ø: {we_avg} Schritte")
    if all_hrv:
        metrics.append(f"Ø HRV: {sum(all_hrv)/len(all_hrv):.0f} (min: {min(all_hrv):.0f}, max: {max(all_hrv):.0f})")
    if all_sleep:
        metrics.append(f"Ø Schlaf: {sum(all_sleep)/len(all_sleep):.1f}h")

    health_summary = "\n".join(health_lines) + "\n\nMetriken:\n" + "\n".join(metrics)

    # Trigger für suggest_one bauen
    trigger = f"DB-Insight Analyse:\n{health_summary}"

    # suggest_one verwenden (hat bereits Dedup + Qualitätsprüfung)
    result = await suggest_one(trigger, llm, lzg)
    if result:
        log.info("💡 Insight-Task generiert")
    return result
