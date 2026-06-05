"""
Ziele-Domäne: Ziele mit Fortschritt.
"""
from datetime import date

from core import db


def list_goals(status: str = "active") -> list[dict]:
    if status == "all":
        return db.query("SELECT * FROM goals ORDER BY created_at DESC")
    return db.query("SELECT * FROM goals WHERE status=%s ORDER BY created_at DESC", (status,))


def create_goal(title: str, category: str = "general", target_value: float | None = None,
                unit: str | None = None, deadline: date | None = None,
                notes: str | None = None) -> int:
    return db.insert_returning(
        """INSERT INTO goals (title, category, target_value, unit, deadline, notes)
           VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
        (title, category, target_value, unit, deadline, notes),
    )


def update_progress(goal_id: int, current_value: float | None = None,
                    progress_pct: int | None = None, status: str | None = None) -> None:
    sets, params = [], []
    if current_value is not None:
        sets.append("current_value=%s"); params.append(current_value)
    if progress_pct is not None:
        sets.append("progress_pct=%s"); params.append(max(0, min(100, progress_pct)))
    if status is not None:
        sets.append("status=%s"); params.append(status)
    if not sets:
        return
    sets.append("updated_at=NOW()")
    params.append(goal_id)
    db.execute(f"UPDATE goals SET {', '.join(sets)} WHERE id=%s", tuple(params))


def delete_goal(goal_id: int) -> None:
    db.execute("DELETE FROM goals WHERE id=%s", (goal_id,))


def find_goal(query: str) -> dict | None:
    rows = db.query(
        "SELECT * FROM goals WHERE LOWER(title) LIKE LOWER(%s) AND status='active' LIMIT 1",
        (f"%{query}%",),
    )
    return rows[0] if rows else None
