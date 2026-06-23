"""
URL-Handler — extrahiert Inhalt aus beliebigen Links.

Strategie:
  1. yt-dlp  → YouTube, TikTok, Instagram, Twitter/X, Twitch, Vimeo, SoundCloud, Spotify (metadata)
  2. trafilatura → Artikel, Blogs, Nachrichtenseiten
  3. httpx   → Fallback für einfache Seiten ohne JavaScript

Gibt ein dict zurück:
  {
    "type":        "video" | "article" | "audio" | "unknown",
    "url":         str,
    "title":       str,
    "description": str,          # Beschreibung / Untertitel / OG-Description
    "text":        str,          # Volltext (Artikel) oder Transkript (Video)
    "duration_s":  int | None,   # Sekunden (Video/Audio)
    "uploader":    str | None,   # Kanal / Autor
    "platform":    str,          # "youtube", "tiktok", "article", …
    "thumbnail":   str | None,   # Thumbnail-URL
  }
"""
from __future__ import annotations
import asyncio
import logging
import re
from html.parser import HTMLParser
from urllib.parse import urlparse

log = logging.getLogger(__name__)


class _HTMLTextExtractor(HTMLParser):
    """Extract visible text from HTML, skipping script/style blocks."""
    _SKIP_TAGS = frozenset({"script", "style", "noscript", "head"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            stripped = data.strip()
            if stripped:
                self._parts.append(stripped)

    def get_text(self) -> str:
        return " ".join(self._parts)

# Plattformen die yt-dlp unterstützt (Auswahl für schnelle Erkennung)
_YTDLP_HOSTS = {
    "youtube.com", "youtu.be", "www.youtube.com",
    "tiktok.com", "www.tiktok.com", "vm.tiktok.com",
    "instagram.com", "www.instagram.com",
    "twitter.com", "x.com", "www.twitter.com",
    "twitch.tv", "www.twitch.tv", "clips.twitch.tv",
    "vimeo.com", "www.vimeo.com",
    "soundcloud.com", "www.soundcloud.com",
    "reddit.com", "www.reddit.com", "v.redd.it",
    "dailymotion.com", "www.dailymotion.com",
    "rumble.com", "www.rumble.com",
    "bilibili.com", "www.bilibili.com",
}


def _host_matches(host: str, *domains: str) -> bool:
    """True if host equals or is a subdomain of any of the given domains."""
    return any(host == d or host.endswith("." + d) for d in domains)


def _platform(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if _host_matches(host, "youtube.com", "youtu.be"):
        return "youtube"
    if _host_matches(host, "tiktok.com"):
        return "tiktok"
    if _host_matches(host, "instagram.com"):
        return "instagram"
    if _host_matches(host, "twitter.com", "x.com"):
        return "twitter"
    if _host_matches(host, "twitch.tv"):
        return "twitch"
    if _host_matches(host, "spotify.com"):
        return "spotify"
    if _host_matches(host, "soundcloud.com"):
        return "soundcloud"
    if _host_matches(host, "reddit.com", "redd.it"):
        return "reddit"
    # Return the registrable part of the hostname (last two labels) as a safe default
    parts = host.rsplit(".", 2)
    return parts[-2] if len(parts) >= 2 else (host or "unknown")


def _is_ytdlp_url(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return any(h in host for h in _YTDLP_HOSTS)


async def _fetch_ytdlp(url: str) -> dict:
    """Extrahiert Metadaten + Untertitel/Beschreibung via yt-dlp (kein Download)."""
    import yt_dlp

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": False,
        "writeautomaticsub": False,
        "subtitleslangs": ["de", "en"],
        "extract_flat": False,
    }

    def _run() -> dict:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return {}

            # Untertitel-Text aus automatischen Subs extrahieren (wenn vorhanden)
            transcript = ""
            subs = info.get("subtitles") or info.get("automatic_captions") or {}
            for lang in ("de", "en"):
                if lang in subs and subs[lang]:
                    # Nur Metadaten — echtes Subtitle-Scraping würde separaten Request brauchen
                    break

            return {
                "type": "video" if info.get("duration") else "audio",
                "url": url,
                "title": info.get("title", ""),
                "description": (info.get("description") or "")[:2000],
                "text": transcript,
                "duration_s": info.get("duration"),
                "uploader": info.get("uploader") or info.get("channel"),
                "platform": _platform(url),
                "thumbnail": info.get("thumbnail"),
                "view_count": info.get("view_count"),
                "like_count": info.get("like_count"),
                "upload_date": info.get("upload_date"),
                "chapters": [
                    {"title": c.get("title"), "start": c.get("start_time")}
                    for c in (info.get("chapters") or [])
                ][:20],
                "tags": (info.get("tags") or [])[:10],
            }

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        log.warning(f"yt-dlp fehlgeschlagen ({url}): {e}")
        return {"type": "unknown", "url": url, "title": "", "description": str(e),
                "text": "", "platform": _platform(url)}


async def _fetch_article(url: str) -> dict:
    """Artikel-Text via trafilatura, Fallback auf httpx + Regex."""
    # trafilatura
    try:
        import trafilatura
        downloaded = await asyncio.to_thread(trafilatura.fetch_url, url)
        if downloaded:
            text = await asyncio.to_thread(
                trafilatura.extract,
                downloaded,
                include_comments=False,
                include_tables=False,
                output_format="txt",
            )
            meta = await asyncio.to_thread(
                trafilatura.extract_metadata, downloaded
            )
            if text and len(text) > 200:
                return {
                    "type": "article",
                    "url": url,
                    "title": getattr(meta, "title", "") or "",
                    "description": getattr(meta, "description", "") or "",
                    "text": text[:8000],
                    "duration_s": None,
                    "uploader": getattr(meta, "author", "") or "",
                    "platform": "article",
                    "thumbnail": getattr(meta, "image", None),
                }
    except Exception as e:
        log.debug(f"trafilatura fehlgeschlagen: {e}")

    # httpx-Fallback
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15, follow_redirects=True,
                                      headers={"User-Agent": "Mozilla/5.0 Alfred/1.0"}) as c:
            r = await c.get(url)
        html = r.text
        extractor = _HTMLTextExtractor()
        extractor.feed(html)
        text = re.sub(r'\s+', ' ', extractor.get_text()).strip()

        # Extract <title> via a second parser pass (avoids regexp on HTML attributes)
        title_extractor = _HTMLTextExtractor()
        title_m = re.search(r'(?i)<title[^>]*>([\s\S]{0,512})</title>', html)
        title = ""
        if title_m:
            title_extractor.feed(title_m.group(1))
            title = title_extractor.get_text().strip()

        return {
            "type": "article",
            "url": url,
            "title": title,
            "description": "",
            "text": text[:6000],
            "duration_s": None,
            "uploader": "",
            "platform": "article",
            "thumbnail": None,
        }
    except Exception as e:
        return {"type": "unknown", "url": url, "title": "", "description": str(e),
                "text": "", "platform": "unknown"}


async def fetch(url: str) -> dict:
    """Einheitlicher Einstiegspunkt — wählt automatisch yt-dlp oder trafilatura."""
    if _is_ytdlp_url(url):
        result = await _fetch_ytdlp(url)
        if result.get("title") or result.get("description"):
            return result
    return await _fetch_article(url)


def format_for_llm(data: dict, max_text: int = 4000) -> str:
    """Formatiert Fetch-Ergebnis als LLM-Kontext-Block."""
    lines = [f"[{data['platform'].upper()} — {data['type']}]"]
    if data.get("title"):
        lines.append(f"Titel: {data['title']}")
    if data.get("uploader"):
        lines.append(f"Von: {data['uploader']}")
    if data.get("duration_s"):
        m, s = divmod(int(data["duration_s"]), 60)
        lines.append(f"Länge: {m}:{s:02d}")
    if data.get("upload_date"):
        d = data["upload_date"]
        lines.append(f"Datum: {d[:4]}-{d[4:6]}-{d[6:]}" if len(d) == 8 else d)
    if data.get("view_count"):
        lines.append(f"Aufrufe: {data['view_count']:,}")
    if data.get("chapters"):
        chaps = ", ".join(c["title"] for c in data["chapters"][:5] if c.get("title"))
        if chaps:
            lines.append(f"Kapitel: {chaps}")
    if data.get("description"):
        lines.append(f"\nBeschreibung:\n{data['description'][:1000]}")
    if data.get("text"):
        lines.append(f"\nInhalt:\n{data['text'][:max_text]}")
    return "\n".join(lines)


def extract_urls(text: str) -> list[str]:
    """Findet alle URLs in einem Text."""
    return re.findall(r'https?://[^\s<>"\']+', text)
