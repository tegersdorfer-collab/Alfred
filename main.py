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
    ║         J A R V I S           ║
    ║   Persönlicher AI-Begleiter   ║
    ╚═══════════════════════════════╝
    """)

    if not __import__("config").TELEGRAM_BOT_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN nicht gesetzt in .env")
        sys.exit(1)

    from llm.local import OllamaProvider
    from memory.lzg import LZG
    from communication.telegram import TelegramChannel
    from thermal import ThermalMonitor
    from orchestrator import Orchestrator

    llm         = OllamaProvider()
    lzg         = LZG()
    thermal     = ThermalMonitor()
    channel     = TelegramChannel()
    orchestrator = Orchestrator(llm=llm, channel=channel, lzg=lzg, thermal=thermal)

    # Dashboard-API im selben Prozess (geteilter State mit dem Agent)
    import uvicorn
    from web.api import create_app
    api_app = create_app(orchestrator)
    api_conf = uvicorn.Config(api_app, host="0.0.0.0", port=7779, log_level="warning")
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
    log.info("🖥️  Dashboard läuft auf http://localhost:7779")
    await stop_event.wait()


if __name__ == "__main__":
    asyncio.run(main())
