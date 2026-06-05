"""
Dashboard-Integration – Jarvis liest aus und schreibt in die aidashboard DB.
Read:  HealthData, CalendarEvent, Task
Write: Task (erstellen, abhaken)
"""
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

import psycopg2
import psycopg2.extras

log = logging.getLogger(__name__)

DASHBOARD_DB = "postgresql://localhost:5432/aidashboard"


@dataclass
class HealthSummary:
    date: date
    steps: Optional[int]
    active_calories: Optional[int]
    exercise_minutes: Optional[int]
    sleep_duration: Optional[float]
    sleep_deep: Optional[float]
    resting_hr: Optional[int]
    hrv: Optional[float]
    weight: Optional[float]

    def format(self) -> str:
        parts = [f"📅 {self.date.strftime('%d.%m.%Y')}"]
        if self.steps:          parts.append(f"👟 {self.steps:,} Schritte")
        if self.active_calories:parts.append(f"🔥 {self.active_calories} kcal aktiv")
        if self.exercise_minutes:parts.append(f"⏱ {self.exercise_minutes} Min Sport")
        if self.sleep_duration: parts.append(f"😴 {self.sleep_duration:.1f}h Schlaf")
        if self.sleep_deep:     parts.append(f"   Tiefschlaf: {self.sleep_deep:.1f}h")
        if self.resting_hr:     parts.append(f"❤️ {self.resting_hr} bpm Ruhepuls")
        if self.hrv:            parts.append(f"📊 HRV: {self.hrv:.0f}")
        if self.weight:         parts.append(f"⚖️ {self.weight:.1f} kg")
        return " | ".join(parts)


@dataclass
class TaskItem:
    id: str
    title: str
    status: str
    priority: str
    due_date: Optional[datetime]
    notes: Optional[str]

    def format(self) -> str:
        icon = {"todo": "⬜", "in_progress": "🔄", "done": "✅"}.get(self.status, "⬜")
        prio = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(self.priority, "")
        due = f" (fällig: {self.due_date.strftime('%d.%m')})" if self.due_date else ""
        return f"{icon} {prio} {self.title}{due}"


@dataclass
class CalendarItem:
    title: str
    start: datetime
    end: datetime
    all_day: bool
    calendar: Optional[str]
    location: Optional[str]

    def format(self) -> str:
        if self.all_day:
            time_str = self.start.strftime("%d.%m.")
        else:
            time_str = self.start.strftime("%d.%m. %H:%M")
        loc = f" @ {self.location}" if self.location else ""
        cal = f" [{self.calendar}]" if self.calendar else ""
        return f"📅 {time_str} – {self.title}{loc}{cal}"


