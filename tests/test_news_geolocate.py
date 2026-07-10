"""Tests für die News-Geolokalisierung (tools/news/geolocate.py) — ohne LLM/Netz.

Gemockt: _extract_place (qwen) und nominatim.geocode. Geprüft: Item bekommt
Koordinaten, wird ohne Ort/ohne Geocode-Treffer korrekt übersprungen, Cache greift.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.news import geolocate
from tools.geo import nominatim


def _setup(place, geo):
    geolocate._cache = {}
    geolocate._save_cache = lambda: None
    calls = {"extract": 0}

    async def fake_extract(text):
        calls["extract"] += 1
        return place
    geolocate._extract_place = fake_extract

    async def fake_geocode(p):
        return geo
    nominatim.geocode = fake_geocode
    return calls


def test_item_gets_coordinates():
    _setup("Tokio", {"lat": 35.68, "lon": 139.69, "display_name": "Tokio"})
    item = {"title": "Erdbeben in Tokio", "summary": ""}
    out = asyncio.run(geolocate.geolocate_item(item))
    assert out["lat"] == 35.68 and out["lon"] == 139.69 and out["place"] == "Tokio"


def test_item_without_place_has_no_coords():
    _setup("", None)
    out = asyncio.run(geolocate.geolocate_item({"title": "Allgemeine Meldung", "summary": ""}))
    assert "lat" not in out and "place" not in out


def test_item_place_but_no_geocode():
    _setup("Nirgendwo", None)   # Ort erkannt, aber kein Geocode-Treffer
    out = asyncio.run(geolocate.geolocate_item({"title": "X in Nirgendwo", "summary": ""}))
    assert "lat" not in out


def test_locate_headline_caches():
    calls = _setup("Paris", {"lat": 48.85, "lon": 2.35, "display_name": "Paris"})
    asyncio.run(geolocate.locate_headline("Wahl in Paris"))
    asyncio.run(geolocate.locate_headline("wahl in paris"))   # gleiche Schlagzeile
    assert calls["extract"] == 1
