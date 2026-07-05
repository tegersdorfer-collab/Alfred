"""
Screen-Context-Awareness — Alfred kann sich einen Screenshot machen und
beschreiben lassen, um kontextbezogen zu helfen (z.B. "was siehst du gerade
auf meinem Bildschirm?", "hilf mir bei diesem Fehler").

Nutzt macOS' eingebautes `screencapture` (kein Zusatz-Paket nötig) + das
bereits bestehende Ollama-Vision-Modell aus core/vision.py (dasselbe, das
Telegram-Fotos beschreibt).
"""
import asyncio
import logging
import subprocess
import tempfile
from pathlib import Path

from core import tools as T
from core.vision import describe_image

log = logging.getLogger("core.skills")

_SCREENCAPTURE_BIN = "/usr/sbin/screencapture"  # nicht per PATH suchen — launchd-Prozesse
                                                  # haben /usr/sbin oft nicht im PATH

_SCREEN_PROMPT = (
    "Beschreibe kurz auf Deutsch, was auf diesem Bildschirmfoto zu sehen ist — "
    "welche App(s) offen sind, worum es inhaltlich geht, und falls ein Fehler/"
    "eine Fehlermeldung sichtbar ist, gib sie möglichst genau wieder."
)


@T.register("see_screen",
    "Macht einen Screenshot von Timos Bildschirm und beschreibt was darauf zu sehen ist. "
    "Nutze dies wenn Timo fragt was du gerade siehst, oder wenn er Hilfe zu etwas auf dem "
    "Bildschirm braucht (z.B. einer Fehlermeldung, einem Dokument, einer App).",
    {}, [], "vision")
async def _see_screen() -> str:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        path = tmp.name
    try:
        result = await asyncio.to_thread(
            subprocess.run, [_SCREENCAPTURE_BIN, "-x", path], capture_output=True,
        )
        if result.returncode != 0:
            err = (result.stderr or b"").decode(errors="replace")
            if "could not create image from display" in err:
                return (
                    "FEHLER: Keine Bildschirmaufnahme-Berechtigung. Bitte in "
                    "Systemeinstellungen → Privacy & Security → Bildschirmaufnahme "
                    "den Alfred-Prozess (Python) erlauben und Alfred neu starten."
                )
            return f"FEHLER: Screenshot fehlgeschlagen: {err}"
        image_bytes = Path(path).read_bytes()
        return await describe_image(image_bytes, _SCREEN_PROMPT)
    finally:
        Path(path).unlink(missing_ok=True)
