"""RSS/Atom-Feed-Aggregator für den News-Globus.

fetch_all() holt mehrere Feeds parallel, parst sie (feedparser) und dedupliziert.
Die HTTP-Grenze _http_get_text() wird in Tests gemockt. feedparser wird lazy
importiert, damit ein fehlendes Paket die Skill-Registrierung nicht crasht.
"""
from __future__ import annotations

import asyncio
import logging
import re

import httpx

log = logging.getLogger("core.news")

_USER_AGENT = "Mantis/1.0 (persönlicher Assistent)"
_TAG_RE = re.compile(r"<[^>]+>")


async def _http_get_text(url: str) -> str:  # pragma: no cover - live-only
    try:
        async with httpx.AsyncClient(timeout=10, headers={"User-Agent": _USER_AGENT},
                                     follow_redirects=True) as c:
            r = await c.get(url)
        return r.text if r.status_code == 200 else ""
    except Exception as e:
        log.warning("Feed-Abruf fehlgeschlagen (%s): %s", url, e)
        return ""


def _clean(text: str) -> str:
    return _TAG_RE.sub("", text or "").strip()


async def fetch_feed(url: str) -> list[dict]:
    """Ein Feed → Liste von {title, summary, link, published, source}."""
    xml = await _http_get_text(url)
    if not xml:
        return []
    import feedparser
    d = feedparser.parse(xml)
    source = (d.feed.get("title") if getattr(d, "feed", None) else "") or url
    items = []
    for e in d.entries:
        title = _clean(e.get("title", ""))
        if not title:
            continue
        items.append({
            "title": title,
            "summary": _clean(e.get("summary", e.get("description", ""))),
            "link": e.get("link", ""),
            "published": e.get("published", e.get("updated", "")),
            "source": source,
        })
    return items


async def fetch_all(urls: list[str]) -> list[dict]:
    """Mehrere Feeds parallel holen + nach link (sonst title) deduplizieren."""
    results = await asyncio.gather(*[fetch_feed(u) for u in urls], return_exceptions=True)
    seen: set[str] = set()
    out: list[dict] = []
    for r in results:
        if isinstance(r, Exception):
            continue
        for it in r:
            key = it["link"] or it["title"]
            if key and key not in seen:
                seen.add(key)
                out.append(it)
    return out
