"""
Onboarding – systematisches Erstgespräch mit Timo.
Läuft einmalig wenn < 5 Memories in der LZG vorhanden sind.
Stellt gezielte Fragen und speichert Antworten direkt als Memories.
"""
import asyncio
import logging

from llm.base import LLMProvider, Message
from memory.lzg import LZG

log = logging.getLogger(__name__)

# Fragen in dieser Reihenfolge – jede liefert wertvolle LZG-Daten
ONBOARDING_QUESTIONS = [
    {
        "text": (
            "Hey, ich bin neu hier und will dich wirklich kennenlernen – nicht oberflächlich. "
            "Fang einfach an: Wer bist du, was machst du gerade in deinem Leben, "
            "und was treibt dich an?"
        ),
        "category": "context",
    },
    {
        "text": (
            "Was sind deine 2-3 größten Ziele gerade – egal ob Sport, Arbeit, Finanzen oder privat? "
            "Konkret, nicht allgemein."
        ),
        "category": "goal",
    },
    {
        "text": (
            "Wie sieht dein normaler Tagesablauf aus? Wann stehst du auf, "
            "wann arbeitest du, wann trainierst du – und was stimmt davon gerade nicht?"
        ),
        "category": "fact",
    },
    {
        "text": (
            "Was läuft gerade richtig gut in deinem Leben? "
            "Und wo steckst du fest oder kommst nicht weiter?"
        ),
        "category": "pattern",
    },
    {
        "text": (
            "Letzte Frage: Was erwartest du von mir? "
            "Wann bin ich für dich nützlich, wann nervt mich – sag's direkt."
        ),
        "category": "context",
    },
]

COMPRESS_PROMPT_PREFIX = """Du analysierst eine Antwort von Timo im Rahmen eines Onboardings.
Extrahiere alle langfristig relevanten Fakten als JSON-Array.

Kategorie: {category}

Regeln:
- Konkret und spezifisch (keine Verallgemeinerungen)
- Konfidenz: 0.9 wenn klar gesagt, 0.95 wenn explizit bestätigt
- Mehrere Einträge wenn sinnvoll
- Wenn nichts Relevantes: []

Format:
[{{"category": "{category}", "content": "...", "confidence": 0.9}}]

Antwort von Timo:
"""


class Onboarding:
    def __init__(self, llm: LLMProvider, lzg: LZG, send_fn):
        self.llm     = llm
        self.lzg     = lzg
        self.send_fn = send_fn  # async fn(text) -> None
        self._waiting_answer = False
        self._current_q_idx  = -1
        self._pending_category = None

    @property
    def is_active(self) -> bool:
        return self._waiting_answer

    def should_run(self) -> bool:
        """Onboarding starten wenn < 5 Memories vorhanden."""
        try:
            count = len(self.lzg.get_all(limit=5))
            return count < 5
        except Exception:
            return False

    async def start(self) -> None:
        """Onboarding-Intro senden und erste Frage stellen."""
        log.info("🎯 Onboarding startet")
        intro = (
            "Bevor wir loslegen – ich brauche ein paar Minuten von dir. "
            "Ich stelle dir ein paar direkte Fragen damit ich dich wirklich kenne "
            "und nicht ins Blaue rede. Keine Schönfärberei nötig.\n\n"
        )
        await self.send_fn(intro + ONBOARDING_QUESTIONS[0]["text"])
        self._current_q_idx  = 0
        self._pending_category = ONBOARDING_QUESTIONS[0]["category"]
        self._waiting_answer = True

    async def handle_answer(self, answer: str) -> bool:
        """
        Verarbeitet eine Antwort. Gibt True zurück solange Onboarding läuft.
        Gibt False zurück wenn Onboarding abgeschlossen.
        """
        if not self._waiting_answer:
            return False

        # Antwort als Memories speichern
        await self._compress_answer(answer, self._pending_category)

        # Nächste Frage oder abschließen
        next_idx = self._current_q_idx + 1
        if next_idx < len(ONBOARDING_QUESTIONS):
            self._current_q_idx  = next_idx
            self._pending_category = ONBOARDING_QUESTIONS[next_idx]["category"]
            await self.send_fn(ONBOARDING_QUESTIONS[next_idx]["text"])
            return True
        else:
            self._waiting_answer = False
            await self.send_fn(
                "Gut. Ich habe mir alles gemerkt. "
                "Ab jetzt rede ich nicht mehr ins Leere."
            )
            log.info("🎯 Onboarding abgeschlossen")
            return False

    async def _compress_answer(self, answer: str, category: str) -> None:
        """Extrahiert Fakten aus Antwort und speichert sie in LZG."""
        import json
        prompt = COMPRESS_PROMPT_PREFIX.replace("{category}", category) + answer + "\n\nJSON:"
        try:
            response = await self.llm.chat(
                messages=[Message(role="user", content=prompt)],
                temperature=0.2,
                max_tokens=512,
            )
            raw = response.strip()
            start = raw.find("[")
            end   = raw.rfind("]") + 1
            if start == -1 or end == 0:
                return
            entries = json.loads(raw[start:end])
            saved = 0
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                content    = str(entry.get("content", "")).strip()
                cat        = str(entry.get("category", category))
                confidence = float(entry.get("confidence", 0.9))
                if not content:
                    continue
                embedding = await self.llm.embed(content)
                similar = self.lzg.find_similar(embedding, threshold=0.12)
                if similar:
                    self.lzg.update_confidence(similar[0][0].id, confidence)
                else:
                    self.lzg.save(content=content, embedding=embedding,
                                  category=cat, confidence=confidence)
                    saved += 1
            if saved:
                log.info(f"🎯 Onboarding: {saved} Memories gespeichert")
        except Exception as e:
            log.warning(f"Onboarding-Komprimierung fehlgeschlagen: {e}")
