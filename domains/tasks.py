"""
Reiches Task-System (jarvis-nativ).
Arten: task | project | checklist. Unteraufgaben via parent_id. Fortschritt %. Archiv.
"""
from datetime import datetime

from core import db


def create_task(title: str, kind: str = "task", priority: str = "medium",
                due: datetime | None = None, notes: str | None = None,
                parent_id: int | None = None) -> int:
    return db.insert_returning(
        """INSERT INTO tasks (title, kind, priority, due, notes, parent_id)
           VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
        (title, kind, priority, due, notes, parent_id),
    )


def list_tasks(status: str = "open", include_sub: bool = True) -> list[dict]:
    """status: open (todo+in_progress) | done | archived | all"""
    if status == "open":
        where = "status IN ('todo','in_progress') AND (suggestion_status IS NULL OR suggestion_status != 'proposed')"
    elif status == "all":
        where = "status != 'archived'"
    else:
        where = "status = %s"
    params = () if status in ("open", "all") else (status,)
    rows = db.query(
        f"""SELECT * FROM tasks WHERE {where} AND parent_id IS NULL
            ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                     due ASC NULLS LAST, created_at DESC""",
        params,
    )
    if include_sub:
        for t in rows:
            t["subtasks"] = db.query(
                "SELECT * FROM tasks WHERE parent_id=%s ORDER BY sort_order, id", (t["id"],)
            )
            t["progress_pct"] = _computed_progress(t)
    return rows


def _computed_progress(task: dict) -> int:
    subs = task.get("subtasks") or []
    if subs:
        done = sum(1 for s in subs if s["status"] == "done")
        return round(done / len(subs) * 100)
    return task.get("progress_pct") or (100 if task["status"] == "done" else 0)


def complete_task(task_id: int) -> None:
    db.execute(
        "UPDATE tasks SET status='done', progress_pct=100, completed_at=NOW() WHERE id=%s",
        (task_id,),
    )


def set_status(task_id: int, status: str) -> None:
    if status == "done":
        complete_task(task_id)
    else:
        db.execute("UPDATE tasks SET status=%s WHERE id=%s", (status, task_id))


def set_progress(task_id: int, pct: int) -> None:
    pct = max(0, min(100, pct))
    status = "done" if pct >= 100 else "in_progress"
    db.execute(
        "UPDATE tasks SET progress_pct=%s, status=%s, completed_at=%s WHERE id=%s",
        (pct, status, datetime.now() if pct >= 100 else None, task_id),
    )


def archive_task(task_id: int) -> None:
    db.execute("UPDATE tasks SET status='archived' WHERE id=%s", (task_id,))


def delete_task(task_id: int) -> None:
    db.execute("DELETE FROM tasks WHERE id=%s", (task_id,))


def find_task(query: str) -> dict | None:
    rows = db.query(
        """SELECT * FROM tasks WHERE LOWER(title) LIKE LOWER(%s)
           AND status IN ('todo','in_progress') ORDER BY created_at DESC LIMIT 1""",
        (f"%{query}%",),
    )
    return rows[0] if rows else None


def open_count() -> int:
    r = db.query_one("SELECT COUNT(*) c FROM tasks WHERE status IN ('todo','in_progress')")
    return r["c"] if r else 0


def context_summary(limit: int = 8) -> str:
    rows = list_tasks("open")[:limit]
    if not rows:
        return ""
    out = []
    pr = {"high": "🔴", "medium": "🟡", "low": "🟢"}
    for t in rows:
        line = f"{pr.get(t['priority'],'')} {t['title']}"
        if t.get("subtasks"):
            line += f" ({t['progress_pct']}%, {len(t['subtasks'])} Unteraufgaben)"
        if t.get("due"):
            line += f" [fällig {t['due'].strftime('%d.%m')}]"
        out.append(line)
    return "\n".join(out)
