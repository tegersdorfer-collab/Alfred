"""
Knowledge-Tools — aus core/skills.py extrahiert (verhaltensgleich).
Registriert sich via @T.register beim Import (durch core/skills/__init__.py).
"""
import logging
from datetime import date, datetime

from core import tools as T
from core.timeparse import parse_datetime, parse_date
from core.skill_context import CTX
from domains import habits, fitness, nutrition, journal, goals, weather, tasks as tasks_d

log = logging.getLogger("core.skills")


@T.register("web_search",
    "Sucht aktuelle Informationen im Web (News, Fakten, Preise, Wetter-Hintergründe). "
    "Nutze dies wenn du aktuelle/externe Infos brauchst die du nicht weißt.",
    {"query": {"type": "string", "description": "Suchanfrage"},
     "news": {"type": "boolean", "description": "True für aktuelle Schlagzeilen"}},
    ["query"], "knowledge")
async def _web_search(query: str, news: bool = False):
    if not CTX.search:
        return "Suche nicht verfügbar."
    results = await CTX.search.search(query, max_results=4, news=news)
    return CTX.search.format_results(results) if results else "Keine Ergebnisse."

@T.register("get_weather",
    "Aktuelles Wetter und 3-Tage-Vorhersage.",
    {"city": {"type": "string", "description": "Stadt (optional, Default aus Settings)"}},
    [], "knowledge")
async def _get_weather(city: str = None):
    w = await weather.get_weather(city)
    if w.get("error"):
        return w["error"]
    now = w["now"]
    out = [f"Wetter in {w['city']}: {now['temp']}°C ({now['desc']}), gefühlt {now['feels']}°C, Wind {now['wind']} km/h."]
    for d in w["forecast"]:
        out.append(f"  {d['date']}: {d['min']}–{d['max']}°C, {d['code']}, Regen {d['rain_prob']}%")
    return "\n".join(out)

@T.register("brain_save",
    "Speichert eine Notiz, Erkenntnis, Entscheidung oder Information im Second Brain. "
    "Kategorien: context (über Timo), inbox (unsortiert), project (aktives Projekt), "
    "area (laufende Verantwortlichkeit), resource (Wissen/Recherche), daily (Tageslog), archive.",
    {
        "title":    {"type": "string",  "description": "Kurzer Titel der Notiz"},
        "content":  {"type": "string",  "description": "Inhalt der Notiz (Markdown, [[Wiki-Links]] unterstützt)"},
        "category": {"type": "string",  "description": "Kategorie: inbox | context | project | area | resource | daily | archive"},
        "tags":     {"type": "array",   "items": {"type": "string"}, "description": "Optionale Tags"},
    },
    ["title", "content"], "knowledge")
async def _brain_save(title: str, content: str, category: str = "inbox", tags: list = None):
    from domains.second_brain import brain_tool_save
    return brain_tool_save(title, content, category, tags)

@T.register("brain_search",
    "Durchsucht das Second Brain nach gespeichertem Wissen, Notizen, Projekten oder Entscheidungen.",
    {"query": {"type": "string", "description": "Suchbegriff oder Thema"}},
    ["query"], "knowledge")
async def _brain_search(query: str):
    from domains.second_brain import brain_tool_search
    return brain_tool_search(query)

@T.register("brain_inbox",
    "Wirft schnell einen Gedanken, eine Idee oder einen Brain-Dump in die Inbox des Second Brains. "
    "Mantis sortiert die Inbox regelmäßig automatisch ein.",
    {"content": {"type": "string", "description": "Der Gedanke oder die Idee die gespeichert werden soll"}},
    ["content"], "knowledge")
async def _brain_inbox(content: str):
    from domains.second_brain import brain_tool_inbox_add
    return brain_tool_inbox_add(content)

@T.register("brain_daily_log",
    "Schreibt einen Eintrag in die heutige Daily Note des Second Brains. "
    "Ideal für Tagesrückblicke, Entscheidungen, erledigte Dinge.",
    {"entry": {"type": "string", "description": "Was heute passiert ist oder entschieden wurde"}},
    ["entry"], "knowledge")
async def _brain_daily_log(entry: str):
    from domains.second_brain import brain_tool_daily_log
    return brain_tool_daily_log(entry)

@T.register("import_kindle_highlights",
    "Importiert Kindle-Highlights aus dem 'My Clippings.txt'-Format ins Second Brain als Quotes. "
    "Pfad zur Clippings-Datei oder Text direkt einfügen.",
    {
        "file_path": {"type": "string", "description": "Pfad zur My Clippings.txt"},
        "raw_text":  {"type": "string", "description": "Inhalt direkt als Text (Alternative zu file_path)"},
        "limit":     {"type": "integer","description": "Max. Highlights importieren (default 50)"},
    },
    [], "knowledge")
