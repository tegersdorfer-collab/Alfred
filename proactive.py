"""
Proaktive Nachrichten – Jarvis meldet sich aus eigener Initiative.
Basiert auf LZG-Memories und Tageszeit.
"""
import logging
from datetime import date, datetime

from llm.base import LLMProvider, Message
from memory.lzg import LZG
import config

try:
    from tools.dashboard import DashboardReader
    _dashboard = DashboardReader()
except Exception:
    _dashboard = None

log = logging.getLogger(__name__)

PROACTIVE_PROMPT = """Du bist Jarvis. Antworte IMMER auf Deutsch.

Du überlegst ob du Timo jetzt proaktiv schreiben sollst.

Generiere EINEN konkreten Gedanken/eine Nachricht an Timo auf Deutsch.

Priorität (in dieser Reihenfolge):
1. Follow-up zu etwas Konkretem aus dem letzten Gespräch – aber NUR wenn noch offen
2. Beobachtung oder Impuls basierend auf seinen Daten (Gesundheit, Ziele, Habits)
3. Gezielte Frage zu etwas das du noch NICHT weißt und nicht bereits gefragt hast

STRENGE Regeln:
- Max 2-3 Sätze
- Kein "Hallo Timo" – direkt rein
- Kein leeres "Wie geht's?" ohne Kontext
- KEINE Frage die im letzten Gespräch bereits gestellt oder beantwortet wurde
- KEINE Wiederholung von Themen die im letzten Gespräch bereits besprochen wurden
- Wenn du dir nicht sicher bist ob das Thema neu ist: lieber schweigen
- KEINE Diagnosen, medizinischen Erklärungen oder Ursachen erfinden die Timo nicht selbst genannt hat
- Nur Fakten verwenden die Timo dir tatsächlich mitgeteilt hat

Aktuelle Zeit: {time}
Was du über Timo weißt:
{memories}
{recent_chat}
Generiere jetzt den Gedanken (nur der Text, kein Kommentar):"""

EVALUATE_PROMPT = """Du bist Jarvis. Du hast gerade diesen Gedanken generiert:

"{thought}"

Entscheide: Soll ich das JETZT an Timo schicken?

Kriterien für JA:
- Echter Mehrwert oder echte Frage
- Nicht zu ähnlich wie die letzte Nachricht
- Nicht zu aufdringlich für den Zeitpunkt

Kriterien für NEIN:
- Zu trivial oder generisch
- Keine neuen Informationen
- Wirkt aufgesetzt

Antworte NUR mit: JA oder NEIN"""


class ProactiveTracker:
    """Verfolgt wie viele proaktive Nachrichten heute schon gesendet wurden."""

    def __init__(self):
        self._today: date = date.today()
        self._count: int = 0
        # Beim Start so tun als hätten wir gerade gesendet → kein Spam direkt nach Neustart
        self._last_sent: datetime | None = datetime.now()

    def _reset_if_new_day(self) -> None:
        today = date.today()
        if today != self._today:
            self._today = today
            self._count = 0
            log.debug("Proaktiv-Zähler für neuen Tag zurückgesetzt")

    def _interval(self) -> int:
        """Mindestabstand – kann durch Selbst-Reflexion angepasst werden."""
        try:
            from core import db
            override = db.get_setting("proactive_interval_override")
            if isinstance(override, (int, float)):
                return int(override)
        except Exception:
            pass
        return config.PROACTIVE_INTERVAL

    def can_send(self) -> bool:
        self._reset_if_new_day()

        # Mindestabstand zum letzten proaktiven Message
        if self._last_sent:
            elapsed = (datetime.now() - self._last_sent).total_seconds()
            if elapsed < self._interval():
                return False

        return True

    def record_sent(self) -> None:
        self._reset_if_new_day()
        self._count += 1
        self._last_sent = datetime.now()
        log.info(f"📤 Proaktive Nachricht gesendet ({self._count} heute)")

    @property
    def count_today(self) -> int:
        self._reset_if_new_day()
        return self._count


