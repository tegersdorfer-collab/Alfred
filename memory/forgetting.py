"""
memory/forgetting.py

Simuliert die Ebbinghaussche Vergessenskurve für das Mantis-Langzeitgedächtnis.

Formel:
    retention = exp(-t / S)
    S = importance * (1 + 0.25 * recall_count)   # Stabilität wächst mit Wiederholungen

    t = Tage seit last_recalled

Regeln:
  - retention < DELETE_THRESHOLD → Memory löschen
  - kg_linked = TRUE             → niemals löschen (im Wissens-Graphen verankert)
  - Chat-Nachrichten ohne Entity-Bezug → nach CHAT_TTL_DAYS löschen

Läuft stündlich im Idle-Loop des Orchestrators.
"""
import logging
import math
from datetime import datetime, timezone

from core import db as _db

log = logging.getLogger(__name__)

DELETE_THRESHOLD = 0.10   # Retention unter 10% → vergessen
CHAT_TTL_DAYS    = 3      # Einfache Chat-Nachrichten nach 3 Tagen löschen


class ForgettingCurve:

    async def run(self) -> dict:
        """
        Führt einen Vergessens-Durchlauf durch.
        Gibt Stats-Dict zurück: {checked, forgotten, chat_pruned}
        """
        forgotten   = await self._decay_memories()
        chat_pruned = await self._prune_chat()
        await self._importance_triage()
        return {"forgotten": forgotten, "chat_pruned": chat_pruned}

    async def _importance_triage(self) -> None:
        """
        Importance Triage: oft-abgerufene Memories steigen auf (max 1.0),
        nie-abgerufene sinken ab (min 0.1). Läuft im Vergessens-Durchlauf.
        """
        import asyncio
        # Hochstufen: recall_count >= 3 → importance += 0.1 (max 1.0)
        await asyncio.to_thread(
            _db.execute,
            """
            UPDATE memories
            SET importance = LEAST(importance + 0.1, 1.0)
            WHERE recall_count >= 3 AND importance < 1.0
            """,
        )
        # Abstufen: nie abgerufen und älter als 14 Tage → importance -= 0.05 (min 0.1)
        await asyncio.to_thread(
            _db.execute,
            """
            UPDATE memories
            SET importance = GREATEST(importance - 0.05, 0.1)
            WHERE recall_count = 0
              AND created_at < NOW() - INTERVAL '14 days'
              AND importance > 0.1
            """,
        )

    async def _decay_memories(self) -> int:
        """Löscht Memories mit zu niedriger Retention (außer kg_linked)."""
        import asyncio
        rows = await asyncio.to_thread(
            _db.query,
            """
            SELECT id, importance, recall_count, last_recalled, content
            FROM memories
            WHERE kg_linked = FALSE
            """,
        )
        now = datetime.now(timezone.utc)
        to_delete = []

        for r in rows:
            last = r["last_recalled"]
            if last is None:
                continue
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            days = (now - last).total_seconds() / 86400
            importance   = float(r["importance"]   or 0.5)
            recall_count = int(r["recall_count"]   or 0)

            # Stabilität steigt mit jeder Wiederholung
            stability = importance * (1 + 0.25 * recall_count)
            # Mindest-Stabilität: normale Memories halten mindestens ~7 Tage (S=1)
            stability = max(stability, 1.0)
            retention = math.exp(-days / stability)

            if retention < DELETE_THRESHOLD:
                to_delete.append((r["id"], r["content"][:60], round(retention, 3)))

        for mid, snippet, ret in to_delete:
            await asyncio.to_thread(_db.execute, "DELETE FROM memories WHERE id = %s", (mid,))
            log.info(f"🕐 Vergessen (ret={ret}): '{snippet}'")

        return len(to_delete)

    async def _prune_chat(self) -> int:
        """Löscht alte Chat-Nachrichten (einfaches TTL)."""
        import asyncio
        result = await asyncio.to_thread(
            _db.query_one,
            f"""
            WITH deleted AS (
                DELETE FROM chat_messages
                WHERE created_at < NOW() - INTERVAL '{CHAT_TTL_DAYS} days'
                RETURNING id
            )
            SELECT count(*) AS n FROM deleted
            """,
        )
        n = int((result or {}).get("n", 0))
        if n:
            log.info(f"🗑️ {n} alte Chat-Nachrichten gelöscht (>{CHAT_TTL_DAYS}d)")
        return n

    def bump_recall(self, memory_id: int) -> None:
        """Wird aufgerufen wenn eine Memory im Kontext genutzt wurde → Stabilität erhöhen."""
        _db.execute(
            """
            UPDATE memories
            SET recall_count  = recall_count + 1,
                last_recalled = NOW()
            WHERE id = %s
            """,
            (memory_id,),
        )
