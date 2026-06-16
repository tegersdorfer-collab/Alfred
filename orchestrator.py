"""
Orchestrator – Herzstück von Alfred 2.0.
Koordiniert: Agent (Tool-Calling), Gedächtnis, Autopilot, Reflexion, Kommunikation, Thermal.
"""
import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path

from llm.base import LLMProvider
from llm.local import OllamaProvider
from core.backends.base import AgentBackend
from memory.kzg import KZG
from memory.lzg import LZG
from memory.consolidator import Consolidator
from memory.extractor import MemoryExtractor
from memory.knowledge import KnowledgeGraph
from memory.forgetting import ForgettingCurve
from communication.base import CommunicationChannel, IncomingMessage
from thermal import ThermalMonitor
from proactive import ProactiveEngine, ProactiveTracker


from core import db, fast, skills
from core.agent import Agent
from core.skills import SkillContext
from core.autopilot import Autopilot
from core.reflection import Reflection
from core.db import log_event

from tools.search import WebSearch
from domains import pattern_detector
from tools.dashboard import DashboardReader
from tools.reminders import ReminderStore
from core.status import BUS
import config

log = logging.getLogger(__name__)


def _load_identity() -> str:
    """Lädt die generische Identität und füllt persönliche Platzhalter aus .env."""
    text = (Path(__file__).parent / "identity" / "alfred.md").read_text()
    text = text.replace("{{OWNER}}", config.OWNER_NAME)
    text = text.replace("{{TIMEZONE}}", config.OWNER_TIMEZONE)
    if config.OWNER_EMAIL:
        text += f"\n- Kontakt: {config.OWNER_EMAIL}\n"
    return text


IDENTITY = _load_identity()


