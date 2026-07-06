"""
Second Brain – persönliche Wissensbasis in PostgreSQL.

Kategorien (wie Obsidian-Ordner):
  context   – Wer Timo ist: Schreibstil, Background, Präferenzen, ICP
  inbox     – Brain-Dump, unsortierte Gedanken
  project   – Aktive Projekte mit Deadline
  area      – Laufende Verantwortlichkeiten (kein End-Datum)
  resource  – Allgemeines Wissen, Recherche, Tooldoku
  daily     – Tagesnotizen / Logbuch
  archive   – Erledigte / alte Einträge

Wiki-Links [[Titel]] werden automatisch beim Speichern aufgelöst.
"""
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

import numpy as np

from core import db as _db

log = logging.getLogger(__name__)

CATEGORIES = ["context", "inbox", "project", "area", "resource", "daily", "quote", "archive"]

CATEGORY_LABELS = {
    "context": "Kontext",
    "inbox":   "Inbox",
    "project": "Projekte",
    "area":    "Bereiche",
    "resource":"Ressourcen",
    "daily":   "Daily Notes",
    "quote":   "Zitate",
    "archive": "Archiv",
}

WIKI_LINK_RE = re.compile(r"\[\[([^\]]{1,300})\]\]")


@dataclass
class BrainNote:
    id: int
    title: str
    content: str
    category: str
    tags: list[str]
    status: str
    pinned: bool
    created_at: datetime
    updated_at: datetime
    links: list[int] = field(default_factory=list)  # IDs der verlinkten Notes


# ── CRUD ──────────────────────────────────────────────────────────────────────

