"""
Web-Suche für Alfred.
Primär: DuckDuckGo (kostenlos, kein API-Key)
Fallback: Brave Search API (falls BRAVE_API_KEY gesetzt)
"""
import asyncio
import logging
from dataclasses import dataclass

import httpx

import config

log = logging.getLogger(__name__)

DUCKDUCKGO_URL  = "https://api.duckduckgo.com/"
BRAVE_URL       = "https://api.search.brave.com/res/v1/web/search"
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str

    def __str__(self) -> str:
        return f"**{self.title}**\n{self.snippet}\n{self.url}"


class WebSearch:
    """
    Führt Web-Suchen durch.
    Nutzt DuckDuckGo als Standard, Brave als Fallback.
    """

    async def search(self, query: str, max_results: int = 5, news: bool = False) -> list[SearchResult]:
        """
        Sucht im Web.
        news=True → Google News RSS (aktuelle Schlagzeilen)
        Fallback-Kette: DDG → Brave
        """
        log.info(f"🔍 Suche: {query}")

        if news:
            try:
                results = await self._google_news(query, max_results)
                if results:
                    log.info(f"🔍 Google News: {len(results)} Ergebnisse")
                    return results
            except Exception as e:
                log.debug(f"Google News fehlgeschlagen: {e}")

        try:
            results = await self._duckduckgo(query, max_results)
            if results:
                log.info(f"🔍 DDG: {len(results)} Ergebnisse")
                return results
        except Exception as e:
            log.debug(f"DDG fehlgeschlagen: {e}")

        if config.BRAVE_API_KEY:
            try:
                results = await self._brave(query, max_results)
                if results:
                    log.info(f"🔍 Brave: {len(results)} Ergebnisse")
                    return results
            except Exception as e:
                log.debug(f"Brave fehlgeschlagen: {e}")

        log.warning(f"Suche fehlgeschlagen für: {query}")
        return []

    async def _google_news(self, query: str, max_results: int) -> list[SearchResult]:
        """Google News RSS – liefert aktuelle Schlagzeilen."""
        import xml.etree.ElementTree as ET
        async with httpx.AsyncClient(headers=HEADERS, timeout=10, follow_redirects=True) as client:
            r = await client.get(GOOGLE_NEWS_RSS, params={
                "q": query,
                "hl": "de",
                "gl": "DE",
                "ceid": "DE:de",
            })
        root = ET.fromstring(r.text)
        results = []
        for item in root.findall(".//item")[:max_results]:
            title   = item.findtext("title", "").strip()
            link    = item.findtext("link", "").strip()
            desc    = item.findtext("description", "").strip()
            source  = item.findtext("source", "").strip()
            # HTML aus description entfernen
            import re
            desc = re.sub(r'<[^>]+>', '', desc).strip()
            if title:
                snippet = f"{desc[:200]}" if desc else title
                if source:
                    snippet += f" ({source})"
                results.append(SearchResult(title=title, url=link, snippet=snippet))
        return results

    def format_results(self, results: list[SearchResult]) -> str:
        """Formatiert Suchergebnisse als lesbaren Text für LLM-Kontext."""
        if not results:
            return "Keine Suchergebnisse gefunden."
        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r.title}\n   {r.snippet}\n   {r.url}")
        return "\n\n".join(lines)

    async def _duckduckgo(self, query: str, max_results: int) -> list[SearchResult]:
        """DuckDuckGo Instant Answer API + HTML-Fallback."""
        async with httpx.AsyncClient(headers=HEADERS, timeout=10) as client:
            # Instant Answer API
            r = await client.get(DUCKDUCKGO_URL, params={
                "q": query,
                "format": "json",
                "no_html": "1",
                "skip_disambig": "1",
            })
            data = r.json()

        results = []

        # Abstract (Wikipedia-ähnliche Zusammenfassung)
        if data.get("AbstractText"):
            results.append(SearchResult(
                title=data.get("Heading", query),
                url=data.get("AbstractURL", ""),
                snippet=data["AbstractText"][:300],
            ))

        # Related Topics
        for topic in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append(SearchResult(
                    title=topic.get("Text", "")[:60],
                    url=topic.get("FirstURL", ""),
                    snippet=topic.get("Text", "")[:200],
                ))
            if len(results) >= max_results:
                break

        # Falls DDG Instant nichts liefert → HTML-Suche
        if not results:
            results = await self._duckduckgo_html(query, max_results)

        return results[:max_results]

    async def _duckduckgo_html(self, query: str, max_results: int) -> list[SearchResult]:
        """DuckDuckGo HTML-Scraping als Fallback."""
        async with httpx.AsyncClient(headers=HEADERS, timeout=10, follow_redirects=True) as client:
            r = await client.get("https://html.duckduckgo.com/html/", params={"q": query})

        results = []
        # Einfaches Parsing ohne BeautifulSoup
        html = r.text
        # Suche nach Ergebnis-Snippets im HTML
        import re
        titles   = re.findall(r'class="result__title"[^>]*>.*?<a[^>]*>(.*?)</a>', html, re.DOTALL)
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</span>', html, re.DOTALL)
        urls     = re.findall(r'class="result__url"[^>]*>(.*?)</a>', html, re.DOTALL)

        # HTML-Tags entfernen
        clean = lambda s: re.sub(r'<[^>]+>', '', s).strip()

        for i in range(min(max_results, len(titles), len(snippets))):
            t = clean(titles[i])
            s = clean(snippets[i])
            u = clean(urls[i]) if i < len(urls) else ""
            if t and s:
                results.append(SearchResult(title=t, url=u, snippet=s[:250]))

        return results

    async def _brave(self, query: str, max_results: int) -> list[SearchResult]:
        """Brave Search API."""
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(BRAVE_URL, params={
                "q": query,
                "count": max_results,
                "country": "DE",
                "search_lang": "de",
            }, headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": config.BRAVE_API_KEY,
            })
            data = r.json()

        results = []
        for item in data.get("web", {}).get("results", [])[:max_results]:
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("description", "")[:250],
            ))
        return results
