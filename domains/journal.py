"""
Journal-Domäne: Tagebucheinträge mit Stimmung/Energie.
"""
from datetime import date

from core import db


def add_entry(content: str, mood: int | None = None, energy: int | None = None,
              tags: list[str] | None = None, author: str = "timo",
              on_date: date | None = None) -> int:
    d = on_date or date.today()
    return db.insert_returning(
        """INSERT INTO journal_entries (date, mood, energy, content, tags, author)
           VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
        (d, mood, energy, content, tags or [], author),
    )


def recent_entries(limit: int = 30) -> list[dict]:
    return db.query("SELECT * FROM journal_entries ORDER BY date DESC, id DESC LIMIT %s", (limit,))


def mood_trend(days: int = 14) -> list[dict]:
    return db.query(
        """SELECT date, AVG(mood)::float mood, AVG(energy)::float energy
           FROM journal_entries WHERE date >= CURRENT_DATE - %s
           GROUP BY date ORDER BY date""",
        (days,),
    )
