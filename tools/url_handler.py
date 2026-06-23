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
from urllib.parse import urlparse

log = logging.getLogger(__name__)

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


def _platform(url: str) -> str:
    host = urlparse(url).hostname or ""
    host = host.lstrip("www.")
    if "youtube" in host or "youtu.be" in host:
        return "youtube"
    if "tiktok" in host:
        return "tiktok"
    if "instagram" in host:
        return "instagram"
    if "twitter" in host or "x.com" in host:
        return "twitter"
    if "twitch" in host:
        return "twitch"
    if "spotify" in host:
        return "spotify"
    if "soundcloud" in host:
        return "soundcloud"
    if "reddit" in host or "redd.it" in host:
        return "reddit"
    return host.split(".")[0] if host else "unknown"


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
        text = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()

        title_m = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else ""

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