class DashboardReader:
    """Liest Daten aus der aidashboard DB für Jarvis-Kontext."""

    def __init__(self):
        self._conn = None

    def _get_conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(DASHBOARD_DB)
            self._conn.autocommit = False
        return self._conn

    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()
            self._conn = None

    # ── Health ──────────────────────────────────────────────────────────────

    def get_recent_health(self, days: int = 3) -> list[HealthSummary]:
        """Letzte N Tage Gesundheitsdaten."""
        conn = self._get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("""
                SELECT date, steps, "activeCalories", "exerciseMinutes",
                       "sleepDuration", "sleepDeep", "restingHR", hrv, weight
                FROM "HealthData"
                WHERE date >= CURRENT_DATE - %s
                ORDER BY date DESC
            """, (days,))
            rows = cur.fetchall()
        return [HealthSummary(
            date=r["date"],
            steps=r["steps"],
            active_calories=r["activeCalories"],
            exercise_minutes=r["exerciseMinutes"],
            sleep_duration=r["sleepDuration"],
            sleep_deep=r["sleepDeep"],
            resting_hr=r["restingHR"],
            hrv=r["hrv"],
            weight=r["weight"],
        ) for r in rows]

    # ── Tasks ────────────────────────────────────────────────────────────────

    def get_open_tasks(self, limit: int = 10) -> list[TaskItem]:
        """Offene und laufende Tasks."""
        conn = self._get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("""
                SELECT id, title, status, priority, "dueDate", notes
                FROM "Task"
                WHERE status IN ('todo', 'in_progress')
                ORDER BY
                    CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                    "dueDate" ASC NULLS LAST
                LIMIT %s
            """, (limit,))
            rows = cur.fetchall()
        return [TaskItem(
            id=r["id"], title=r["title"], status=r["status"],
            priority=r["priority"], due_date=r["dueDate"], notes=r["notes"],
        ) for r in rows]

    def create_task(self, title: str, priority: str = "medium",
                    due_date: Optional[datetime] = None, notes: Optional[str] = None) -> str:
        """Erstellt einen neuen Task. Gibt ID zurück."""
        conn = self._get_conn()
        task_id = str(uuid.uuid4())
        now = datetime.now()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO "Task" (id, title, status, priority, "dueDate", notes, "createdAt", "updatedAt")
                VALUES (%s, %s, 'todo', %s, %s, %s, %s, %s)
            """, (task_id, title, priority, due_date, notes, now, now))
            conn.commit()
        log.info(f"✅ Task erstellt: {title}")
        return task_id

    def complete_task(self, task_id: str) -> bool:
        """Markiert Task als erledigt. Gibt True zurück wenn gefunden."""
        conn = self._get_conn()
        now = datetime.now()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE "Task"
                SET status = 'done', "completedAt" = %s, "updatedAt" = %s
                WHERE id = %s AND status != 'done'
            """, (now, now, task_id))
            updated = cur.rowcount
            conn.commit()
        if updated:
            log.info(f"✅ Task abgehakt: {task_id}")
        return updated > 0

    def find_task(self, title_query: str) -> Optional[TaskItem]:
        """Findet Task anhand eines Titels (case-insensitive, partial match)."""
        conn = self._get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("""
                SELECT id, title, status, priority, "dueDate", notes
                FROM "Task"
                WHERE LOWER(title) LIKE LOWER(%s) AND status != 'done'
                LIMIT 1
            """, (f"%{title_query}%",))
            row = cur.fetchone()
        if not row:
            return None
        return TaskItem(
            id=row["id"], title=row["title"], status=row["status"],
            priority=row["priority"], due_date=row["dueDate"], notes=row["notes"],
        )

    # ── Kalender ─────────────────────────────────────────────────────────────

    def create_event(self, title: str, start, end=None, location: str | None = None,
                     notes: str | None = None, all_day: bool = False) -> str:
        """Erstellt einen Kalendereintrag (Kalender 'Jarvis')."""
        import uuid as _uuid
        from datetime import timedelta
        if end is None:
            end = start + timedelta(hours=1)
        uid = f"jarvis-{_uuid.uuid4()}"
        eid = str(_uuid.uuid4())
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO "CalendarEvent" (id, uid, title, start, "end", "allDay", calendar, location, notes, synced)
                VALUES (%s,%s,%s,%s,%s,%s,'Jarvis',%s,%s, CURRENT_TIMESTAMP)
            """, (eid, uid, title, start, end, all_day, location, notes))
            conn.commit()
        return eid

    def get_upcoming_events(self, days: int = 7) -> list[CalendarItem]:
        """Termine der nächsten N Tage."""
        conn = self._get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("""
                SELECT title, start, "end", "allDay", calendar, location
                FROM "CalendarEvent"
                WHERE start >= NOW() AND start <= NOW() + INTERVAL '%s days'
                ORDER BY start ASC
                LIMIT 15
            """ % days)
            rows = cur.fetchall()
        return [CalendarItem(
            title=r["title"], start=r["start"], end=r["end"],
            all_day=r["allDay"], calendar=r["calendar"], location=r["location"],
        ) for r in rows]

    # ── Kontext für System-Prompt ─────────────────────────────────────────────

    def format_for_context(self) -> str:
        """Kompakter Kontext-Block für Jarvis System-Prompt."""
        parts = []

        try:
            health = self.get_recent_health(days=2)
            if health:
                parts.append("### Gesundheit (letzte Tage)")
                for h in health:
                    parts.append(h.format())
        except Exception as e:
            log.debug(f"Health-Kontext fehlgeschlagen: {e}")

        # Tasks kommen jetzt aus dem jarvis-nativen System (separat im Prompt)

        try:
            events = self.get_upcoming_events(days=3)
            if events:
                parts.append("\n### Kalender (nächste 3 Tage)")
                for e in events:
                    parts.append(e.format())
        except Exception as e:
            log.debug(f"Kalender-Kontext fehlgeschlagen: {e}")

        return "\n".join(parts) if parts else "Keine Dashboard-Daten verfügbar."
