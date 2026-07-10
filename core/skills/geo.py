"""Geo- & News-Tools für den Agenten — Ortssuche und Welt-Briefing.

Nutzt Nominatim (Geocoding) und den News-Globus-Cache. Registriert sich via
@T.register beim Import (durch core/skills/__init__.py).
"""
import logging

from core import news_globe
from core import tools as T
from tools.geo import nominatim

log = logging.getLogger("core.skills")


@T.register(
    "where_is",
    "Findet einen Ort (Stadt, Land, Sehenswürdigkeit) und gibt Region + Koordinaten "
    "zurück. Nutze dies für 'wo ist/liegt X?' oder wenn eine Position gebraucht wird.",
    {"ort": {"type": "string", "description": "Ortsname, z.B. 'Kyoto' oder 'Eiffelturm'"}},
    ["ort"],
    "geo",
)
async def _where_is(ort: str):
    geo = await nominatim.geocode(ort)
    if not geo:
        return f"🤷 ‚{ort}' konnte ich nicht finden."
    return f"📍 {geo['display_name']} ({geo['lat']:.4f}, {geo['lon']:.4f})"


@T.register(
    "news_briefing",
    "Fasst die aktuellen Nachrichten zusammen — 'was ist in der Welt los'. Liest die "
    "geolokalisierten Schlagzeilen des News-Globus.",
    {},
    [],
    "geo",
)
async def _news_briefing():
    items = news_globe.cached()
    if not items:
        return "📰 Noch keine News geladen — der News-Globus aktualisiert sich in Kürze."
    lines = []
    for it in items[:8]:
        loc = f" [{it['place']}]" if it.get("place") else ""
        src = f" — {it['source']}" if it.get("source") else ""
        lines.append(f"• {it['title']}{loc}{src}")
    return "📰 Aktuelle Schlagzeilen:\n" + "\n".join(lines)
