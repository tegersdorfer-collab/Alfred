"""
Selbst-Verbesserung – Jarvis lernt über sich selbst und über Timo.

1. Interaktions-Reflexion: erkennt Korrekturen/Stimmung nach jedem Austausch,
   speichert Vorlieben & Kommunikationsstil als Meta-Gedächtnis.
2. Tages-Reflexion: analysiert die letzten Gespräche + Events, schreibt Insights,
   leitet Verhaltensanpassungen ab (z.B. mehr/weniger proaktiv, Tonfall).
3. behavior_notes(): liefert gelernte Stil-Hinweise für den System-Prompt.
"""
import json
import logging
from datetime import date, datetime

from core import db, fast
from core.db import log_event

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
             "es gibt", "nichts", "json", "assistant", "timo:", "jarvis:")

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
            "Analysiere diesen Austausch zwischen Timo (User) und Jarvis (Assistant). "
            "Gibt es eine KORREKTUR, eine VORLIEBE, oder ein Zeichen von Unmut/Zufriedenheit, "
            "das Jarvis sich fürs nächste Mal merken sollte?\n\n"
            f"Timo: {user_msg[:400]}\n"
            f"Jarvis: {assistant_msg[:400]}\n\n"
            "Wenn ja: antworte mit EINEM kurzen Lern-Satz (imperativ, z.B. 'Fasse dich kürzer'). "
            "Wenn nichts Relevantes: antworte mit 'NICHTS'."
        )
        out = await fast.ask(prompt, max_tokens=40)
        out = out.strip().strip('"')
        if out and not out.upper().startswith("NICHTS") and len(out) > 8:
            self._add_note(out)

    # ── Tages-Reflexion (einmal/Tag, tiefer) ──────────────────────────────────

    def _needs_daily(self) -> bool:
        return db.get_setting("reflection_daily_date") != str(date.today())

    async def daily_reflection(self) -> str | None:
        if not self._needs_daily():
            return None
        db.set_setting("reflection_daily_date", str(date.today()))

        msgs = db.query(
            "SELECT role, content, channel FROM chat_messages ORDER BY created_at DESC LIMIT 30"
        )
        if len(msgs) < 4:
            return None
        convo = "\n".join(
            f"{'Timo' if m['role']=='user' else 'Jarvis'}: {m['content'][:200]}"
            for m in reversed(msgs)
        )
        prompt = (
            "Du bist Jarvis und reflektierst über deine Arbeit mit Timo. "
            "Analysiere die jüngsten Interaktionen und antworte als JSON:\n"
            '{"insight": "wichtigste Erkenntnis (1 Satz)", '
            '"behavior_adjustment": "konkrete Verhaltensänderung oder leer", '
            '"proactivity": "more|less|keep"}\n\n'
            f"Interaktionen:\n{convo}\n\nJSON:"
        )
        try:
            from core.jsonutil import extract_json
            raw = await self.llm.chat(messages=[{"role": "user", "content": prompt}],
                                      temperature=0.4, max_tokens=300, format="json")
            data = extract_json(raw, default={})
        except Exception as ex:
            log.debug(f"Tages-Reflexion JSON-Fehler: {ex}")
            return None
        if not isinstance(data, dict):
            data = {}

        insight = (data.get("insight") or "").strip()
        adjustment = (data.get("behavior_adjustment") or "").strip()
        proactivity = (data.get("proactivity") or "keep").strip().lower()

        if insight:
            db.execute(
                "INSERT INTO reflections (kind, content, insights) VALUES ('daily', %s, %s)",
                (insight, json.dumps(data)),
            )
        if adjustment and len(adjustment) > 5:
            self._add_note(adjustment)

        # Proaktivität anpassen (begrenzt)
        if proactivity in ("more", "less"):
            cur = db.get_setting("proactive_interval_override")
            base = cur if isinstance(cur, (int, float)) else 1800
            if proactivity == "more":
                base = max(900, int(base * 0.8))
            else:
                base = min(7200, int(base * 1.25))
            db.set_setting("proactive_interval_override", base)
            log_event("reflection", f"Proaktivität → {proactivity} (Intervall {base}s)")

        log.info(f"🪞 Tages-Reflexion: {insight[:80]}")
        log_event("reflection", f"Tages-Reflexion: {insight[:100]}")
        return insight
