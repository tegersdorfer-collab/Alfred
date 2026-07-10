"""Tests für den RSS-Aggregator (tools/news/feeds.py) — ohne Netz.

_http_get_text wird gemockt und liefert Fixture-XML. Geprüft: Parsing (RSS+Atom),
HTML-Bereinigung der Zusammenfassung, Dedup über mehrere Feeds.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.news import feeds

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<title>Tagesschau</title>
<item>
  <title>Erdbeben erschüttert Tokio</title>
  <description>&lt;p&gt;Ein starkes Beben in &lt;b&gt;Tokio&lt;/b&gt;.&lt;/p&gt;</description>
  <link>https://ex.org/a</link>
  <pubDate>Wed, 10 Jul 2026 08:00:00 GMT</pubDate>
</item>
<item>
  <title>Wahl in Frankreich</title>
  <description>Paris wählt.</description>
  <link>https://ex.org/b</link>
  <pubDate>Wed, 10 Jul 2026 07:00:00 GMT</pubDate>
</item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Reuters</title>
<entry>
  <title>Flooding in Jakarta</title>
  <summary>Heavy rain hits Jakarta.</summary>
  <link href="https://ex.org/c"/>
  <updated>2026-07-10T06:00:00Z</updated>
</entry>
</feed>"""


def _patch(mapping):
    async def fake(url):
        return mapping.get(url, "")
    feeds._http_get_text = fake


def test_fetch_feed_rss_parses_and_cleans():
    _patch({"u1": RSS})
    items = asyncio.run(feeds.fetch_feed("u1"))
    assert len(items) == 2
    a = items[0]
    assert a["title"] == "Erdbeben erschüttert Tokio"
    assert "<" not in a["summary"] and "Tokio" in a["summary"]   # HTML entfernt
    assert a["link"] == "https://ex.org/a"
    assert a["source"] == "Tagesschau"


def test_fetch_feed_atom():
    _patch({"u2": ATOM})
    items = asyncio.run(feeds.fetch_feed("u2"))
    assert items[0]["title"] == "Flooding in Jakarta"
    assert items[0]["link"] == "https://ex.org/c"
    assert items[0]["source"] == "Reuters"


def test_fetch_all_dedups_by_link():
    _patch({"u1": RSS, "u3": RSS})   # gleiche Items zweimal
    items = asyncio.run(feeds.fetch_all(["u1", "u3"]))
    links = [i["link"] for i in items]
    assert len(links) == len(set(links)) == 2   # dedupliziert


def test_fetch_feed_empty_on_blank():
    _patch({})
    assert asyncio.run(feeds.fetch_feed("nope")) == []
