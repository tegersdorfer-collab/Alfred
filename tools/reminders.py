"""
Reminder-System – Jarvis erinnert Timo zu bestimmten Zeiten.
Gespeichert in der jarvis DB, wird im Denkzyklus geprüft.
Nutzt den zentralen Connection-Pool (core.db) – keine eigene Connection mehr.
"""
import logging
from dataclasses import dataclass
from datetime import datetime

from core import db as _db

log = logging.getLogger(__name__)


@dataclass
class Reminder:
    id: int
    text: str
    remind_at: datetime
    sent: bool


class ReminderStore:

    def setup(self) -> None:
        with _db.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id         SERIAL PRIMARY KEY,
                    text       TEXT NOT NULL,
                    remind_at  TIMESTAMPTZ NOT NULL,
                    sent       BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)

    def add(self, text: str, remind_at: datetime) -> int:
        with _db.cursor() as cur:
            cur.execute(
                "INSERT INTO reminders (text, remind_at) VALUES (%s, %s) RETURNING id",
                (text, remind_at),
            )
            rid = cur.fetchone()["id"]
        log.info(f"⏰ Reminder gesetzt: '{text}' um {remind_at.strftime('%d.%m. %H:%M')}")
        return rid

    def get_due(self) -> list[Reminder]:
        """Gibt fällige Reminders zurück und markiert sie als gesendet."""
        rows = _db.query(
            "SELECT id, text, remind_at, sent FROM reminders "
            "WHERE remind_at <= NOW() AND sent = FALSE "
            "ORDER BY remind_at ASC"
        )
        if rows:
            ids = [r["id"] for r in rows]
            _db.execute(
                "UPDATE reminders SET sent = TRUE WHERE id = ANY(%s)", (ids,)
            )
        return [Reminder(id=r["id"], text=r["text"],
                         remind_at=r["remind_at"], sent=r["sent"]) for r in rows]

    def next_due_seconds(self) -> float | None:
        """Sekunden bis zum nächsten fälligen Reminder (oder None)."""
        row = _db.query_one(
            "SELECT EXTRACT(EPOCH FROM (MIN(remind_at) - NOW())) AS secs "
            "FROM reminders WHERE sent = FALSE AND remind_at > NOW()"
        )
        return float(row["secs"]) if row and row.get("secs") is not None else None

    def close(self) -> None:
        pass  # Pool-Verwaltung übernimmt core.db
