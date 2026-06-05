"""
Reminder-System – Jarvis erinnert Timo zu bestimmten Zeiten.
Gespeichert in der jarvis DB, wird im Denkzyklus geprüft.
"""
import logging
from dataclasses import dataclass
from datetime import datetime

import psycopg2
import psycopg2.extras

import config

log = logging.getLogger(__name__)


@dataclass
class Reminder:
    id: int
    text: str
    remind_at: datetime
    sent: bool


class ReminderStore:
    def __init__(self):
        self._conn = None

    def _get_conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(config.DATABASE_URL)
        return self._conn

    def setup(self) -> None:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id         SERIAL PRIMARY KEY,
                    text       TEXT NOT NULL,
                    remind_at  TIMESTAMPTZ NOT NULL,
                    sent       BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            conn.commit()

    def add(self, text: str, remind_at: datetime) -> int:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO reminders (text, remind_at) VALUES (%s, %s) RETURNING id",
                (text, remind_at),
            )
            rid = cur.fetchone()[0]
            conn.commit()
        log.info(f"⏰ Reminder gesetzt: '{text}' um {remind_at.strftime('%d.%m. %H:%M')}")
        return rid

    def get_due(self) -> list[Reminder]:
        """Gibt fällige Reminders zurück und markiert sie als gesendet."""
        conn = self._get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("""
                SELECT id, text, remind_at, sent FROM reminders
                WHERE remind_at <= NOW() AND sent = FALSE
                ORDER BY remind_at ASC
            """)
            rows = cur.fetchall()
            if rows:
                ids = [r["id"] for r in rows]
                cur.execute(
                    "UPDATE reminders SET sent = TRUE WHERE id = ANY(%s)", (ids,)
                )
                conn.commit()
        return [Reminder(id=r["id"], text=r["text"],
                         remind_at=r["remind_at"], sent=r["sent"]) for r in rows]

    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()
            self._conn = None
