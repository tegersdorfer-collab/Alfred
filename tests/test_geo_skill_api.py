"""Tests für Geo-Skill-Tools (core/skills/geo.py) + Globus-API (web/routers/globe.py).

Backends gemockt; die API wird über den FastAPI-TestClient geprüft.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import news_globe
from tools.geo import nominatim


# ── Skill-Tools ───────────────────────────────────────────────────────────────

def test_where_is_found():
    async def fake_geocode(o):
        return {"lat": 35.0116, "lon": 135.7681, "display_name": "Kyoto, Japan"}
    nominatim.geocode = fake_geocode
    from core.skills.geo import _where_is
    out = asyncio.run(_where_is("Kyoto"))
    assert "Kyoto" in out and "35.0116" in out


def test_where_is_not_found():
    async def none_geocode(o):
        return None
    nominatim.geocode = none_geocode
    from core.skills.geo import _where_is
    assert "🤷" in asyncio.run(_where_is("Blafasel"))


def test_news_briefing_lists_headlines():
    news_globe.cached = lambda: [
        {"title": "Beben in Tokio", "place": "Tokio", "source": "Tagesschau"},
        {"title": "Wahl in Paris", "place": "Paris", "source": "Reuters"},
    ]
    from core.skills.geo import _news_briefing
    out = asyncio.run(_news_briefing())
    assert "Beben in Tokio" in out and "[Tokio]" in out and "Tagesschau" in out


def test_news_briefing_empty():
    news_globe.cached = lambda: []
    from core.skills.geo import _news_briefing
    assert "Noch keine News" in asyncio.run(_news_briefing())


# ── API-Router ────────────────────────────────────────────────────────────────

def _client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from web.routers import globe
    app = FastAPI()
    app.include_router(globe.build_router(None))
    return TestClient(app)


def test_api_globe_news_returns_cache():
    news_globe.cached_geo = lambda: [{"title": "X", "lat": 1.0, "lon": 2.0}]
    r = _client().get("/api/globe/news")
    assert r.status_code == 200
    assert r.json()["items"][0]["lat"] == 1.0


def test_api_geo_search():
    async def fake_search(q, limit=5):
        return [{"lat": 48.85, "lon": 2.35, "display_name": "Paris", "type": "city"}]
    nominatim.search = fake_search
    r = _client().get("/api/geo/search", params={"q": "Paris"})
    assert r.status_code == 200
    assert r.json()["results"][0]["display_name"] == "Paris"
