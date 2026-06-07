"""
Orchestrator – Herzstück von Jarvis 2.0.
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
from memory.kzg import KZG
from memory.lzg import LZG
from memory.compressor import Compressor
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
from tools.dashboard import DashboardReader
from tools.reminders import ReminderStore
from tools.router import pick_model
from core.status import BUS
import config

log = logging.getLogger(__name__)


def _load_identity() -> str:
    """Lädt die generische Identität und füllt persönliche Platzhalter aus .env."""
    text = (Path(__file__).parent / "identity" / "jarvis.md").read_text()
    text = text.replace("{{OWNER}}", config.OWNER_NAME)
    text = text.replace("{{TIMEZONE}}", config.OWNER_TIMEZONE)
    if config.OWNER_EMAIL:
        text += f"\n- Kontakt: {config.OWNER_EMAIL}\n"
    return text


IDENTITY = _load_identity()


class Orchestrator:
    def __init__(self, llm: LLMProvider, channel: CommunicationChannel,
                 lzg: LZG, thermal: ThermalMonitor):
        self.llm     = llm
        self.channel = channel
        self.lzg     = lzg
        self.thermal = thermal

        self.kzg          = KZG()
        self.kg           = KnowledgeGraph()
        self.compressor   = Compressor(llm=llm, kzg=self.kzg, lzg=self.lzg)
        self.consolidator = Consolidator(llm=llm, lzg=self.lzg)
        self.forgetting   = ForgettingCurve()
        self.extractor    = MemoryExtractor(llm_provider=llm, lzg=self.lzg, kg=self.kg)
        self.reflection   = Reflection(llm=llm, lzg=self.lzg)
        self.agent        = Agent(max_steps=8)   # längere Tool-Ketten erlauben

        self._search    = WebSearch()
        self._dashboard = DashboardReader()
        self._reminders = ReminderStore()

        self._proactive_tracker = ProactiveTracker()
        self._proactive_engine  = ProactiveEngine(llm=llm, lzg=lzg, claude=None)

        self._llm_lock = asyncio.Lock()       # serialisiert schwere LLM-Last
        self._last_user_ts = 0.0              # Zeitpunkt letzter User-Interaktion

        self.autopilot = Autopilot(
            llm=llm, lzg=lzg, dashboard=self._dashboard, reminders=self._reminders,
            channel=channel, proactive=self._proactive_engine,
            tracker=self._proactive_tracker, identity=IDENTITY,
            lock=self._llm_lock, is_user_active=self._user_active,
        )

        self._state = "idle"
        self._last_consolidation: datetime | None = None
        self._last_compress: datetime | None = None
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
            from core import db as _db
            for m in mems:
                try:
                    _db.execute(
                        "UPDATE memories SET recall_count = recall_count + 1, last_recalled = NOW() WHERE id = %s",
                        (m.id,),
                    )
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
                embedding = await self.llm.embed(user_text)
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

        # Kontext bauen
        system = await self._build_system_prompt(msg.text)

        # Streaming vorbereiten
        stream_cb, finalize = await self._make_stream()

        allowed = skills.T.select_tools(msg.text)
        model, keep_alive = pick_model(msg.text)
        try:
            async with self._llm_lock:
                response, trace = await self.agent.run(
                    messages=self.kzg.recent_messages(max_tokens=3000),
                    system=system,
                    stream_cb=stream_cb,
                    allowed_tools=allowed,
                    temperature=0.75,
                    max_tokens=1500,
                    model=model,
                    keep_alive=keep_alive,
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
        asyncio.create_task(self._post_turn(msg.text, response))
        self._resume_idle()

    async def dashboard_respond(self, text: str, stream_cb=None) -> tuple[str, list]:
        """Verarbeitet eine Chat-Nachricht aus dem Dashboard (teilt Gedächtnis mit Telegram)."""
        self._last_user_ts = time.time()
        self.kzg.add("user", text)
        self._persist_msg("user", text, channel="dashboard")
        system = await self._build_system_prompt(text)
        allowed = skills.T.select_tools(text)
        model, keep_alive = pick_model(text)
        try:
            async with self._llm_lock:
                response, trace = await self.agent.run(
                    messages=self.kzg.recent_messages(max_tokens=3000), system=system,
                    stream_cb=stream_cb, allowed_tools=allowed,
                    temperature=0.75, max_tokens=1500,
                    model=model, keep_alive=keep_alive,
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
        else:
            BUS.emit("idle", "Bereit")

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
                    # Health stündlich aus iCloud nachziehen (billig, Datei ~2KB)
                    try:
                        await asyncio.to_thread(self._dashboard.refresh_health)
                    except Exception as e:
                        log.debug(f"Health-Refresh: {e}", exc_info=True)

            # Adaptiver Takt: bis kurz vor den nächsten Reminder schlafen (max 60s)
            try:
                nxt = self._reminders.next_due_seconds()
            except Exception as e:
                log.debug(f"Reminder-next_due: {e}", exc_info=True)
                nxt = None
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
            lzg=self.lzg, llm=self.llm, search=self._search,
            reminders=self._reminders, dashboard=self._dashboard,
        ))

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
        # Bei Routing das residente schnelle Modell warm halten (nicht den Fallback).
        warm_model = config.AGENT_MODEL_FAST if config.LLM_ROUTING else None
        asyncio.create_task(self.agent.warmup(warm_model))
        asyncio.create_task(fast.warmup())

        self.channel.on_message(self.handle_message)

        self._idle_task = asyncio.create_task(self._autopilot_loop())
        await self.channel.start()
        log_event("system", "Jarvis gestartet")
        log.info("Jarvis bereit ✅")

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
        log_event("system", "Jarvis gestoppt")
        log.info("Orchestrator gestoppt")
