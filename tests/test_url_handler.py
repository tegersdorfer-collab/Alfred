"""Tests für die reinen URL-Handler-Helfer (tools/url_handler.py) — Plattform-
Erkennung, yt-dlp-Routing (Subdomain-sicher), URL-Extraktion, LLM-Formatierung,
HTML-Textextraktion. Kein Netzwerk.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.url_handler import (
    _platform, _host_matches, _is_ytdlp_url, extract_urls,
    format_for_llm, _HTMLTextExtractor,
)


# ── _host_matches ─────────────────────────────────────────────────────────────

def test_host_matches_exact_and_subdomain():
    assert _host_matches("youtube.com", "youtube.com")
    assert _host_matches("www.youtube.com", "youtube.com")
    assert _host_matches("m.youtube.com", "youtube.com")


def test_host_matches_rejects_lookalike():
    assert not _host_matches("myyoutube.com", "youtube.com")
    assert not _host_matches("youtube.com.evil.example", "youtube.com")


# ── _platform ─────────────────────────────────────────────────────────────────

def test_platform_known_hosts():
    assert _platform("https://youtu.be/abc") == "youtube"
    assert _platform("https://www.youtube.com/watch?v=x") == "youtube"
    assert _platform("https://x.com/user/status/1") == "twitter"
    assert _platform("https://vm.tiktok.com/xyz") == "tiktok"


def test_platform_unknown_returns_registrable():
    assert _platform("https://www.spiegel.de/artikel") == "spiegel"
    assert _platform("https://blog.example.org/post") == "example"


# ── _is_ytdlp_url (Subdomain-sicher) ──────────────────────────────────────────

def test_is_ytdlp_true_for_supported():
    assert _is_ytdlp_url("https://www.youtube.com/watch?v=x")
    assert _is_ytdlp_url("https://youtu.be/x")
    assert _is_ytdlp_url("https://vm.tiktok.com/x")


def test_is_ytdlp_false_for_article_and_lookalike():
    assert not _is_ytdlp_url("https://www.spiegel.de/artikel")
    assert not _is_ytdlp_url("https://youtube.com.evil.example/x")  # kein Substring-Match
    assert not _is_ytdlp_url("https://myyoutube.com/x")


# ── extract_urls ──────────────────────────────────────────────────────────────

def test_extract_urls_finds_all():
    text = "Schau https://a.com und http://b.org/x?y=1 an."
    assert extract_urls(text) == ["https://a.com", "http://b.org/x?y=1"]


def test_extract_urls_none():
    assert extract_urls("kein link hier") == []


# ── format_for_llm ────────────────────────────────────────────────────────────

def test_format_for_llm_video():
    data = {"platform": "youtube", "type": "video", "title": "Titel",
            "uploader": "Kanal", "duration_s": 125, "description": "Beschr.",
            "text": ""}
    out = format_for_llm(data)
    assert "[YOUTUBE — video]" in out
    assert "Titel: Titel" in out
    assert "Länge: 2:05" in out  # 125s → 2:05


def test_format_for_llm_truncates_text():
    data = {"platform": "article", "type": "article", "title": "T",
            "text": "x" * 10000}
    out = format_for_llm(data, max_text=100)
    assert "x" * 100 in out and "x" * 101 not in out


# ── _HTMLTextExtractor ────────────────────────────────────────────────────────

def test_html_extractor_skips_script_style():
    ext = _HTMLTextExtractor()
    ext.feed("<html><body>Hallo<script>var x=1;</script>"
             "<style>.a{}</style> Welt</body></html>")
    txt = ext.get_text()
    assert "Hallo" in txt and "Welt" in txt
    assert "var x" not in txt and ".a{" not in txt
