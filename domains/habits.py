"""
Habits-Domäne: CRUD, Logging, Streaks. Datenschicht + Dashboard-Helfer.
"""
from datetime import date, timedelta

from core import db


def list_habits(active_only: bool = True) -> list[dict]:
    sql = "SELECT * FROM habits"
    if active_only:
        sql += " WHERE active = TRUE"
    sql += " ORDER BY sort_order, id"
    return db.query(sql)


def create_habit(name: str, emoji: str = "✅", cadence: str = "daily",
                 target_per_week: int = 7, color: str = "#0ea5e9",
                 category: str = "day") -> int:
    return db.insert_returning(
        """INSERT INTO habits (name, emoji, cadence, target_per_week, color, category)
           VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
        (name, emoji, cadence, target_per_week, color, category),
    )


def delete_habit(habit_id: int) -> None:
    db.execute("UPDATE habits SET active = FALSE WHERE id = %s", (habit_id,))


def log_habit(habit_id: int, on_date: date | None = None, done: bool = True,
              note: str | None = None) -> None:
    d = on_date or date.today()
    db.execute(
        """INSERT INTO habit_logs (habit_id, date, done, note)
           VALUES (%s,%s,%s,%s)
           ON CONFLICT (habit_id, date) DO UPDATE SET done = EXCLUDED.done, note = EXCLUDED.note""",
        (habit_id, d, done, note),
    )


def streak(habit_id: int) -> int:
    rows = db.query(
        "SELECT date FROM habit_logs WHERE habit_id=%s AND done=TRUE ORDER BY date DESC",
        (habit_id,),
    )
    if not rows:
        return 0
    dates = {r["date"] for r in rows}
    s = 0
    d = date.today()
    # Erlaube heute oder gestern als Start
    if d not in dates and (d - timedelta(days=1)) in dates:
        d = d - timedelta(days=1)
    while d in dates:
        s += 1
        d -= timedelta(days=1)
    return s


def habit_overview(days: int = 30) -> list[dict]:
    """Habits mit Streak + letzten N Tagen Logs (für Heatmap)."""
    out = []
    start = date.today() - timedelta(days=days - 1)
    for h in list_habits():
        logs = db.query(
            "SELECT date, done FROM habit_logs WHERE habit_id=%s AND date >= %s",
            (h["id"], start),
        )
        done_dates = {str(l["date"]) for l in logs if l["done"]}
        today_done = str(date.today()) in done_dates
        out.append({
            **h,
            "streak": streak(h["id"]),
            "today_done": today_done,
            "done_dates": sorted(done_dates),
            "done_count": len(done_dates),
        })
    return out


def commit_history(days: int = 30) -> list[dict]:
    """Pro Tag: wieviel % der aktiven Gewohnheiten erledigt wurden (Commit-Graph)."""
    active = list_habits()
    n = len(active)
    if n == 0:
        return []
    ids = tuple(h["id"] for h in active)
    rows = db.query(
        """SELECT date, COUNT(*) c FROM habit_logs
           WHERE done=TRUE AND habit_id = ANY(%s) AND date >= CURRENT_DATE - %s
           GROUP BY date""",
        (list(ids), days),
    )
    by_date = {str(r["date"]): r["c"] for r in rows}
    out = []
    for i in range(days - 1, -1, -1):
        d = (date.today() - timedelta(days=i))
        ds = str(d)
        done = by_date.get(ds, 0)
        out.append({"date": ds, "done": done, "total": n,
                    "pct": round(done / n * 100) if n else 0})
    return out


def unlog_habit(habit_id: int, on_date: date | None = None) -> None:
    d = on_date or date.today()
    db.execute("DELETE FROM habit_logs WHERE habit_id=%s AND date=%s", (habit_id, d))


def find_habit(query: str) -> dict | None:
    rows = db.query(
        "SELECT * FROM habits WHERE active=TRUE AND LOWER(name) LIKE LOWER(%s) LIMIT 1",
        (f"%{query}%",),
    )
    return rows[0] if rows else None
