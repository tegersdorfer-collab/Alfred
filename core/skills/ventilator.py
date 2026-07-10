"""Ventilator-Steuerung per Flipper-IR — klont das Lampen-Muster.

Registriert sich via @T.register beim Import. Die IR-Codes werden vom User später
per Flipper 'ir rx' aufgenommen und in tools/flipper/remotes.json unter 'ventilator'
eingetragen (learned: true). Solange nicht angelernt → freundliche Hinweis-Meldung,
kein Sendeversuch.
"""
import asyncio
import logging

from core import tools as T
from tools.flipper.manager import MANAGER, load_remotes

log = logging.getLogger("core.skills")

# Eingabe-Normalisierung → Signalname in remotes.json
_ALIASES = {
    "an": "an", "ein": "an", "anmachen": "an", "einschalten": "an", "on": "an",
    "aus": "aus", "ausmachen": "aus", "ausschalten": "aus", "off": "aus",
    "staerker": "staerker", "stärker": "staerker", "schneller": "staerker",
    "hoch": "staerker", "mehr": "staerker", "höher": "staerker",
    "schwaecher": "schwaecher", "schwächer": "schwaecher", "langsamer": "schwaecher",
    "runter": "schwaecher", "weniger": "schwaecher", "niedriger": "schwaecher",
}

_EMOJI = {"an": "🌀 Ventilator an", "aus": "⏹️ Ventilator aus",
          "staerker": "💨 stärker", "schwaecher": "🍃 schwächer"}

_NOT_LEARNED = (
    "🛠 Ventilator-IR ist noch nicht angelernt. Nimm die Codes per Flipper 'ir rx' auf "
    "und trag sie in tools/flipper/remotes.json unter 'ventilator' ein (learned: true). "
    "Danach steuere ich an/aus/stärker/schwächer ohne weiteren Code-Change."
)


def _is_learned() -> bool:
    r = load_remotes().get("ventilator") or {}
    if r.get("learned") is False:
        return False
    sigs = r.get("signals") or {}
    return any((s.get("command") or "").strip() for s in sigs.values())


@T.register(
    "ventilator",
    "Steuert Timos Ventilator per Infrarot über den Flipper Zero: an/aus und stärker/schwächer "
    "(Geschwindigkeit). Nutze dies, wenn Timo den Ventilator/Lüfter schalten oder die Stufe "
    "ändern will. 'schritte' wiederholt stärker/schwächer.",
    {
        "action": {
            "type": "string",
            "enum": ["an", "aus", "staerker", "schwaecher"],
            "description": "an/aus = schalten, staerker/schwaecher = Geschwindigkeit ändern",
        },
        "schritte": {
            "type": "integer",
            "description": "nur für staerker/schwaecher: wie viele Stufen (Standard 1, max 10)",
        },
    },
    ["action"],
    "flipper",
)
async def _ventilator(action: str, schritte: int = 1):
    sig = _ALIASES.get((action or "").strip().lower())
    if sig is None:
        return ("❌ Unbekannte Ventilator-Aktion. Möglich: an, aus, staerker (schneller), "
                "schwaecher (langsamer).")
    if not _is_learned():
        return _NOT_LEARNED
    reps = 1
    if sig in ("staerker", "schwaecher"):
        reps = max(1, min(10, int(schritte or 1)))
    try:
        for i in range(reps):
            await MANAGER.send_named("ventilator", sig)
            if i + 1 < reps:
                await asyncio.sleep(0.18)
    except Exception as e:
        log.warning("ventilator fehlgeschlagen: %s", e)
        return f"❌ Ventilator nicht erreichbar: {e}. Hängt der Flipper per USB am Mac?"
    label = _EMOJI.get(sig, sig)
    return f"{label} (×{reps})" if reps > 1 else label
