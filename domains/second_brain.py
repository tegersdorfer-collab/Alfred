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
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime

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

# ── Luhmann-Folgezettel-IDs (1 → 1a → 1a1 → 1a1a …) ───────────────────────────

def _zettel_segments(zid: str) -> list[str]:
    """'1a10' → ['1','a','10'] (abwechselnd Zahl/Buchstaben-Läufe)."""
    return re.findall(r"[0-9]+|[a-z]+", zid or "")


def _letters_to_int(s: str) -> int:
    """Spaltenweise wie Tabellen: a→1, z→26, aa→27."""
    n = 0
    for c in s:
        n = n * 26 + (ord(c) - 96)
    return n


def _int_to_letters(n: int) -> str:
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(97 + r) + s
    return s


def next_zettel_id(existing: list[str], parent: str | None = None) -> str:
    """Nächste freie Folgezettel-ID.

    Ohne parent: nächste Top-Level-Zahl. Mit parent: Kind-ID — endet der Elternteil
    auf eine Zahl, ist das Kind ein Buchstabe (1 → 1a), endet er auf einen
    Buchstaben, ist das Kind eine Zahl (1a → 1a1). Alterniert also nach Tiefe.
    """
    ids = set(existing or [])
    if parent is None:
        tops = [int(i) for i in ids if i.isdigit()]
        return str(max(tops) + 1) if tops else "1"

    psegs = _zettel_segments(parent)
    child_depth = len(psegs) + 1
    child_last = []
    for i in ids:
        segs = _zettel_segments(i)
        if len(segs) == child_depth and segs[:-1] == psegs:
            child_last.append(segs[-1])

    if psegs[-1].isdigit():  # Kind = Buchstabe
        if not child_last:
            return parent + "a"
        return parent + _int_to_letters(max(_letters_to_int(c) for c in child_last) + 1)
    # Kind = Zahl
    if not child_last:
        return parent + "1"
    return parent + str(max(int(c) for c in child_last) + 1)


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
    parent_id: int | None = None,
) -> int:
    """Legt eine neue Notiz an. embedding_fn(text) → list[float] optional.
    parent_id → Folgezettel-Kind-ID unter diesem Elternzettel (Luhmann)."""
    if category not in CATEGORIES:
        category = "inbox"
    emb = None
    if embedding_fn:
        try:
            emb = np.array(embedding_fn(f"{title}\n{content[:500]}"))
        except Exception as e:
            log.warning(f"Brain-Embedding fehlgeschlagen: {e}")

    zid = _assign_zettel_id(parent_id)

    with _db.cursor(vector=bool(emb)) as cur:
        cur.execute(
            """
            INSERT INTO brain_notes (title, content, category, tags, pinned, embedding, zettel_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (title, content, category, tags or [], pinned,
             emb if emb is not None else None, zid),
        )
        note_id = cur.fetchone()["id"]

    _resolve_wiki_links(note_id, content)
    return note_id


def _assign_zettel_id(parent_id: int | None) -> str:
    """Berechnet die nächste freie Folgezettel-ID (optional als Kind von parent_id)."""
    existing = [r["zettel_id"] for r in
                _db.query("SELECT zettel_id FROM brain_notes WHERE zettel_id IS NOT NULL")]
    parent_zettel = None
    if parent_id:
        prow = _db.query_one("SELECT zettel_id FROM brain_notes WHERE id=%s", (parent_id,))
        parent_zettel = prow["zettel_id"] if prow else None
    return next_zettel_id(existing, parent=parent_zettel)


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
    return _rows_to_notes(rows)


def get_inbox() -> list[BrainNote]:
    return get_by_category("inbox")


def get_backlinks(note_id: int) -> list[BrainNote]:
    """Notizen, die AUF diese verweisen ('was verweist hierher')."""
    rows = _db.query(
        """
        SELECT n.* FROM brain_notes n
        JOIN brain_links l ON n.id = l.from_id
        WHERE l.to_id = %s AND n.status = 'active'
        ORDER BY n.updated_at DESC
        """,
        (note_id,),
    )
    return _rows_to_notes(rows)


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
    return _rows_to_notes(rows)


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
    rows = list(keyword_rows)

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
                        rows.append(r)
                        seen.add(r["id"])
        except Exception as e:
            log.warning(f"Semantische Brain-Suche fehlgeschlagen: {e}")

    # Links für alle Treffer in einer Query (kein N+1)
    return _rows_to_notes(rows)[:limit]


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
    """Findet [[Titel]]- UND [[zettel_id]]-Links im Content und legt brain_links an."""
    for target in WIKI_LINK_RE.findall(content):
        t = target.strip()
        row = None
        if re.fullmatch(r"[0-9][a-z0-9]*", t):  # sieht wie eine Folgezettel-ID aus
            row = _db.query_one(
                "SELECT id FROM brain_notes WHERE zettel_id=%s AND id != %s LIMIT 1",
                (t, note_id),
            )
        if not row:
            row = _db.query_one(
                "SELECT id FROM brain_notes WHERE title ILIKE %s AND id != %s LIMIT 1",
                (t, note_id),
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

def _build_note(r: dict, links: list[int]) -> BrainNote:
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
        links=links,
    )


def _row_to_note(r: dict) -> BrainNote:
    """Einzelne Zeile → Note (eigene Link-Query). Für Einzel-Lookups."""
    link_rows = _db.query("SELECT to_id FROM brain_links WHERE from_id=%s", (r["id"],))
    return _build_note(r, [lr["to_id"] for lr in link_rows])


def _rows_to_notes(rows: list[dict]) -> list[BrainNote]:
    """Mehrere Zeilen → Notes mit EINER Link-Query statt einer pro Zeile (kein N+1)."""
    if not rows:
        return []
    ids = [r["id"] for r in rows]
    link_rows = _db.query(
        "SELECT from_id, to_id FROM brain_links WHERE from_id = ANY(%s)", (ids,)
    )
    links_by: dict[int, list[int]] = {}
    for lr in link_rows:
        links_by.setdefault(lr["from_id"], []).append(lr["to_id"])
    return [_build_note(r, links_by.get(r["id"], [])) for r in rows]


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
