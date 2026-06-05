"""
Memory-Konsolidierung – findet ähnliche Memories und merged sie via LLM.
Läuft periodisch im Hintergrund.
"""
import asyncio
import json
import logging

import numpy as np

from llm.base import LLMProvider, Message
from memory.lzg import LZG, Memory

log = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.35  # Distanz unter der Memories als ähnlich gelten

MERGE_PROMPT_PREFIX = """Du konsolidierst zwei Erinnerungen über Timo die dasselbe Thema betreffen.

Erstelle EINE kombinierte, präzisere Erinnerung die alle Informationen beider enthält.
Antworte NUR mit der neuen Erinnerung als JSON-Objekt:
{"category": "...", "content": "...", "confidence": 0.0}

Regeln:
- Kategorie: die spezifischere der beiden wählen
- Konfidenz: Maximum beider + 0.02 (Bestätigung)
- Inhalt: alle Details beider zusammenführen, keine Wiederholungen

Erinnerung 1 (Kategorie: {cat1}, Konfidenz: {conf1}):
{content1}

Erinnerung 2 (Kategorie: {cat2}, Konfidenz: {conf2}):
{content2}

JSON:"""


class Consolidator:
    def __init__(self, llm: LLMProvider, lzg: LZG):
        self.llm = llm
        self.lzg = lzg

    async def consolidate(self) -> int:
        """
        Findet ähnliche Memory-Paare und merged sie.
        Gibt Anzahl der Merges zurück.
        """
        memories = self.lzg.get_all(limit=100)
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

        # Ähnliche Paare finden
        merged_ids: set[int] = set()
        merge_count = 0

        for i, (m1, e1) in enumerate(embeddings):
            if m1.id in merged_ids:
                continue
            for j, (m2, e2) in enumerate(embeddings):
                if i >= j or m2.id in merged_ids or m1.id in merged_ids:
                    continue
                dist = float(1 - np.dot(e1, e2) / (np.linalg.norm(e1) * np.linalg.norm(e2)))
                if dist < SIMILARITY_THRESHOLD:
                    log.info(f"🔀 Merge (dist={dist:.3f}): '{m1.content[:40]}' + '{m2.content[:40]}'")
                    merged = await self._merge(m1, m2)
                    if merged:
                        # Alte löschen, neue speichern
                        self.lzg.delete(m1.id)
                        self.lzg.delete(m2.id)
                        new_emb = await self.llm.embed(merged["content"])
                        self.lzg.save(
                            content=merged["content"],
                            embedding=new_emb,
                            category=merged["category"],
                            confidence=merged["confidence"],
                        )
                        merged_ids.add(m1.id)
                        merged_ids.add(m2.id)
                        merge_count += 1
                        break  # m1 ist jetzt gemerged, nächste Memory

        if merge_count:
            log.info(f"🔀 {merge_count} Memories konsolidiert")
        return merge_count

    async def _merge(self, m1: Memory, m2: Memory) -> dict | None:
        prompt = MERGE_PROMPT_PREFIX \
            .replace("{cat1}", m1.category).replace("{conf1}", str(m1.confidence)) \
            .replace("{content1}", m1.content) \
            .replace("{cat2}", m2.category).replace("{conf2}", str(m2.confidence)) \
            .replace("{content2}", m2.content)
        try:
            response = await self.llm.chat(
                messages=[Message(role="user", content=prompt)],
                temperature=0.2,
                max_tokens=200,
            )
            raw = response.strip()
            start = raw.find("{")
            end   = raw.rfind("}") + 1
            if start == -1:
                return None
            result = json.loads(raw[start:end])
            result["confidence"] = min(0.99, float(result.get("confidence", 0.85)))
            return result
        except Exception as e:
            log.warning(f"Merge fehlgeschlagen: {e}")
            return None

    async def consolidate_silent(self) -> None:
        """Läuft im Hintergrund ohne zu blockieren."""
        try:
            count = await self.consolidate()
            if count == 0:
                log.debug("Konsolidierung: keine ähnlichen Memories gefunden")
        except Exception as e:
            log.warning(f"Konsolidierung fehlgeschlagen: {e}")
