"""OpenStreetMap-Nominatim-Client — Geocoding (Ort → Koordinaten) + Ortssuche.

Nutzungspolicy von Nominatim strikt einhalten: aussagekräftiger User-Agent,
max. ~1 Request/Sekunde, Ergebnisse cachen (Geocoding ist stabil). Cache in
data/geo_cache.json. Die einzige HTTP-Grenze ist _http_get() — Tests mocken sie.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time

import httpx

log = logging.getLogger("core.geo")

_BASE = "https://nominatim.openstreetmap.org/search"
_USER_AGENT = "Mantis/1.0 (persönlicher Assistent; lokaler Betrieb)"
_MIN_INTERVAL = 1.1  # Sekunden zwischen Live-Calls (Policy)

_CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data", "geo_cache.json")

_cache: dict | None = None
_last_call: float = 0.0


def _load_cache() -> dict:
    global _cache
    if _cache is None:
        try:
            with open(_CACHE_PATH, encoding="utf-8") as f:
                _cache = json.load(f)
        except Exception:
            _cache = {}
    return _cache


def _save_cache() -> None:
    try:
        with open(_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_cache or {}, f, ensure_ascii=False)
    except Exception as e:  # pragma: no cover
        log.warning("geo_cache Schreibfehler: %s", e)


async def _http_get(params: dict) -> list:  # pragma: no cover - live-only
    """Einzige HTTP-Grenze (in Tests gemockt). Drosselt gemäß Policy."""
    global _last_call
    wait = _MIN_INTERVAL - (time.time() - _last_call)
    if wait > 0:
        await asyncio.sleep(wait)
    async with httpx.AsyncClient(timeout=10, headers={"User-Agent": _USER_AGENT}) as c:
        r = await c.get(_BASE, params={**params, "format": "json"})
    _last_call = time.time()
    if r.status_code != 200:
        log.warning("Nominatim HTTP %s", r.status_code)
        return []
    return r.json()


def _row(item: dict) -> dict:
    return {
        "lat": float(item["lat"]),
        "lon": float(item["lon"]),
        "display_name": item.get("display_name", ""),
        "type": item.get("type", ""),
    }


async def geocode(place: str) -> dict | None:
    """Ort → {lat, lon, display_name} (bester Treffer) oder None."""
    key = (place or "").strip().lower()
    if not key:
        return None
    cache = _load_cache()
    if key in cache:
        return cache[key]
    rows = await _http_get({"q": place, "limit": 1})
    if not rows:
        cache[key] = None
        _save_cache()
        return None
    r = _row(rows[0])
    result = {"lat": r["lat"], "lon": r["lon"], "display_name": r["display_name"]}
    cache[key] = result
    _save_cache()
    return result


async def search(query: str, limit: int = 5) -> list[dict]:
    """Ortssuche → Liste von {lat, lon, display_name, type}."""
    if not (query or "").strip():
        return []
    rows = await _http_get({"q": query, "limit": limit})
    return [_row(it) for it in rows]
