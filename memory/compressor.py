"""
KZG → LZG Komprimierung.
Läuft async nach jedem Gespräch und extrahiert langfristig relevante Fakten.
"""
import asyncio
import json
import logging

from llm.base import LLMProvider, Message
from memory.kzg import KZG
from memory.lzg import LZG

log = logging.getLogger(__name__)

# Kein f-string, kein .format() – plain string mit eigenem Platzhalter
COMPRESSION_PROMPT_PREFIX = """Du analysierst ein Gespräch zwischen Timo und Jarvis.
Extrahiere alle Informationen die LANGFRISTIG relevant sind.

Kategorien:
- fact: Konkrete Fakten über Timo (Gewohnheiten, Vorlieben, Lebensumstände)
- goal: Ziele, Pläne, Vorhaben
- pattern: Erkannte Verhaltensmuster
- correction: Korrekturen zu früheren Annahmen
- context: Wichtiger situativer Kontext

Antworte NUR mit einem JSON-Array, kein Text davor oder danach:
[
  {"category": "fact", "content": "Timo trainiert 4x pro Woche", "confidence": 0.9},
  {"category": "goal", "content": "Timo will bis September 80kg wiegen", "confidence": 0.85}
]

Regeln:
- Nur wirklich neue oder bestätigte Informationen
- Keine Trivialitäten
- Konfidenz: 0.5 = unsicher, 0.8 = klar gesagt, 0.95 = explizit bestätigt
- Wenn nichts relevantes: []

Gespräch:
"""

COMPRESSION_PROMPT_SUFFIX = "\n\nJSON:"


class Compressor:
    def __init__(self, llm: LLMProvider, kzg: KZG, lzg: LZG):
        self.llm = llm
        self.kzg = kzg
        self.lzg = lzg

    def _build_prompt(self, conversation: str) -> str:
        """Baut Prompt durch einfache Konkatenation – kein format(), kein replace()."""
        return COMPRESSION_PROMPT_PREFIX + conversation + COMPRESSION_PROMPT_SUFFIX

    async def compress(self) -> int:
        """
        Komprimiert aktuelles KZG ins LZG.
        Gibt Anzahl gespeicherter Memories zurück.
        """
        if self.kzg.is_empty():
            return 0

        conversation = self.kzg.summary_for_compression()
        prompt = self._build_prompt(conversation)

        try:
            response = await self.llm.chat(
                messages=[Message(role="user", content=prompt)],
                temperature=0.3,
                max_tokens=1024,
                format="json",
            )

            from core.jsonutil import extract_json
            entries = extract_json(response, default=[])
            if not isinstance(entries, list) or len(entries) == 0:
                return 0

            saved = 0
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                content = str(entry.get("content", "")).strip()
                category = str(entry.get("category", "fact"))
                try:
                    confidence = float(entry.get("confidence", 0.8))
                except (ValueError, TypeError):
                    confidence = 0.8

                if not content:
                    continue

                embedding = await self.llm.embed(content)

                # Duplikat-Check: ähnliche Memory bereits vorhanden?
                similar = self.lzg.find_similar(embedding, threshold=0.30)
                if similar:
                    best_match, dist = similar[0]
                    # Konfidenz nach oben updaten (Bestätigung)
                    new_conf = min(0.99, max(best_match.confidence, confidence))
                    self.lzg.update_confidence(best_match.id, new_conf)
                    log.debug(
                        f"Memory aktualisiert (dist={dist:.3f}): {best_match.content[:60]}"
                    )
                else:
                    self.lzg.save(
                        content=content,
                        embedding=embedding,
                        category=category,
                        confidence=confidence,
                    )
                    saved += 1

            return saved

        except (ValueError, KeyError, TypeError) as e:
            # Parsing-/Datenfehler → kein Retry sinnvoll, einfach nichts extrahiert
            log.debug(f"Komprimierung ohne Ergebnis: {e}")
            return 0
        # LLM-/DB-/Netzwerkfehler propagieren absichtlich → Retry in _compress_silent

    async def compress_async(self) -> None:
        """Startet Komprimierung im Hintergrund ohne zu blockieren."""
        asyncio.create_task(self._compress_silent())

    async def _compress_silent(self, retries: int = 1) -> None:
        for attempt in range(retries + 1):
            try:
                count = await self.compress()
                if count > 0:
                    log.info(f"💾 {count} Erinnerungen ins LZG komprimiert")
                return
            except Exception as e:
                if attempt < retries:
                    log.debug(f"Komprimierung Versuch {attempt+1} fehlgeschlagen ({e}) – Retry in 3s")
                    await asyncio.sleep(3)
                else:
                    log.warning(f"Komprimierung endgültig fehlgeschlagen: {e}")
