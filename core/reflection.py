"""
Selbst-Verbesserung – Alfred lernt über sich selbst und über Timo.

1. Interaktions-Reflexion: erkennt Korrekturen/Stimmung nach jedem Austausch,
   speichert Vorlieben & Kommunikationsstil als Meta-Gedächtnis.
2. Tages-Reflexion: analysiert die letzten Gespräche + Events, schreibt Insights,
   leitet Verhaltensanpassungen ab (z.B. mehr/weniger proaktiv, Tonfall).
3. behavior_notes(): liefert gelernte Stil-Hinweise für den System-Prompt.
"""
import logging
from datetime import datetime

from core import db, fast
from core.db import log_event
from llm.base import Message

log = logging.getLogger(__name__)

MAX_NOTES = 12


class Reflection:
    def __init__(self, llm, lzg):
        self.llm = llm
        self.lzg = lzg

    # ── Verhaltens-Hinweise (für System-Prompt) ───────────────────────────────

    def behavior_notes(self) -> str:
        notes = db.get_setting("meta_notes", []) or []
        if not notes:
            return ""
        return "## Gelernt über die Zusammenarbeit mit Timo:\n" + "\n".join(f"- {n}" for n in notes)

    _JUNK = ("korrektur", "vorliebe", "zeichen von", "technisches problem",
             "es gibt", "nichts", "json", "assistant", "timo:", "alfred:")

    def _add_note(self, note: str) -> None:
        n = note.strip().strip('"')
        low = n.lower()
        # Müll/Prompt-Echo herausfiltern
        if len(n) < 8 or len(n) > 120 or "\n" in n:
            return
        if any(j in low for j in self._JUNK):
            return
        notes = db.get_setting("meta_notes", []) or []
        if any(n.lower()[:40] in x.lower() for x in notes):
            return
        notes.append(n)
        notes = notes[-MAX_NOTES:]
        db.set_setting("meta_notes", notes)
        log_event("reflection", f"Neue Verhaltens-Notiz: {n[:80]}")

    # ── Interaktions-Reflexion (leichtgewichtig, nach jedem Turn) ─────────────

    async def reflect_on_interaction(self, user_msg: str, assistant_msg: str) -> None:
        """Schnelle Analyse via Schnellmodell: Korrektur? Vorliebe? Unmut?"""
        prompt = (
            "Analysiere diesen Austausch zwischen Timo (User) und Alfred (Assistant). "
            "Gibt es eine KORREKTUR, eine VORLIEBE, oder ein Zeichen von Unmut/Zufriedenheit, "
            "das Alfred sich fürs nächste Mal merken sollte?\n\n"
            f"Timo: {user_msg[:400]}\n"
            f"Alfred: {assistant_msg[:400]}\n\n"
            "Wenn ja: antworte mit EINEM kurzen Lern-Satz (imperativ, z.B. 'Fasse dich kürzer'). "
            "Wenn nichts Relevantes: antworte mit 'NICHTS'."
        )
        out = await fast.ask(prompt, max_tokens=40)
        out = out.strip().strip('"')
        if out and not out.upper().startswith("NICHTS") and len(out) > 8:
            self._add_note(out)

    async def daily_reflection(self) -> str | None:
        """Tages-Reflexion, 1x/Tag.

        Frühere Version ließ das LLM frei über den Tagesverlauf nachdenken und
        erzeugte dabei erfundene Insights. Jetzt wählt das LLM nur noch EINES aus
        echten, von pattern_detector berechneten Mustern aus und formuliert es kurz –
        es darf nichts hinzuerfinden, das nicht in den Mustern steht.
        """
        today = datetime.now().date().isoformat()
        if db.get_setting("last_daily_reflection_date") == today:
            return None
        db.set_setting("last_daily_reflection_date", today)

        from domains import pattern_detector
        try:
            patterns = pattern_detector.detect_all(days=7)
        except Exception as e:
            log.debug(f"daily_reflection: Pattern-Detector-Fehler: {e}")
            return None
        if not patterns:
            return None

        prompt = (
            "Hier sind echte, aus Timos Daten der letzten 7 Tage berechnete Muster:\n"
            + "\n".join(f"- {p}" for p in patterns)
            + "\n\nWähle GENAU EINES dieser Muster aus, das für Timo am relevantesten ist, "
            "und formuliere es als einen kurzen, konkreten Hinweis (maximal ein Satz). "
            "Erfinde NICHTS hinzu, das nicht oben steht – keine neuen Zahlen, keine neuen "
            "Beobachtungen. Antworte NUR mit dem Satz, ohne Anführungszeichen oder Erklärung."
        )
        try:
            insight = await self.llm.chat(
                [Message(role="user", content=prompt)], temperature=0.2, max_tokens=80,
            )
        except Exception as e:
            log.debug(f"daily_reflection: LLM-Fehler: {e}")
            return None

        insight = (insight or "").strip().strip('"')
        if not insight or len(insight) < 8 or len(insight) > 200:
            return None

        self._add_note(insight)
        log_event("reflection", f"Tages-Reflexion: {insight[:80]}")
        return insight