def _import_kindle_highlights(file_path: str = "", raw_text: str = "", limit: int = 50):
    import re
    from domains.second_brain import add_quote

    if file_path:
        try:
            text = open(file_path, encoding="utf-8-sig", errors="replace").read()
        except Exception as e:
            return f"Datei nicht lesbar: {e}"
    elif raw_text:
        text = raw_text
    else:
        # Suche Standard-Kindle-Pfade
        from pathlib import Path
        candidates = [
            Path.home() / "Documents" / "My Clippings.txt",
            Path("/Volumes/Kindle/documents/My Clippings.txt"),
        ]
        found = next((p for p in candidates if p.exists()), None)
        if not found:
            return "Keine Clippings.txt gefunden. Pfad angeben oder Text direkt einfügen."
        text = found.read_text(encoding="utf-8-sig", errors="replace")

    # Kindle-Format: ========== \n Titel (Autor)\n Deine Markierung | ...\n\n Text\n=====
    blocks = [b.strip() for b in text.split("==========") if b.strip()]
    imported = 0
    for block in blocks[:limit]:
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if len(lines) < 3:
            continue
        book = lines[0]
        # Highlight-Text ist alles ab Zeile 3
        highlight = " ".join(lines[2:]).strip()
        if len(highlight) < 15:
            continue
        author_match = re.search(r'\(([^)]+)\)\s*$', book)
        author = author_match.group(1) if author_match else ""
        title  = re.sub(r'\s*\([^)]+\)\s*$', '', book).strip()
        source = f"{title} — {author}" if author else title
        add_quote(text=highlight, source=source, tags=["kindle", "highlight"])
        imported += 1

    return f"✅ {imported} Kindle-Highlights als Quotes importiert."

@T.register("add_research_query",
    "Speichert ein Thema für die wöchentliche Recherche (jeden Montag automatisch). "
    "Beispiel: 'KI-News', 'Roblox-Entwicklung', 'Fitness-Wissenschaft'.",
    {"topic": {"type": "string", "description": "Thema das wöchentlich recherchiert werden soll"}},
    ["topic"], "knowledge")
def _add_research_query(topic: str):
    from domains.second_brain import add_note
    add_note(title=topic, content=f"Wöchentliche Recherche-Query: {topic}",
             category="resource", tags=["research_query"])
    return f"Recherche-Query gespeichert: '{topic}'. Jeden Montag wird dazu automatisch recherchiert."

@T.register("fetch_and_summarize_url",
    "Lädt eine URL (YouTube, TikTok, Instagram, Twitter/X, Artikel, Blog, Nachricht) via yt-dlp "
    "oder trafilatura, analysiert den Inhalt und speichert optional ins Second Brain. "
    "Funktioniert mit allen gängigen Plattformen.",
    {
        "url":      {"type": "string",  "description": "Beliebige URL — Video, Artikel, Social Media"},
        "save":     {"type": "boolean", "description": "In Second Brain speichern (default true)"},
        "category": {"type": "string",  "description": "brain_notes Kategorie (default 'resource')"},
    },
    ["url"], "knowledge")
async def _fetch_and_summarize_url(url: str, save: bool = True, category: str = "resource"):
    from tools.url_handler import fetch, format_for_llm
    from llm import fast as _fast

    data = await fetch(url)

    if data["type"] == "unknown" and not data.get("description"):
        return f"Konnte URL nicht laden: {url}"

    context = format_for_llm(data)

    # Prompt je nach Typ anpassen
    if data["type"] in ("video", "audio"):
        prompt = (
            "Analysiere diesen Video-/Audio-Inhalt. Antworte auf Deutsch.\n"
            "1. WORUM GEHT ES: Kurze Zusammenfassung (2-3 Sätze)\n"
            "2. KERNAUSSAGEN: 3-5 Bullet Points\n"
            "3. RELEVANZ FÜR TIMO: Lohnt es sich anzuschauen? Warum?\n\n"
            + context
        )
    else:
        prompt = (
            "Analysiere diesen Web-Inhalt. Antworte auf Deutsch.\n"
            "1. KERNAUSSAGEN: 3-5 Bullet Points (was ist wichtig/neu/interessant)\n"
            "2. BEWERTUNG: Was ist gut, was fragwürdig oder oberflächlich?\n"
            "3. RELEVANZ FÜR TIMO: Konkrete Anwendung oder nächster Schritt.\n\n"
            + context
        )

    summary = await _fast.ask(prompt, max_tokens=500)

    if save:
        from domains.second_brain import add_note
        title = data.get("title") or url.split("/")[-1][:60] or url[:60]
        tags = ["web", "import", data["platform"]]
        content = f"**Quelle:** {url}\n**Plattform:** {data['platform']}\n\n{summary}"
        add_note(title=title, content=content, category=category, tags=tags)
        return f"✅ Gespeichert ({data['platform']}):\n\n{summary}"
    return summary

@T.register("save_quote",
    "Speichert ein Zitat ins Second Brain. Gedanken dazu können später mit add_thought_to_quote ergänzt werden.",
    {
        "text":   {"type": "string", "description": "Das Zitat"},
        "source": {"type": "string", "description": "Autor oder Quelle"},
        "tags":   {"type": "array",  "items": {"type": "string"}, "description": "Themen-Tags"},
    },
    ["text"], "knowledge")
def _save_quote(text: str, source: str = "", tags: list = None):
    from domains.second_brain import add_quote
    q = add_quote(text, source, tags)
    return f"Zitat gespeichert (ID {q.get('id', '?')}): \"{text[:60]}\""

@T.register("add_thought_to_quote",
    "Fügt einen neuen Gedanken zu einem gespeicherten Zitat hinzu.",
    {
        "note_id": {"type": "integer", "description": "ID des Zitat-Eintrags im Second Brain"},
        "thought": {"type": "string",  "description": "Dein aktueller Gedanke dazu"},
    },
    ["note_id", "thought"], "knowledge")
def _add_thought_to_quote(note_id: int, thought: str):
    from domains.second_brain import add_thought_to_quote
    ok = add_thought_to_quote(note_id, thought)
    return "Gedanke hinzugefügt." if ok else "Zitat nicht gefunden."