def add_note(
    title: str,
    content: str,
    category: str = "inbox",
    tags: list[str] | None = None,
    pinned: bool = False,
    embedding_fn=None,
) -> int:
    """Legt eine neue Notiz an. embedding_fn(text) → list[float] optional."""
    if category not in CATEGORIES:
        category = "inbox"
    emb = None
    if embedding_fn:
        try:
            emb = np.array(embedding_fn(f"{title}\n{content[:500]}"))
        except Exception as e:
            log.warning(f"Brain-Embedding fehlgeschlagen: {e}")

    with _db.cursor(vector=bool(emb)) as cur:
        cur.execute(
            """
            INSERT INTO brain_notes (title, content, category, tags, pinned, embedding)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (title, content, category, tags or [], pinned,
             emb if emb is not None else None),
        )
        note_id = cur.fetchone()["id"]

    _resolve_wiki_links(note_id, content)
    return note_id


def update_note(
    note_id: int,
    title: str | None = None,
    content: str | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
    status: str | None = None,
    pinned: bool | None = None,
    embedding_fn=None,
) -> bool:
    note = get_note(note_id)
    if not note:
        return False

    new_title   = title   if title   is not None else note.title
    new_content = content if content is not None else note.content
    new_cat     = category if category in CATEGORIES else note.category
    new_tags    = tags   if tags    is not None else note.tags
    new_status  = status if status  is not None else note.status
    new_pinned  = pinned if pinned  is not None else note.pinned

    emb = None
    if embedding_fn and content is not None:
        try:
            emb = np.array(embedding_fn(f"{new_title}\n{new_content[:500]}"))
        except Exception as e:
            log.warning(f"Brain-Embedding update fehlgeschlagen: {e}")

    if emb is not None:
        with _db.cursor(vector=True) as cur:
            cur.execute(
                """
                UPDATE brain_notes SET title=%s, content=%s, category=%s, tags=%s,
                    status=%s, pinned=%s, embedding=%s, updated_at=NOW()
                WHERE id=%s
                """,
                (new_title, new_content, new_cat, new_tags,
                 new_status, new_pinned, emb, note_id),
            )
    else:
        _db.execute(
            """
            UPDATE brain_notes SET title=%s, content=%s, category=%s, tags=%s,
                status=%s, pinned=%s, updated_at=NOW()
            WHERE id=%s
            """,
            (new_title, new_content, new_cat, new_tags,
             new_status, new_pinned, note_id),
        )

    if content is not None:
        _db.execute("DELETE FROM brain_links WHERE from_id=%s", (note_id,))
        _resolve_wiki_links(note_id, new_content)

    return True


def delete_note(note_id: int) -> bool:
    _db.execute("DELETE FROM brain_notes WHERE id=%s", (note_id,))
    return True


def get_note(note_id: int) -> BrainNote | None:
    row = _db.query_one(
        "SELECT * FROM brain_notes WHERE id=%s", (note_id,)
    )
    if not row:
        return None
    return _row_to_note(row)


def get_by_category(category: str, limit: int = 200) -> list[BrainNote]:
    rows = _db.query(
        """
        SELECT * FROM brain_notes
        WHERE category=%s AND status='active'
        ORDER BY pinned DESC, updated_at DESC
        LIMIT %s
        """,
        (category, limit),
    )
    return [_row_to_note(r) for r in rows]


def get_inbox() -> list[BrainNote]:
    return get_by_category("inbox")


def get_all(limit: int = 500) -> list[BrainNote]:
    rows = _db.query(
        """
        SELECT * FROM brain_notes
        WHERE status='active'
        ORDER BY pinned DESC, updated_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    return [_row_to_note(r) for r in rows]


def get_today_daily() -> BrainNote | None:
    today = date.today().isoformat()
    return _db.query_one(
        "SELECT * FROM brain_notes WHERE category='daily' AND title=%s",
        (today,),
    )


def ensure_today_daily() -> BrainNote:
    existing = get_today_daily()
    if existing:
        return _row_to_note(existing)
    note_id = add_note(
        title=date.today().isoformat(),
        content=f"# Daily Note {date.today().isoformat()}\n\n",
        category="daily",
    )
    return get_note(note_id)


# ── Suche ─────────────────────────────────────────────────────────────────────

def search_notes(query: str, limit: int = 20, embedding_fn=None) -> list[BrainNote]:
    """Keyword-Suche (ILIKE). Mit embedding_fn auch semantisch."""
    keyword_rows = _db.query(
        """
        SELECT * FROM brain_notes
        WHERE status='active'
          AND (title ILIKE %s OR content ILIKE %s OR %s = ANY(tags))
        ORDER BY updated_at DESC
        LIMIT %s
        """,
        (f"%{query}%", f"%{query}%", query.lower(), limit),
    )
    seen = {r["id"] for r in keyword_rows}
    results = [_row_to_note(r) for r in keyword_rows]

    if embedding_fn:
        try:
            emb = np.array(embedding_fn(query))
            with _db.cursor(vector=True) as cur:
                cur.execute(
                    """
                    SELECT * FROM brain_notes
                    WHERE status='active' AND embedding IS NOT NULL
                    ORDER BY embedding <=> %s
                    LIMIT %s
                    """,
                    (emb, limit),
                )
                for r in cur.fetchall():
                    if r["id"] not in seen:
                        results.append(_row_to_note(r))
                        seen.add(r["id"])
        except Exception as e:
            log.warning(f"Semantische Brain-Suche fehlgeschlagen: {e}")

    return results[:limit]


# ── Graph ─────────────────────────────────────────────────────────────────────

CATEGORY_COLORS = {
    "context":  "#4fc3f7",
    "inbox":    "#aaa",
    "project":  "#ff8a65",
    "area":     "#81c784",
    "resource": "#ce93d8",
    "daily":    "#fff176",
    "archive":  "#555",
    "quote":    "#f9a825",
}


# ── Quotes mit evolving Thoughts ──────────────────────────────────────────────

def add_quote(text: str, source: str = "", tags: list[str] | None = None) -> dict:
    """Speichert ein Zitat als brain_note (Kategorie 'quote')."""
    title = (text[:60] + "…") if len(text) > 60 else text
    content = f"> {text}\n\n— {source}\n\n---\n\n### Gedanken"
    note_id = add_note(title=title, content=content, category="quote",
                        tags=(tags or []) + ["quote", source] if source else (tags or []) + ["quote"])
    return get_note(note_id) or {}


def add_thought_to_quote(note_id: int, thought: str) -> bool:
    """Fügt einen neuen Gedanken an ein Zitat an."""
    note = get_note(note_id)
    if not note or note.category != "quote":
        return False
    from datetime import datetime as _dt
    stamp = _dt.now().strftime("%Y-%m-%d")
    new_content = note.content + f"\n\n**{stamp}:** {thought}"
    return update_note(note_id, content=new_content)


def get_quotes(limit: int = 50) -> list[dict]:
    """Alle Zitate sortiert nach letzter Aktualisierung."""
    return [note_to_dict(n) for n in get_by_category("quote", limit=limit)]


def get_graph_data() -> dict:
    """Gibt nodes + edges für vis.js zurück."""
    notes = get_all(limit=500)
    links = _db.query("SELECT from_id, to_id FROM brain_links")

    nodes = []
    for n in notes:
        nodes.append({
            "id": n.id,
            "label": n.title[:30] + ("…" if len(n.title) > 30 else ""),
            "title": n.title,
            "group": n.category,
            "color": CATEGORY_COLORS.get(n.category, "#888"),
            "size": 20 if n.pinned else 12,
        })

    edges = [
        {"from": r["from_id"], "to": r["to_id"], "arrows": "to"}
        for r in links
    ]
    return {"nodes": nodes, "edges": edges}


# ── Inbox-Sorting (LLM) ───────────────────────────────────────────────────────

async def sort_inbox_note(note: BrainNote, llm) -> str:
    """
    LLM entscheidet für eine Inbox-Notiz welche Kategorie passt.
    Gibt die neue Kategorie zurück.
    """
    prompt = (
        "Du bist Mantis' Wissens-Sortierer. Ordne diese Notiz einer Kategorie zu.\n\n"
        f"Titel: {note.title}\nInhalt: {note.content[:400]}\n\n"
        "Kategorien:\n"
        "- context: Infos über Timo selbst (Schreibstil, Background, Präferenzen)\n"
        "- project: Aktives Projekt mit Deadline\n"
        "- area: Laufende Verantwortlichkeit ohne festes Ende\n"
        "- resource: Allgemeines Wissen, Recherche, Tooldoku\n"
        "- daily: Tagesnotiz / Was heute passiert ist\n"
        "- archive: Erledigt, nicht mehr relevant\n\n"
        "Antworte NUR mit einem dieser Wörter: context | project | area | resource | daily | archive"
    )
    try:
        result = await llm.complete(prompt, max_tokens=10)
        cat = result.strip().lower().split()[0]
        return cat if cat in CATEGORIES and cat != "inbox" else "resource"
    except Exception as e:
        log.warning(f"Inbox-Sorting fehlgeschlagen: {e}")
        return "resource"


async def sort_all_inbox(llm) -> list[dict]:
    """Sortiert alle Inbox-Notizen per LLM. Gibt Liste von Änderungen zurück."""
    inbox = get_inbox()
    changes = []
    for note in inbox:
        new_cat = await sort_inbox_note(note, llm)
        update_note(note.id, category=new_cat)
        changes.append({"id": note.id, "title": note.title, "category": new_cat})
        log.info(f"Brain Inbox-Sort: '{note.title}' → {new_cat}")
    return changes


# ── Mantis-Tools (für den Agent) ──────────────────────────────────────────────

def brain_tool_save(title: str, content: str, category: str = "inbox",
                    tags: list[str] | None = None) -> str:
    """Mantis-Tool: Notiz im Second Brain speichern."""
    note_id = add_note(title=title, content=content, category=category, tags=tags)
    return f"Notiz '{title}' gespeichert (ID {note_id}, Kategorie: {category})"


def brain_tool_search(query: str) -> str:
    """Mantis-Tool: Second Brain durchsuchen."""
    results = search_notes(query)
    if not results:
        return f"Keine Notizen zu '{query}' gefunden."
    lines = [f"**{n.title}** [{n.category}]\n{n.content[:200]}…\n---" for n in results[:5]]
    return "\n".join(lines)


def brain_tool_inbox_add(content: str) -> str:
    """Mantis-Tool: Schnell etwas in die Inbox werfen."""
    title = content[:60].split("\n")[0].strip() or "Inbox-Notiz"
    note_id = add_note(title=title, content=content, category="inbox")
    return f"In Inbox gespeichert (ID {note_id}): '{title}'"


def brain_tool_daily_log(entry: str) -> str:
    """Mantis-Tool: Eintrag in heutige Daily Note schreiben."""
    daily = ensure_today_daily()
    new_content = daily.content + f"\n## {datetime.now().strftime('%H:%M')}\n{entry}\n"
    update_note(daily.id, content=new_content)
    return f"Daily Note {daily.title} aktualisiert."


# ── Wiki-Links ────────────────────────────────────────────────────────────────

def _resolve_wiki_links(note_id: int, content: str) -> None:
    """Findet [[Titel]]-Links im Content und legt brain_links-Einträge an."""
    titles = WIKI_LINK_RE.findall(content)
    for title in titles:
        row = _db.query_one(
            "SELECT id FROM brain_notes WHERE title ILIKE %s AND id != %s LIMIT 1",
            (title.strip(), note_id),
        )
        if row:
            try:
                _db.execute(
                    "INSERT INTO brain_links (from_id, to_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (note_id, row["id"]),
                )
            except Exception:
                pass


# ── Serialisierung ────────────────────────────────────────────────────────────

def _row_to_note(r: dict) -> BrainNote:
    links_rows = _db.query(
        "SELECT to_id FROM brain_links WHERE from_id=%s", (r["id"],)
    )
    return BrainNote(
        id=r["id"],
        title=r["title"],
        content=r["content"],
        category=r["category"],
        tags=r.get("tags") or [],
        status=r.get("status", "active"),
        pinned=r.get("pinned", False),
        created_at=r["created_at"],
        updated_at=r["updated_at"],
        links=[lr["to_id"] for lr in links_rows],
    )


def note_to_dict(n: BrainNote) -> dict:
    return {
        "id": n.id,
        "title": n.title,
        "content": n.content,
        "category": n.category,
        "tags": n.tags,
        "status": n.status,
        "pinned": n.pinned,
        "links": n.links,
        "created_at": n.created_at.isoformat(),
        "updated_at": n.updated_at.isoformat(),
    }
