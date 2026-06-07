"""
Memory-Konsolidierung – findet sehr ähnliche Memories und behält nur die beste.
Kein LLM-Merge mehr → kein Halluzinationsrisiko.

Logik:
  - Alle Memories paarweise per Kosinus-Distanz vergleichen
  - Paare unter SIMILARITY_THRESHOLD: schwächere (niedrigere Confidence) löschen
  - Keine Inhalte erfinden oder zusammenführen
"""
import asyncio
import logging

import numpy as np

from llm.base import LLMProvider
from memory.lzg import LZG

log = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.20  # Kosinus-Distanz < 0.20 = semantisch fast identisch


class Consolidator:
    def __init__(self, llm: LLMProvider, lzg: LZG):
        self.llm = llm
        self.lzg = lzg

    async def consolidate(self) -> int:
        """
        Findet nahezu identische Memory-Paare und löscht die schwächere.
        Gibt Anzahl der gelöschten Einträge zurück.
        """
        memories = self.lzg.get_all(limit=200)
        if len(memories) < 2:
            return 0

        # Embeddings für alle Memories laden
        embeddings = []
        for m in memories:
            try:
                emb = await self.llm.embed(m.content)
                embeddings.append((m, np.array(emb)))
            except Exception:
                pass

        deleted_ids: set[int] = set()
        delete_count = 0

        for i, (m1, e1) in enumerate(embeddings):
            if m1.id in deleted_ids:
                continue
            for j, (m2, e2) in enumerate(embeddings):
                if i >= j or m2.id in deleted_ids or m1.id in deleted_ids:
                    continue

                norm1 = np.linalg.norm(e1)
                norm2 = np.linalg.norm(e2)
                if norm1 == 0 or norm2 == 0:
                    continue
                dist = float(1 - np.dot(e1, e2) / (norm1 * norm2))

                if dist < SIMILARITY_THRESHOLD:
                    # Schwächere löschen, stärkere behalten + Confidence leicht erhöhen
                    keep, drop = (m1, m2) if m1.confidence >= m2.confidence else (m2, m1)
                    new_conf = min(0.99, keep.confidence + 0.02)
                    self.lzg.update_confidence(keep.id, new_conf)
                    self.lzg.delete(drop.id)
                    deleted_ids.add(drop.id)
                    delete_count += 1
                    log.info(
                        f"🗑️ Duplikat gelöscht (dist={dist:.3f}): '{drop.content[:60]}' "
                        f"→ behalte '{keep.content[:60]}'"
                    )
                    break

        if delete_count:
            log.info(f"🗑️ {delete_count} doppelte Memories entfernt")
        return delete_count

    async def consolidate_silent(self) -> None:
        """Läuft im Hintergrund ohne zu blockieren."""
        try:
            count = await self.consolidate()
            if count == 0:
                log.debug("Konsolidierung: keine Duplikate gefunden")
        except Exception as e:
            log.warning(f"Konsolidierung fehlgeschlagen: {e}")
