# News-Globus + OSM + News — Design

**Datum:** 2026-07-10 · **Status:** vom User freigegeben („passt, config machen wir am Ende").

## Ziel

Ein **News-Globus** im Mantis-Dashboard: eine drehbare 3D-Weltkugel (Google-Earth-
Anmutung), die aktuelle Nachrichten als Punkte an ihrem geografischen Ort zeigt.
Verbindet drei Bausteine: **OSM/Nominatim** (Geocoding + Ortssuche + 2D-Karte),
**News** (RSS + Timos Themen), **Globus** (globe.gl). Karten-Analysen kommen als
eigene, spätere Scheibe.

**Voll-lokal-Grenze (bewusst):** News, Geocoding und Kartenkacheln brauchen
Internet — bei diesem Feature unvermeidbar. Globe.gl + Erdtextur werden lokal
vendored; offline zeigt der Globus keine frischen News, stürzt aber nicht ab.

## Bauscheiben (Reihenfolge)

1. **Backend**: Nominatim-Client, Feed-Aggregator, Geolokalisierung, Aggregator-Cache, API.
2. **Globus-View** (globe.gl) mit News-Punkten + Ortssuche.
3. **Agent-Tools** `where_is`, `news_briefing`.
4. **2D-OSM-Karte** (Leaflet) als zusätzliche View.
5. *(später, eigener Spec)* Karten-Analysen.

Analysen sind hier NICHT enthalten.

## Architektur

### Backend (Python)

**`tools/geo/nominatim.py`** — OSM-Nominatim-Client (httpx):
- `async geocode(place) -> dict|None` → `{lat, lon, display_name}` oder None.
- `async search(query, limit=5) -> list[dict]` → `[{lat, lon, display_name, type}]`.
- **Policy strikt:** User-Agent `Mantis/1.0 (persönlicher Assistent)`, min. 1 s
  zwischen Live-Calls (Semaphore/Timestamp), Ergebnisse gecacht in
  `data/geo_cache.json` (Geocoding ist stabil). Test-Seam: `_http_get(params)`.

**`tools/news/feeds.py`** — RSS-Aggregator (Dependency `feedparser`):
- `async fetch_feed(url) -> list[dict]` → `[{title, summary, link, published, source}]`.
- `async fetch_all(urls) -> list[dict]` → aggregiert + dedupliziert (nach link/title).
- Test-Seam: `_http_get_text(url)` liefert rohes XML (Fixtures in Tests).

**`tools/news/geolocate.py`** — Ortsextraktion:
- `async locate_headline(title, summary="") -> str|None` → Ortsname via **lokalem qwen**
  (`BG_REASONING_MODEL`), gecacht nach Titel-Hash (kein Doppel-LLM-Call).
- `async geolocate_item(item) -> dict` → item + `{lat, lon, place}` oder ohne Koordinaten.
- Test-Seams: `_extract_place(text)` (LLM) und `nominatim.geocode` mockbar.

**`core/news_globe.py`** — Aggregator + Cache:
- `async refresh() -> list[dict]` → alle Quellen holen, geolokalisieren, in
  `data/news_cache.json` schreiben, Liste zurückgeben.
- `cached() -> list[dict]` → letzter Cache (schnelles Dashboard-Laden).
- Im **Idle-Loop** periodisch (z. B. stündlich) aufgerufen.

**`web/routers/globe.py`** — `GET /api/globe/news` (gecachte Geo-News),
`GET /api/geo/search?q=` (Ortssuche via Nominatim).

**`core/skills/geo.py`** — Agent-Tools:
- `where_is(ort)` → geocode → Textantwort (auch für Sprachbefehle).
- `news_briefing()` → fasst die gecachten News zusammen („was ist in der Welt los?").
- Kategorie `geo`, Keywords in `_CATEGORY_KEYWORDS`.

### Konfiguration

`config/news_sources.json`: `{ "feeds": [<RSS-URLs>], "topics": [<Timos Themen>] }`.
Allgemeine Feeds (Tagesschau, Reuters …) + Themen; Themen-News zusätzlich über das
vorhandene `web_search` (Brave). **Defaults lege ich an; Feinschliff am Ende mit Timo.**

### Frontend (PWA, `web/index.html`)

- Neue View **🌍 Globus**: Container + **globe.gl** (vendored nach `web/vendor/`,
  wie chart.js/vis-network eingebunden).
- `GET /api/globe/news` → Punkte (lat/lon), Farbe nach Aktualität/Kategorie;
  Klick → Popup mit Schlagzeile + Quell-Link.
- **Ortssuche-Feld** → `/api/geo/search` → Globus fliegt zum Ort (`pointOfView`).
- **2D-Leaflet-Karte** als zusätzliche View/Umschalter (OSM-Kacheln + Attribution),
  Scheibe 4.

## Fehlerbehandlung

- Nominatim/Feed/LLM nicht erreichbar → geloggt, Item ohne Koordinaten wird
  übersprungen; API liefert den letzten Cache. Nie Absturz.
- Leerer Cache (erster Start) → API liefert `[]`, Globus zeigt „lade News …".
- Rate-Limit/Policy-Verstöße vermeiden (Cache + Drosselung).

## Tests (TDD)

- `nominatim`: httpx gemockt, Cache-Treffer ohne Live-Call, Rate-Limit-Logik.
- `feeds`: RSS/Atom-Fixtures → korrektes Parsing + Dedup.
- `geolocate`: LLM + Nominatim gemockt → Item bekommt Koordinaten / wird ohne Ort übersprungen.
- `news_globe`: refresh schreibt Cache, `cached()` liest ihn; Quelle gemockt.
- `globe`-Router: `/api/globe/news` liefert Cache, `/api/geo/search` ruft Nominatim.
- `skills/geo`: where_is/news_briefing mit gemockten Quellen.
- **Globus-JS**: nicht unit-getestet → live über Browser-Preview gegen das laufende
  Dashboard (Punkte sichtbar, Klick-Popup, Ortssuche).

## Globus-Bibliothek

**globe.gl** (three.js-basiert) — ideal für einen Daten-Globus (Punkte/Arcs/Labels),
ein CDN-/Vendor-Script, einfache API. Alternative für echte Satelliten-/Terrain-Optik
wäre **Cesium** (schwerer) — nicht in dieser Scheibe.

## Globale Randbedingungen

- Python 3.14, Tests `pytest -q`, Lint `ruff (F,E9)`, Deutsch + Emoji-Stil.
- Neue Dependencies: `feedparser` (RSS). Vendored JS: globe.gl + three + Erdtextur.
- Alles degradiert ohne Netz/Cache sauber; Mantis-Start nie gefährdet.
- Commits `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## Nicht in dieser Scheibe

- Karten-Analysen (eigener Spec).
- Cesium/Satelliten-Terrain.
- Routing/Navigation.
