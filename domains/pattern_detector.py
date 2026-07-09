"""
Pattern Detector – erkennt wiederkehrende Verhaltensmuster aus Gesundheits-,
Trainings-, Gewohnheits- und Kalenderdaten und speichert sie als Langzeitgedächtnisse.

Läuft täglich im Idle-Loop. Überschreibt bestehende Pattern-Memories statt neue
zu duplizieren (confidence ≥ 0.85 = etabliertes Muster).
"""
import logging
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Optional

from core import db

log = logging.getLogger(__name__)

# Minimum Datenpunkte damit ein Muster als valide gilt
MIN_SAMPLES = 4


# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

_WD_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


def _weekday_name(wd: int) -> str:
    return _WD_DE[wd]


def _avg(vals: list) -> Optional[float]:
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


# ── Analyse-Funktionen ─────────────────────────────────────────────────────────

def _workout_patterns(days: int = 60) -> list[str]:
    """Analysiert Trainingsfrequenz und bevorzugte Wochentage."""
    since = date.today() - timedelta(days=days)
    rows = db.query(
        "SELECT date, type FROM workouts WHERE date >= %s ORDER BY date",
        (since,),
    )
    if len(rows) < MIN_SAMPLES:
        return []

    patterns = []

    # Wochentag-Häufigkeit
    wd_counts = Counter(r["date"].weekday() for r in rows)
    top_days = [d for d, c in wd_counts.most_common(3) if c >= 2]
    if top_days:
        day_names = " und ".join(_weekday_name(d) for d in sorted(top_days))
        patterns.append(f"Timo trainiert am häufigsten {day_names}.")

    # Durchschnittliche Trainings pro Woche
    weeks = max(1, days // 7)
    per_week = round(len(rows) / weeks, 1)
    if per_week >= 1:
        patterns.append(f"Timo trainiert durchschnittlich {per_week}x pro Woche.")

    # Bevorzugter Trainingstyp
    type_counts = Counter(r["type"] for r in rows if r.get("type"))
    if type_counts:
        top_type = type_counts.most_common(1)[0][0]
        patterns.append(f"Timos bevorzugter Trainingstyp ist {top_type}.")

    return patterns


def _sleep_patterns(days: int = 30) -> list[str]:
    """Analysiert Schlafmuster."""
    since = date.today() - timedelta(days=days)
    rows = db.query(
        "SELECT date, sleep_duration, sleep_deep FROM health_data "
        "WHERE date >= %s AND sleep_duration IS NOT NULL ORDER BY date",
        (since,),
    )
    if len(rows) < MIN_SAMPLES:
        return []

    patterns = []
    avg_sleep = _avg([r["sleep_duration"] for r in rows])
    if avg_sleep:
        patterns.append(f"Timo schläft durchschnittlich {avg_sleep:.1f} Stunden pro Nacht.")
        if avg_sleep < 6.5:
            patterns.append("Timo schläft regelmäßig unter 6.5h – Schlafdefizit möglich.")
        elif avg_sleep >= 7.5:
            patterns.append("Timos Schlafqualität ist gut (≥7.5h Durchschnitt).")

    # Wochentag-Unterschiede (Wochenende vs. Werktag)
    wd_sleep = defaultdict(list)
    for r in rows:
        wd_sleep[r["date"].weekday()].append(r["sleep_duration"])

    weekday_avg = _avg([v for wd in range(5) for v in wd_sleep.get(wd, [])])
    weekend_avg = _avg([v for wd in [5, 6] for v in wd_sleep.get(wd, [])])
    if weekday_avg and weekend_avg and abs(weekend_avg - weekday_avg) >= 0.7:
        diff = weekend_avg - weekday_avg
        dir_ = "mehr" if diff > 0 else "weniger"
        patterns.append(
            f"Timo schläft am Wochenende {abs(diff):.1f}h {dir_} als unter der Woche."
        )

    return patterns


def _step_patterns(days: int = 30) -> list[str]:
    """Analysiert Schritt-Muster."""
    since = date.today() - timedelta(days=days)
    rows = db.query(
        "SELECT date, steps FROM health_data WHERE date >= %s AND steps IS NOT NULL ORDER BY date",
        (since,),
    )
    if len(rows) < MIN_SAMPLES:
        return []

    patterns = []
    avg_steps = _avg([r["steps"] for r in rows])
    if avg_steps:
        patterns.append(f"Timo geht durchschnittlich {int(avg_steps):,} Schritte pro Tag.".replace(",", "."))

    # Wochenend-Muster
    wd_steps = defaultdict(list)
    for r in rows:
        wd_steps[r["date"].weekday()].append(r["steps"])

    weekday_avg = _avg([v for wd in range(5) for v in wd_steps.get(wd, [])])
    weekend_avg = _avg([v for wd in [5, 6] for v in wd_steps.get(wd, [])])
    if weekday_avg and weekend_avg:
        diff_pct = (weekend_avg - weekday_avg) / weekday_avg * 100
        if abs(diff_pct) >= 20:
            dir_ = "mehr" if diff_pct > 0 else "weniger"
            patterns.append(
                f"Timo ist am Wochenende {abs(int(diff_pct))}% {dir_} aktiv als unter der Woche."
            )

    return patterns


def _habit_patterns(days: int = 30) -> list[str]:
    """Analysiert Gewohnheits-Streaks und Konsistenz."""
    since = date.today() - timedelta(days=days)
    rows = db.query(
        "SELECT h.name, h.emoji, h.created_at, COUNT(hl.id) as completions "
        "FROM habits h LEFT JOIN habit_logs hl ON h.id = hl.habit_id "
        "AND hl.date >= %s "
        "WHERE h.active = true GROUP BY h.id, h.name, h.emoji, h.created_at",
        (since,),
    )
    patterns = []
    for r in rows:
        # Konsistenz nur gegen die Tage rechnen, seit denen die Habit tatsächlich existiert
        # (sonst wirkt eine brandneue Habit künstlich "inkonsequent")
        tracked_days = min(days, (date.today() - r["created_at"].date()).days + 1) if r.get("created_at") else days
        tracked_days = max(tracked_days, 1)
        rate = r["completions"] / tracked_days * 100
        name = r["name"]
        emoji = r["emoji"] or "✅"
        if rate >= 80:
            patterns.append(f"Timo hält {emoji} {name} sehr konsequent durch ({int(rate)}% der Tage).")
        elif rate >= 50:
            patterns.append(f"Timo macht {emoji} {name} regelmäßig ({int(rate)}% der Tage).")
        elif rate < 20 and r["completions"] > 0:
            patterns.append(f"Timo hat Schwierigkeiten mit {emoji} {name} (nur {int(rate)}% Konsistenz).")
    return patterns


def _resting_hr_trend(days: int = 30) -> list[str]:
    """Erkennt Trends beim Ruhepuls."""
    since = date.today() - timedelta(days=days)
    rows = db.query(
        "SELECT date, resting_hr FROM health_data "
        "WHERE date >= %s AND resting_hr IS NOT NULL ORDER BY date",
        (since,),
    )
    if len(rows) < MIN_SAMPLES:
        return []

    avg_hr = _avg([r["resting_hr"] for r in rows])
    patterns = []
    if avg_hr:
        if avg_hr <= 55:
            patterns.append(f"Timos Ruhepuls ist sehr niedrig ({int(avg_hr)} bpm) – gute Fitness.")
        elif avg_hr <= 65:
            patterns.append(f"Timos Ruhepuls liegt bei {int(avg_hr)} bpm (guter Bereich).")
        else:
            patterns.append(f"Timos Ruhepuls ist erhöht ({int(avg_hr)} bpm) – könnte auf Stress oder Übertraining hinweisen.")

    # Trend: erste Hälfte vs. zweite Hälfte
    mid = len(rows) // 2
    early = _avg([r["resting_hr"] for r in rows[:mid]])
    late  = _avg([r["resting_hr"] for r in rows[mid:]])
    if early and late:
        diff = late - early
        if abs(diff) >= 3:
            dir_ = "gesunken" if diff < 0 else "gestiegen"
            patterns.append(
                f"Timos Ruhepuls ist in den letzten {days} Tagen um {abs(int(diff))} bpm {dir_}."
            )

    return patterns


# ── Haupt-API ──────────────────────────────────────────────────────────────────

def detect_all(days: int = 30) -> list[str]:
    """
    Führt alle Musteranalysen durch.
    Gibt eine Liste von Muster-Strings zurück.
    """
    patterns = []
    try:
        patterns += _workout_patterns(days=60)
    except Exception as e:
        log.debug(f"Workout patterns: {e}")
    try:
        patterns += _sleep_patterns(days=days)
    except Exception as e:
        log.debug(f"Sleep patterns: {e}")
    try:
        patterns += _step_patterns(days=days)
    except Exception as e:
        log.debug(f"Step patterns: {e}")
    try:
        patterns += _habit_patterns(days=days)
    except Exception as e:
        log.debug(f"Habit patterns: {e}")
    try:
        patterns += _resting_hr_trend(days=days)
    except Exception as e:
        log.debug(f"HR trend: {e}")

    log.info(f"Pattern Detector: {len(patterns)} Muster erkannt")
    return patterns


async def update_memories(lzg, llm) -> int:
    """
    Erkennt Muster und speichert/aktualisiert sie im Langzeitgedächtnis.
    Gibt Anzahl neu gespeicherter Muster zurück.
    """
    patterns = detect_all()
    if not patterns:
        return 0

    saved = 0
    for pattern in patterns:
        try:
            emb = await llm.embed(pattern)
            # Prüfe ob ähnliches Muster schon existiert (Threshold 0.25 für Pattern-Updates)
            similar = lzg.find_similar(emb, threshold=0.25)
            if similar:
                # Vorhandenes Muster: Confidence stärken (Content-Update über DB direkt)
                existing = similar[0][0]
                db.execute(
                    "UPDATE memories SET content = %s, confidence = 0.88, "
                    "last_recalled = NOW() WHERE id = %s",
                    (pattern, existing.id),
                )
                lzg.update_confidence(existing.id, 0.88)
            else:
                lzg.save(content=pattern, embedding=emb,
                         category="pattern", confidence=0.85)
                saved += 1
        except Exception as e:
            log.debug(f"Pattern-Memory Update: {e}")

    log.info(f"Pattern Detector: {saved} neue Muster gespeichert")
    return saved