class ProactiveEngine:
    """Generiert und sendet proaktive Nachrichten."""

    def __init__(self, llm: LLMProvider, lzg: LZG, claude: LLMProvider | None = None):
        self.llm    = llm
        self.lzg    = lzg
        self.claude = claude  # Optional: Claude Code für Bewertung

    async def evaluate(self, thought: str) -> bool:
        """
        Lässt Jarvis selbst entscheiden ob der Gedanke es wert ist gesendet zu werden.
        Nutzt Claude Code wenn verfügbar (besseres Urteilsvermögen), sonst Qwen.
        """
        prompt = EVALUATE_PROMPT.replace("{thought}", thought)
        try:
            response = await self.llm.chat(
                messages=[Message(role="user", content=prompt)],
                temperature=0.2,
                max_tokens=10,
            )
            verdict = response.strip().upper()
            should_send = verdict.startswith("JA")
            log.debug(f"Bewertung: {verdict} → {'senden' if should_send else 'verwerfen'}")
            return should_send
        except Exception as e:
            log.warning(f"Bewertung fehlgeschlagen: {e}")
            return False

    async def generate(self) -> str | None:
        """Generiert eine proaktive Nachricht basierend auf Memories + Dashboard + Chat-History."""
        try:
            memories = self.lzg.get_all(limit=10)
            memory_ctx = self.lzg.format_for_context(memories)
        except Exception as e:
            log.warning(f"Memory-Abruf für Proaktiv fehlgeschlagen: {e}")
            memory_ctx = "Keine Langzeiterinnerungen verfügbar."

        # Dashboard-Kontext für proaktive Nutzung
        dashboard_ctx = ""
        if _dashboard:
            try:
                health = _dashboard.get_recent_health(days=2)
                events = _dashboard.get_upcoming_events(days=3)
                tasks  = _dashboard.get_open_tasks(limit=5)
                lines  = []
                if health:
                    lines.append("Gesundheit: " + " | ".join(
                        f"{h.date}: {h.steps or 0} Schritte, {h.sleep_duration or 0:.1f}h Schlaf"
                        for h in health[:2]
                    ))
                if events:
                    lines.append("Bevorstehende Termine: " + ", ".join(
                        f"{e.start.strftime('%d.%m. %H:%M') if not e.all_day else e.start.strftime('%d.%m.')} {e.title}"
                        for e in events[:3]
                    ))
                if tasks:
                    lines.append("Offene Tasks: " + ", ".join(t.title for t in tasks[:3]))
                dashboard_ctx = "\n".join(lines)
            except Exception as e:
                log.debug(f"Dashboard-Kontext für Proaktiv fehlgeschlagen: {e}")

        # Letzte Chat-Nachrichten + explizite Blacklist bereits gestellter Fragen
        recent_chat_ctx = ""
        last_proactive_ctx = ""
        try:
            from core import db as _db
            rows = _db.query(
                """
                SELECT role, content, channel FROM chat_messages
                ORDER BY created_at DESC
                LIMIT 20
                """,
            )
            if rows:
                # Letzte proaktive Jarvis-Nachrichten explizit hervorheben
                proactive_msgs = [
                    r["content"][:150]
                    for r in rows
                    if r["role"] == "assistant" and r.get("channel") in ("autopilot", "telegram")
                ][:3]
                if proactive_msgs:
                    last_proactive_ctx = (
                        "\n⛔ BEREITS GESENDETE NACHRICHTEN (diese Themen/Fragen NICHT wiederholen):\n"
                        + "\n".join(f"- {m}" for m in proactive_msgs)
                        + "\n"
                    )

                # Gesamte Chat-History als Kontext
                rows_conv = list(reversed(rows[:12]))
                lines = []
                for r in rows_conv:
                    role_label = "Timo" if r["role"] == "user" else "Jarvis"
                    lines.append(f"{role_label}: {r['content'][:200]}")
                recent_chat_ctx = "\nLetztes Gespräch:\n" + "\n".join(lines) + "\n"
        except Exception as e:
            log.debug(f"Chat-History für Proaktiv fehlgeschlagen: {e}")

        now = datetime.now().strftime("%A, %d. %B %Y, %H:%M Uhr")
        memories_with_dashboard = memory_ctx
        if dashboard_ctx:
            memories_with_dashboard += f"\n\nLive-Daten:\n{dashboard_ctx}"
        prompt = PROACTIVE_PROMPT.format(
            time=now,
            memories=memories_with_dashboard,
            recent_chat=recent_chat_ctx + last_proactive_ctx,
        )

        try:
            response = await self.llm.chat(
                messages=[Message(role="user", content=prompt)],
                temperature=0.65,   # Niedrig genug um Generations-Loops zu vermeiden
                max_tokens=150,     # Kurz halten – proaktive Nachrichten müssen prägnant sein
            )
            msg = response.strip()
            if msg:
                log.info(f"💭 Proaktiv generiert: {msg[:60]}...")
            return msg if msg else None
        except Exception as e:
            log.warning(f"Proaktiv-Generierung fehlgeschlagen: {e}")
            return None