class Orchestrator:
    def __init__(self, channel: CommunicationChannel, lzg: LZG, thermal: ThermalMonitor,
                 chat_llm: LLMProvider, bg_llm: LLMProvider, embed_llm: LLMProvider,
                 agent_backend: AgentBackend):
        # chat_llm      → Echtzeit-Chat (Haiku) — speed-kritisch
        # bg_llm        → Background-Tasks, Proaktiv, Briefing (llama-server lokal) — qualitätskritisch
        # embed_llm     → Embeddings für Memory (immer Ollama)
        # agent_backend → Tool-Calling im ReAct-Loop (Claude oder Ollama)
        self.llm          = chat_llm   # Alias für Kompatibilität (Chat)
        self.chat_llm     = chat_llm
        self.bg_llm       = bg_llm
        self.embed_llm    = embed_llm
        self.channel      = channel
        self.lzg          = lzg
        self.thermal      = thermal

        self.kzg          = KZG()
        self.kg           = KnowledgeGraph()
        self.consolidator = Consolidator(llm=bg_llm, lzg=self.lzg)
        self.forgetting   = ForgettingCurve()
        self.extractor    = MemoryExtractor(llm_provider=embed_llm, lzg=self.lzg, kg=self.kg)
        self.reflection   = Reflection(llm=bg_llm, lzg=self.lzg)
        self.agent        = Agent(backend=agent_backend, max_steps=8)

        self._search    = WebSearch()
        self._dashboard = DashboardReader()
        self._reminders = ReminderStore()

        self._proactive_tracker = ProactiveTracker()
        self._proactive_engine  = ProactiveEngine(llm=bg_llm, lzg=lzg, claude=None, kg=self.kg)

        self._last_user_ts = 0.0

        self.autopilot = Autopilot(
            llm=bg_llm, lzg=lzg, dashboard=self._dashboard, reminders=self._reminders,
            channel=channel, proactive=self._proactive_engine,
            tracker=self._proactive_tracker, identity=IDENTITY,
            lock=None, is_user_active=self._user_active,
            search=self._search,
        )

        self._state = "idle"
        self._last_consolidation: datetime | None = None
        self._last_compress: datetime | None = None
        self._last_pattern_run: datetime | None = None
        self._last_health_refresh: datetime | None = None
        self._last_health_suggestion: datetime | None = None  # Cooldown für Health-Vorschläge
        self._last_insight_run: datetime | None = None        # Cooldown für Insight-Tasks
        self._idle_task: asyncio.Task | None = None

    def _user_active(self) -> bool:
        """True wenn Timo in den letzten 30min interagiert hat.
        Verhindert dass Autopilot direkt nach einem Gespräch erneut stört."""
        return (time.time() - self._last_user_ts) < 1800

    # ── System-Prompt (parallel aufgebaut) ────────────────────────────────────

    def _memory_context(self, embedding) -> str:
        try:
            if embedding is not None:
                mems = self.lzg.search(embedding, top_k=config.LZG_TOP_K)
            else:
                mems = self.lzg.get_all(limit=10)
            # recall_count erhöhen für genutzte Memories (Ebbinghaus: Wiederholung stärkt)
            for m in mems:
                try:
                    self.forgetting.bump_recall(m.id)
                except Exception:
                    pass
            return self.lzg.format_for_context(mems)
        except Exception as e:
            log.debug(f"Memory-Kontext: {e}")
            return "—"

    def _kg_context(self) -> str:
        try:
            return self.kg.format_for_context()
        except Exception as e:
            log.debug(f"KG-Kontext: {e}")
            return ""

    async def _build_system_prompt(self, user_text: str) -> str:
        # embed → mem_ctx (Kette) läuft parallel zu dash_ctx + task_ctx
        async def _embed_and_mem():
            try:
                embedding = await self.embed_llm.embed(user_text)
            except Exception as e:
                log.debug(f"Embed fehlgeschlagen: {e}", exc_info=True)
                embedding = None
            return await asyncio.to_thread(self._memory_context, embedding)

        mem_ctx, dash_ctx, task_ctx, kg_ctx = await asyncio.gather(
            _embed_and_mem(),
            asyncio.to_thread(self._safe_dashboard_ctx),
            asyncio.to_thread(self._safe_task_ctx),
            asyncio.to_thread(self._kg_context),
        )
        behavior = self.reflection.behavior_notes()
        now = datetime.now()
        WD = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
        now_str = f"{WD[now.weekday()]}, {now.strftime('%d.%m.%Y, %H:%M')} Uhr"

        prompt = IDENTITY
        prompt += (
            "\n\n## Werkzeuge\n"
            "Du hast Zugriff auf viele Tools (Tasks, Reminder, Kalender, Habits, Fitness, "
            "Ernährung, Journal, Ziele, Health-Daten, Wetter, Web-Suche, Gedächtnis). "
            "Nutze sie EIGENSTÄNDIG wenn Timo etwas erledigt oder wissen will – frag nicht um Erlaubnis, "
            "handle. Antworte danach kurz und natürlich auf Deutsch.\n"
            "KRITISCH: Wenn Timo eine AKTION verlangt (löschen, erstellen, eintragen, verschieben, "
            "erinnern, abhaken etc.) MUSST du das passende Tool aufrufen. NIEMALS sagen 'ich habe "
            "keine Funktion dafür' oder 'ich kann das nicht' wenn ein passendes Tool existiert. "
            "Beispiel: 'Lösch den Termin X' → delete_calendar_event aufrufen.\n"
            "AUFGABEN-ZUWEISUNG: Wenn du create_task aufrufst, entscheidet das System automatisch "
            "ob du (Alfred) oder Timo die Aufgabe bekommt – du musst das NICHT selbst entscheiden "
            "oder erklären. Ruf einfach create_task auf. NIEMALS sagen 'ich kann mir keine Aufgaben "
            "zuweisen' – das stimmt nicht, das passiert automatisch im Hintergrund.\n"
            "FÄHIGKEITSLÜCKEN: Wenn für eine Anfrage KEIN passendes Tool existiert, sag NIEMALS "
            "einfach 'das kann ich nicht' oder 'dafür habe ich keine Funktion'. Nutze statt­dessen "
            "create_skill, um dir selbst ein neues Tool zu bauen (Python-Code, sofort aktiv, kein "
            "Neustart nötig) – und ruf es danach direkt auf um Timos Anfrage zu erledigen. Nur wenn "
            "create_skill selbst einen Fehler zurückgibt (z.B. Tages-Limit erreicht oder Validierung "
            "fehlgeschlagen), erklär Timo ehrlich was nicht ging.\n"
            "ZEIT/DATUM: Nutze den Wert aus '## Aktuell' weiter unten als aktuelle Zeit (Europe/Berlin). "
            "Rechne Wochentage/relative Angaben IMMER ab heute. Für Termine/Reminder nutze "
            "Formate wie 'morgen 14:00', 'heute 18:30' oder 'TT.MM.JJJJ HH:MM' – immer LOKALE Zeit, "
            "niemals UTC.\n"
        )
        if behavior:
            prompt += f"\n{behavior}\n"
        prompt += f"\n## Was du über Timo weißt:\n{mem_ctx}\n"
        if kg_ctx:
            prompt += f"\n{kg_ctx}\n"
        if task_ctx:
            prompt += f"\n## Offene Aufgaben:\n{task_ctx}\n"
        if dash_ctx:
            prompt += f"\n## Live-Daten (Dashboard):\n{dash_ctx}\n"
        prompt += f"\n## Aktuell:\n{now_str}\n"
        return prompt

    def _safe_task_ctx(self) -> str:
        try:
            from domains import tasks as tasks_d
            return tasks_d.context_summary(8)
        except Exception:
            return ""

    def _safe_dashboard_ctx(self) -> str:
        try:
            return self._dashboard.format_for_context()
        except Exception:
            return ""

    # ── Nachricht verarbeiten ──────────────────────────────────────────────────

    async def handle_message(self, msg: IncomingMessage) -> None:
        self._state = "conversation"
        self._last_user_ts = time.time()
        t0 = time.time()
        BUS.emit("thinking", "Nachricht empfangen…", detail=msg.text[:60])
        log.info(f"Eingehend: {msg.text[:60]}")
        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()

        self.kzg.add("user", msg.text)
        self._persist_msg("user", msg.text, channel="telegram")

        # ── Task-Klärungsantwort erkennen ──────────────────────────────────────
        waiting = db.query(
            """SELECT id FROM tasks
               WHERE execution_phase='waiting_clarification'
               AND clarification_answer IS NULL
               ORDER BY created_at DESC LIMIT 1"""
        )
        if waiting:
            db.execute(
                "UPDATE tasks SET clarification_answer=%s, execution_phase='executing', hold_until=NULL WHERE id=%s",
                (msg.text, waiting[0]["id"])
            )
            response = "Danke! Ich mache mit deiner Antwort weiter an der Aufgabe. 👍"
            self.kzg.add("assistant", response)
            self._persist_msg("assistant", response)
            BUS.emit("response", response)
            self._resume_idle()
            return
        # ───────────────────────────────────────────────────────────────────────

        # ── Alpha Progression Auto-Import ──────────────────────────────────────
        from domains import alphaprogression as _ap
        _ap_url = _ap.extract_link(msg.text)
        if _ap_url:
            BUS.emit("thinking", "Alpha Progression wird importiert…")
            try:
                import asyncio as _asyncio
                loop = _asyncio.get_running_loop()
                response = await loop.run_in_executor(None, _ap.fetch_and_log, _ap_url)
            except Exception as _e:
                log.error(f"AP import error: {_e}")
                response = f"❌ Fehler beim Importieren: {_e}"
            self.kzg.add("assistant", response)
            self._persist_msg("assistant", response)
            BUS.emit("response", response)
            # Task-Vorschlag nach Workout-Import
            if "✅" in response:
                asyncio.create_task(self._suggest_from_event(f"Neues Workout eingetragen: {response[:120]}"))
            return
        # ───────────────────────────────────────────────────────────────────────

        # Kontext bauen
        system = await self._build_system_prompt(msg.text)

        # Streaming vorbereiten
        stream_cb, finalize = await self._make_stream()

        allowed = skills.T.select_tools(msg.text)
        model = self.agent.model_name
        # force_tools=True wenn Tools vorhanden UND Aktionswort erkannt
        force_tools = bool(allowed) and skills.T.is_action(msg.text)
        try:
            response, trace = await self.agent.run(
                messages=self.kzg.recent_messages(max_tokens=3000),
                system=system,
                stream_cb=stream_cb,
                allowed_tools=allowed,
                force_tools=force_tools,
                temperature=0.75,
                max_tokens=1500,
            )
        except Exception as e:
            log.error(f"Agent-Fehler: {e}")
            response, trace = "⚠️ Technisches Problem, versuch es nochmal.", []

        if not response:
            response = "…"
        await finalize(response)

        self.kzg.add("assistant", response)
        self._persist_msg("assistant", response, channel="telegram",
                          meta={"tools": [t["tool"] for t in trace], "model": model})
        elapsed = time.time() - t0
        log.info(f"Antwort in {elapsed:.1f}s ({len(trace)} Tools, {model})")
        BUS.emit("idle", "Bereit", detail=f"{elapsed:.1f}s · {model}")

        # Hintergrund: Lernen
        tools_used = [t["tool"] for t in trace]
        asyncio.create_task(self._post_turn(msg.text, response))
        # Trigger für Task-Vorschlag bei relevanten Tool-Nutzungen
        trigger_tools = {"create_habit", "create_task", "create_goal", "add_event", "log_workout"}
        if any(t in trigger_tools for t in tools_used):
            asyncio.create_task(self._suggest_from_event(
                f"Alfred hat gerade '{', '.join(t for t in tools_used if t in trigger_tools)}' ausgeführt: {msg.text[:120]}"
            ))
        self._resume_idle()

    async def dashboard_respond(self, text: str, stream_cb=None) -> tuple[str, list]:
        """Verarbeitet eine Chat-Nachricht aus dem Dashboard (teilt Gedächtnis mit Telegram)."""
        self._last_user_ts = time.time()
        self.kzg.add("user", text)
        self._persist_msg("user", text, channel="dashboard")

        # ── Alpha Progression Auto-Import ──────────────────────────────────────
        from domains import alphaprogression as _ap
        _ap_url = _ap.extract_link(text)
        if _ap_url:
            BUS.emit("thinking", "Alpha Progression wird importiert…")
            try:
                import asyncio as _asyncio
                loop = _asyncio.get_running_loop()
                response = await loop.run_in_executor(None, _ap.fetch_and_log, _ap_url)
            except Exception as _e:
                log.error(f"AP import error: {_e}")
                response = f"❌ Fehler beim Importieren: {_e}"
            self.kzg.add("assistant", response)
            self._persist_msg("assistant", response, channel="dashboard")
            BUS.emit("response", response)
            return response, []
        # ───────────────────────────────────────────────────────────────────────

        system = await self._build_system_prompt(text)
        allowed = skills.T.select_tools(text)
        model = self.agent.model_name
        force_tools = bool(allowed) and skills.T.is_action(text)
        try:
            response, trace = await self.agent.run(
                messages=self.kzg.recent_messages(max_tokens=3000), system=system,
                stream_cb=stream_cb, allowed_tools=allowed,
                force_tools=force_tools,
                temperature=0.75, max_tokens=1500,
            )
        except Exception as e:
            log.error(f"Dashboard-Agent-Fehler: {e}")
            response, trace = "⚠️ Technisches Problem.", []
        self.kzg.add("assistant", response)
        self._persist_msg("assistant", response, channel="dashboard",
                          meta={"tools": [t["tool"] for t in trace], "model": model})
        asyncio.create_task(self._post_turn(text, response))
        return response, trace

    async def _post_turn(self, user_text: str, response: str) -> None:
        # Per-Turn: gezielte Fakten-Extraktion aus dem letzten Austausch (Fast-Modell)
        BUS.emit("learning", "Analysiere Gespräch…")
        n = await self.extractor.extract_from_exchange(user_text, response)
        if n > 0:
            BUS.emit("memory", f"🧠 {n} neue{'r' if n == 1 else ''} Fakt{'' if n == 1 else 'en'} gespeichert")
            # Neue Fakten/Ziele → Task-Vorschlag
            asyncio.create_task(self._suggest_from_event(
                f"Neue Information über Timo: {user_text[:100]}"
            ))
        else:
            BUS.emit("idle", "Bereit")

    async def _suggest_from_event(self, trigger: str) -> None:
        """Generiert einen Task-Vorschlag aus einem Datenereignis (fire & forget)."""
        try:
            from domains.task_executor import suggest_one
            await suggest_one(trigger, self.bg_llm, self.lzg)
        except Exception as e:
            log.debug(f"suggest_from_event: {e}")

    # ── Streaming-Helfer ───────────────────────────────────────────────────────

    async def _make_stream(self):
        """Liefert (stream_cb, finalize). stream_cb kann None sein (kein Streaming)."""
        if not getattr(self.channel, "supports_streaming", False):
            await self.channel.send_typing()
            async def finalize_plain(text):
                await self.channel.send(text)
            return None, finalize_plain

        msg_id = await self.channel.start_message("💭 …")
        last_edit = [0.0]

        async def stream_cb(full: str):
            now = time.time()
            if now - last_edit[0] < 0.8:   # Telegram-Edit-Ratelimit schonen
                return
            last_edit[0] = now
            await self.channel.edit_message(msg_id, full)

        async def finalize(text: str):
            # Markdown-Finale mit Fallback
            await self.channel.edit_message(msg_id, text, markdown=True)

        return stream_cb, finalize

    # ── Idle / Autopilot-Loop ──────────────────────────────────────────────────

    def _resume_idle(self) -> None:
        self._state = "idle"
        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()
        self._idle_task = asyncio.create_task(self._autopilot_loop())

    async def _autopilot_loop(self) -> None:
        await asyncio.sleep(20)   # Startup setteln lassen (Warmup etc.)
        while self._state == "idle":
            try:
                thermal_state = self.thermal.get_state()
                if thermal_state.paused:
                    await self.thermal.wait_until_cool()
                    continue
            except Exception as e:
                log.debug(f"Thermal-Check: {e}", exc_info=True)

            try:
                await self.autopilot.tick()
            except Exception as e:
                log.debug(f"Autopilot-Tick: {e}", exc_info=True)

            # Wartung nur wenn Timo nicht aktiv ist (Modell freihalten)
            if not self._user_active():
                # Tages-Reflexion (gated, 1x/Tag intern)
                try:
                    await self.reflection.daily_reflection()
                except Exception as e:
                    log.debug(f"Reflexion: {e}", exc_info=True)
                # Memory-Wartung max 1x/Stunde:
                # Nur noch Vektor-Dedup (kein LLM-Compressor → kein Halluzinationsrisiko)
                now = datetime.now()
                if (self._last_consolidation is None or
                        (now - self._last_consolidation).total_seconds() > 3600):
                    self._last_consolidation = now
                    try:
                        await self.consolidator.consolidate_silent()
                    except Exception as e:
                        log.debug(f"Consolidator: {e}", exc_info=True)
                    try:
                        stats = await self.forgetting.run()
                        if stats["forgotten"] or stats["chat_pruned"]:
                            log.info(f"🕐 Forgetting: {stats}")
                    except Exception as e:
                        log.debug(f"ForgettingCurve: {e}", exc_info=True)
                    # Tägliches DB-Backup (gated, läuft intern nur 1x/Tag)
                    try:
                        from core import backup as _backup
                        await asyncio.to_thread(_backup.maybe_run_daily)
                    except Exception as e:
                        log.debug(f"Backup: {e}", exc_info=True)
                    # Health aus iCloud nachziehen: stündlich, oder alle 15min wenn heute fehlt
                    try:
                        now_h = datetime.now()
                        today_missing = not db.query_one(
                            "SELECT 1 FROM health_data WHERE date=CURRENT_DATE AND steps IS NOT NULL LIMIT 1"
                        )
                        health_interval = 900 if today_missing else 3600
                        since_last = (now_h - self._last_health_refresh).total_seconds() if self._last_health_refresh else health_interval + 1
                        if since_last >= health_interval:
                            self._last_health_refresh = now_h
                        new_days = await asyncio.to_thread(self._dashboard.refresh_health) if since_last >= health_interval else 0
                        if new_days and self._proactive_tracker.can_send_data_event():
                            # Neue Gesundheitsdaten → proaktive Nachricht + Task-Vorschlag
                            thought = await self._proactive_engine.generate()
                            if thought and await self._proactive_engine.evaluate(thought):
                                await self.autopilot._send(thought, kind="health_update")
                                self._proactive_tracker.record_sent()
                            # Task-Vorschlag aus Health-Daten (max 1x/24h)
                            _since_last_sug = (
                                (now_h - self._last_health_suggestion).total_seconds()
                                if self._last_health_suggestion else 86401
                            )
                            if _since_last_sug > 86400:
                                try:
                                    from domains.task_executor import suggest_one
                                    ok = await suggest_one(
                                        f"Neue Gesundheitsdaten für {new_days} Tag(e) importiert",
                                        self.bg_llm, self.lzg
                                    )
                                    if ok:
                                        self._last_health_suggestion = now_h
                                except Exception as _e:
                                    log.debug(f"Health-Suggestion: {_e}")
                    except Exception as e:
                        log.debug(f"Health-Refresh: {e}", exc_info=True)

                # Pattern-Erkennung 1x täglich (86400s)
                now_p = datetime.now()
                if (self._last_pattern_run is None or
                        (now_p - self._last_pattern_run).total_seconds() > 86400):
                    self._last_pattern_run = now_p
                    try:
                        n = await pattern_detector.update_memories(self.lzg, self.bg_llm)
                        if n:
                            log.info(f"🔍 Pattern Detector: {n} neue Muster gespeichert")
                    except Exception as e:
                        log.debug(f"Pattern Detector: {e}", exc_info=True)

                # Insight-Engine: alle 4h wenn keine aktiven Alfred-Tasks
                now_i = datetime.now()
                _since_insight = (
                    (now_i - self._last_insight_run).total_seconds()
                    if self._last_insight_run else 14401
                )
                if _since_insight > 14400:
                    has_active = db.query(
                        "SELECT 1 FROM tasks WHERE assigned_to='alfred' AND status NOT IN ('done','archived') "
                        "AND (suggestion_status IS NULL OR suggestion_status='accepted') LIMIT 1"
                    )
                    if not has_active:
                        self._last_insight_run = now_i
                        try:
                            from domains.insight_engine import generate_insight_task
                            await generate_insight_task(self.bg_llm, self.lzg)
                        except Exception as e:
                            log.debug(f"Insight-Engine: {e}", exc_info=True)

            # Adaptiver Takt: kürzer wenn Alfred gerade an Tasks arbeitet
            try:
                nxt = self._reminders.next_due_seconds()
            except Exception as e:
                log.debug(f"Reminder-next_due: {e}", exc_info=True)
                nxt = None
            # Aktive Alfred-Task? → 8s Takt statt 60s
            from core import db as _db
            has_active_task = _db.query(
                "SELECT 1 FROM tasks WHERE assigned_to='alfred' AND status='in_progress' AND execution_phase IN ('executing','finalizing') LIMIT 1"
            )
            if has_active_task:
                delay = 8
            else:
                delay = 60 if nxt is None else max(5, min(60, nxt + 1))
            await asyncio.sleep(delay)

    # ── Persistenz ──────────────────────────────────────────────────────────────

    def _persist_msg(self, role: str, content: str, channel: str = "telegram",
                     meta: dict | None = None) -> None:
        try:
            self.lzg.save_kzg_turn(role, content)
        except Exception:
            pass
        try:
            db.execute(
                "INSERT INTO chat_messages (role, content, channel, meta) VALUES (%s,%s,%s,%s)",
                (role, content, channel, json.dumps(meta or {})),
            )
        except Exception:
            pass

    # ── Start / Stop ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        log.info("Orchestrator startet...")
        try:
            self.lzg.setup()
            self._reminders.setup()
            db.run_migrations()
            log.info("Datenbank bereit")
        except Exception as e:
            log.error(f"DB-Fehler: {e}")

        # Health frisch aus iCloud Health.json ziehen (direkt von der Quelle)
        try:
            self._dashboard.refresh_health()
        except Exception as e:
            log.debug(f"Health-Refresh beim Start: {e}")

        # Skills binden
        skills.bind(SkillContext(
            lzg=self.lzg, llm=self.bg_llm, search=self._search,
            reminders=self._reminders, dashboard=self._dashboard,
            channel=self.channel,
        ))

        # Dynamisch erstellte Skills aus vorherigen Sessions wieder aktivieren
        try:
            from core.skill_factory import load_all_on_startup
            load_all_on_startup()
        except Exception as e:
            log.error(f"Dynamische Skills konnten nicht geladen werden: {e}")

        # KZG aus letzter Session
        try:
            past = self.lzg.load_recent_kzg(max_turns=config.KZG_MAX_TURNS)
            for t in past:
                self.kzg.add(t["role"], t["content"])
            if past:
                log.info(f"🔄 {len(past)} Turns wiederhergestellt")
                self.lzg.clear_kzg_sessions(keep_last=config.KZG_MAX_TURNS * 2)
        except Exception as e:
            log.warning(f"KZG-Wiederherstellung: {e}")

        # Memories-Übersicht
        try:
            mems = self.lzg.get_all(limit=20)
            if mems:
                log.info(f"🧠 {len(mems)} Erinnerungen, {len(skills.T.REGISTRY)} Tools")
        except Exception:
            pass

        if isinstance(self.llm, OllamaProvider):
            await self.llm.pull_if_missing()

        # Modelle aufwärmen (parallel) – vermeidet Cold-Start.
        asyncio.create_task(self.agent.warmup())
        asyncio.create_task(fast.warmup())

        self.channel.on_message(self.handle_message)

        self._idle_task = asyncio.create_task(self._autopilot_loop())
        await self.channel.start()
        log_event("system", "Alfred gestartet")
        log.info("Alfred bereit ✅")

    async def stop(self) -> None:
        self._state = "stopping"
        if self._idle_task:
            self._idle_task.cancel()
        try:
            self.lzg.close()
        except Exception:
            pass
        try:
            self._dashboard.close()
        except Exception:
            pass
        try:
            db.close_pool()
        except Exception:
            pass
        log_event("system", "Alfred gestoppt")
        log.info("Orchestrator gestoppt")
