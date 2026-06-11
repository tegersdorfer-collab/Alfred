"""
Journal-Domäne: Tagebucheinträge mit Stimmung/Energie.
"""
import json
from datetime import date

from core import db


def add_entry(content: str, mood: int | None = None, energy: int | None = None,
              tags: list[str] | None = None, author: str = "timo",
              on_date: date | None = None,
              prompts_answers: list[dict] | None = None) -> int:
    d = on_date or date.today()
    pa = json.dumps(prompts_answers, ensure_ascii=False) if prompts_answers else None
    return db.insert_returning(
        """INSERT INTO journal_entries (date, mood, energy, content, tags, author, prompts_answers)
           VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb) RETURNING id""",
        (d, mood, energy, content, tags or [], author, pa),
    )


def today_entry() -> dict | None:
    rows = db.query(
        "SELECT * FROM journal_entries WHERE date = CURRENT_DATE ORDER BY id DESC LIMIT 1"
    )
    return rows[0] if rows else None


def recent_entries(limit: int = 30) -> list[dict]:
    return db.query("SELECT * FROM journal_entries ORDER BY date DESC, id DESC LIMIT %s", (limit,))


def mood_trend(days: int = 14) -> list[dict]:
    return db.query(
        """SELECT date, AVG(mood)::float mood, AVG(energy)::float energy
           FROM journal_entries WHERE date >= CURRENT_DATE - %s
           GROUP BY date ORDER BY date""",
        (days,),
    )
