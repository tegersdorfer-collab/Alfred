"""
Alfred – Entry Point
"""
import asyncio
import logging
import os
import signal
import sys

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("alfred")


def ensure_single_instance():
    pidfile = "/tmp/alfred.pid"
    if os.path.exists(pidfile):
        try:
            old_pid = int(open(pidfile).read().strip())
            os.kill(old_pid, 0)
            log.error(f"Alfred läuft bereits (PID {old_pid}). Beende mit: kill {old_pid}")
            sys.exit(1)
        except (ProcessLookupError, ValueError, OSError):
            pass  # Alter Prozess tot
    open(pidfile, "w").write(str(os.getpid()))
    import atexit
    atexit.register(lambda: os.unlink(pidfile) if os.path.exists(pidfile) else None)


async def main():
    ensure_single_instance()

    print("""
    ╔═══════════════════════════════╗
    ║         A L F R E D           ║
    ║   Persönlicher AI-Begleiter   ║
    ╚═══════════════════════════════╝
    """)

    if not __import__("config").TELEGRAM_BOT_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN nicht gesetzt in .env")
        sys.exit(1)

    import config as cfg
    from llm.local import OllamaProvider
    from memory.lzg import LZG
    from communication.telegram import TelegramChannel
    from thermal import ThermalMonitor
    from orchestrator import Orchestrator

    # ── Chat-LLM: Haiku für schnelle Echtzeit-Antworten im Chat ─────────────
    if cfg.ANTHROPIC_API_KEY:
        from llm.claude import ClaudeProvider
        chat_llm = ClaudeProvider(model=cfg.CLAUDE_CHAT_MODEL)
        log.info(f"💬 Chat-LLM: {cfg.CLAUDE_CHAT_MODEL}")
    else:
        chat_llm = OllamaProvider()
        log.info(f"💬 Chat-LLM: Ollama {cfg.OLLAMA_MODEL} (kein API-Key)")

    # ── Agent-Backend: Haiku (user-facing Chat + Tool-Calls) ────────────────────
    if cfg.ANTHROPIC_API_KEY:
        from core.backends.claude import ClaudeBackend
        agent_backend = ClaudeBackend(model=cfg.CLAUDE_CHAT_MODEL)
        log.info(f"🔧 Agent-Backend: {cfg.CLAUDE_CHAT_MODEL} (Haiku, user-facing)")
    else:
        from core.backends.ollama import OllamaBackend
        agent_backend = OllamaBackend()
        log.info(f"🔧 Agent-Backend: Ollama ({cfg.AGENT_MODEL_STRONG}, Fallback)")

    # ── Background-LLM: Ollama (proaktiv, Briefing, Reflexion) ────────────────
    bg_llm = OllamaProvider()
    log.info(f"🧠 Background-LLM: Ollama {cfg.OLLAMA_MODEL}")

    # ── Embed-LLM: immer Ollama (kein Embedding via Claude) ───────────────────
    embed_llm = OllamaProvider()

    lzg     = LZG()
    thermal = ThermalMonitor()
    channel = TelegramChannel()
    orchestrator = Orchestrator(
        chat_llm=chat_llm, bg_llm=bg_llm, embed_llm=embed_llm,
        agent_backend=agent_backend,
        channel=channel, lzg=lzg, thermal=thermal,
    )

    # Dashboard-API im selben Prozess (geteilter State mit dem Agent).
    # Bindet NUR auf die Tailscale-IP – im normalen LAN/WLAN unsichtbar, kein
    # App-Token mehr nötig (PWA-Homescreen-Start_url kann so fix "/" bleiben).
    # Fällt auf localhost zurück falls Tailscale gerade nicht läuft (z.B. Debug).
    import socket as _socket
    import uvicorn
    from web.api import create_app

    def _local_ips() -> set[str]:
        ips = set()
        try:
            for info in _socket.getaddrinfo(_socket.gethostname(), None):
                ips.add(info[4][0])
        except Exception:
            pass
        try:
            import subprocess as _sp
            out = _sp.run(["ifconfig"], capture_output=True, text=True, timeout=3).stdout
            ips.update(_re.findall(r"inet (\d+\.\d+\.\d+\.\d+)", out))
        except Exception:
            pass
        return ips

    import re as _re
    dashboard_host = cfg.DASHBOARD_HOST
    if dashboard_host not in _local_ips():
        log.warning(f"⚠️  Tailscale-IP {dashboard_host} nicht aktiv – Dashboard bindet auf localhost (nur diese Maschine).")
        dashboard_host = "127.0.0.1"

    api_app = create_app(orchestrator)
    api_conf = uvicorn.Config(api_app, host=dashboard_host, port=7779, log_level="warning")
    api_server = uvicorn.Server(api_conf)

    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    async def shutdown():
        log.info("Fährt herunter...")
        await orchestrator.stop()
        await channel.stop()
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))

    await orchestrator.start()
    asyncio.create_task(api_server.serve())
    log.info(f"🖥️  Dashboard läuft auf http://{dashboard_host}:7779")
    await stop_event.wait()


if __name__ == "__main__":
    asyncio.run(main())
