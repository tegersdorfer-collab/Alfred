"""API für den News-Globus: geolokalisierte News + Ortssuche.

`/api/globe/news`  → gecachte, verortete Meldungen (schnell, kein Live-Fetch).
`/api/geo/search`  → Nominatim-Ortssuche (für das Suchfeld / Globus-Anflug).
"""
import logging

from fastapi import APIRouter

from core import news_globe
from tools.geo import nominatim

log = logging.getLogger("mantis.api")


def build_router(orch=None) -> APIRouter:
    router = APIRouter()

    @router.get("/api/globe/news")
    async def globe_news():
        return {"items": news_globe.cached_geo()}

    @router.get("/api/geo/search")
    async def geo_search(q: str = ""):
        return {"results": await nominatim.search(q, limit=5)}

    return router
