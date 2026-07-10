"""Tests für den OSM-Nominatim-Client (tools/geo/nominatim.py) — ohne Netz.

Gemockt wird _http_get (die einzige HTTP-Grenze). Geprüft: Parsing, Cache-Treffer
ohne erneuten Call, None bei keinem Treffer.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.geo import nominatim


def _setup(rows):
    """Frischer Cache, persist deaktiviert, _http_get liefert 'rows' und zählt Calls."""
    nominatim._cache = {}
    nominatim._save_cache = lambda: None
    calls = []

    async def fake_get(params):
        calls.append(params)
        return rows
    nominatim._http_get = fake_get
    return calls


def test_geocode_parses_first_result():
    _setup([{"lat": "52.52", "lon": "13.405", "display_name": "Berlin, Deutschland", "type": "city"}])
    res = asyncio.run(nominatim.geocode("Berlin"))
    assert res == {"lat": 52.52, "lon": 13.405, "display_name": "Berlin, Deutschland"}


def test_geocode_uses_cache_second_time():
    calls = _setup([{"lat": "48.14", "lon": "11.58", "display_name": "München", "type": "city"}])
    asyncio.run(nominatim.geocode("München"))
    asyncio.run(nominatim.geocode("münchen"))   # gleicher Ort, andere Groß/Klein
    assert len(calls) == 1                        # zweiter Aufruf aus dem Cache


def test_geocode_no_result_is_none():
    _setup([])
    assert asyncio.run(nominatim.geocode("Blablasdfstadt")) is None


def test_search_returns_list():
    _setup([
        {"lat": "40.7", "lon": "-74.0", "display_name": "New York, USA", "type": "city"},
        {"lat": "53.5", "lon": "-2.2", "display_name": "New York, England", "type": "hamlet"},
    ])
    res = asyncio.run(nominatim.search("New York", limit=2))
    assert len(res) == 2
    assert res[0]["display_name"].startswith("New York")
    assert res[0]["lat"] == 40.7 and "type" in res[0]


def test_user_agent_is_ascii():
    # HTTP-Header müssen ASCII sein — sonst UnicodeEncodeError beim Request (live gefangen).
    nominatim._USER_AGENT.encode("ascii")
