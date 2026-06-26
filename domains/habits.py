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


def _streak_from_dates(done_dates: set) -> int:
    """Berechnet Streak aus einer Set von date-Objekten."""
    s = 0
    d = date.today()
    if d not in done_dates and (d - timedelta(days=1)) in done_dates:
        d = d - timedelta(days=1)
    while d in done_dates:
        s += 1
        d -= timedelta(days=1)
    return s


def habit_overview(days: int = 30) -> list[dict]:
    """Habits mit Streak + letzten N Tagen Logs – alle Logs in einem Query."""
    habits_list = list_habits()
    if not habits_list:
        return []

    ids = [h["id"] for h in habits_list]
    start = date.today() - timedelta(days=days - 1)

    # Einen Query für alle Habit-Logs + alle historischen Logs (für Streak-Berechnung)
    all_logs = db.query(
        "SELECT habit_id, date, done FROM habit_logs WHERE habit_id = ANY(%s) AND done=TRUE",
        (ids,),
    )

    # Gruppieren nach habit_id
    from collections import defaultdict
    logs_by_habit: dict[int, set] = defaultdict(set)
    for row in all_logs:
        d = row["date"] if isinstance(row["date"], date) else date.fromisoformat(str(row["date"]))
        logs_by_habit[row["habit_id"]].add(d)

    today = date.today()
    out = []
    for h in habits_list:
        all_dates = logs_by_habit[h["id"]]
        recent_dates = {d for d in all_dates if d >= start}
        done_dates_str = sorted(str(d) for d in recent_dates)
        today_done = today in recent_dates
        out.append({
            **h,
            "streak": _streak_from_dates(all_dates),
            "today_done": today_done,
            "done_dates": done_dates_str,
            "done_count": len(recent_dates),
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


# ── Sport-Habit Auto-Logging (Trainingseinheit erledigt → Habit abhaken) ──────

SPORT_HABIT_KEYWORDS = ["gym", "jog", "sport", "training", "workout"]


def pick_sport_habit(habits: list[dict]) -> dict | None:
    """Wählt aus einer Habit-Liste den 'Sport'-Habit per Keyword (Prioritätsreihenfolge)."""
    for kw in SPORT_HABIT_KEYWORDS:
        for h in habits:
            if kw in (h.get("name") or "").lower():
                return h
    return None


def find_sport_habit() -> dict | None:
    """Aktiver Sport-Habit aus der DB (z.B. 'Gym/Joggen')."""
    return pick_sport_habit(list_habits())


def log_sport_done(on_date: date | None = None) -> bool:
    """Hakt den Sport-Habit für den Tag ab, falls vorhanden. True wenn geloggt."""
    h = find_sport_habit()
    if not h:
        return False
    log_habit(h["id"], on_date=on_date, done=True)
    return True
