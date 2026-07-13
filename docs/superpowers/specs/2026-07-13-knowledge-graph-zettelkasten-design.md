# SP3 — Zettelkasten-Memory + vereinter Wissensgraph

**Datum:** 2026-07-13
**Umbrella:** `2026-07-13-native-app-migration-scope.md` (Sub-Projekt 3)
**Status:** Design genehmigt (alle Weichen per Brainstorm entschieden) → Umsetzung.

## Entscheidungen (fix)
1. **Speicher:** Postgres bleibt, eigenes System (kein echter Obsidian-Vault).
2. **Scope:** Notizen **und** Agenten-Fakten **und** Entitäten in **einem** Wissensgraphen.
3. **Vereinigung:** föderierter **Leselayer** (Projektion), kein destruktiver Merge.
4. **Auto-Linking:** Erwähnungen (Entität/Notiztitel im Text) **+** Embedding-Ähnlichkeit.
5. **Zettelkasten:** voller **Luhmann-Apparat** (Folgezettel-IDs) + atomare Notizen + Backlinks.

## Ist-Zustand (alles Postgres)
- `kg_entities` + `kg_relations` — typisierter Entitäten-Graph (subject→predicate→object).
- `brain_notes` + `brain_links` — PARA-Notizen, `[[wiki-links]]`, Embeddings, `get_graph_data()`.
- `memories` (LZG-Fakten) — category/confidence, **`kg_linked`**-Flag (Brücke Fakt↔Entität angelegt).

## Architektur — Unified-Graph-Leselayer
Neues Modul `domains/knowledge_graph.py`:
- `unified_graph(notes, entities, facts, note_links, relations, mentions) -> {nodes, edges}` —
  **reine Projektion** (injizierbare Daten → TDD). Knoten mit `kind` (note|entity|fact) + Farbe/Gruppe;
  Kanten mit `kind` (link|relation|mention).
- Ein dünner Sammler zieht die Daten aus den Stores und ruft die reine Funktion.
- Endpoint `GET /api/knowledge/graph` (Filter `kinds`, `limit`).

## Zettelkasten (auf der Notiz-Schicht, `domains/second_brain.py`)
- **Folgezettel-IDs:** neue Spalte `brain_notes.zettel_id TEXT UNIQUE`. Luhmann-Alternation nach
  Tiefe: `1 → 1a → 1a1 → 1a1a` (Ebene gerade = Zahl, ungerade = Buchstabe).
  - `next_zettel_id(existing_ids, parent=None)` — **reine Funktion**, TDD. Kind von `1a` → `1a1`
    (bzw. nächstes freies `1a2`…); Geschwister/Top-Level → nächste Zahl (`2`).
  - `add_note(..., parent_id=None)` vergibt die ID beim Anlegen.
- **[[zettel_id]]-Referenzen:** `_resolve_wiki_links` matcht zusätzlich reine IDs (`[[1a1]]`) gegen
  `zettel_id`, nicht nur Titel.
- **Backlinks:** `get_backlinks(note_id)` → Notizen mit `brain_links.to_id = note_id`.

## Auto-Linking (beim Speichern)
- **Erwähnungen:** Entitätsnamen/Aliase aus `kg_entities` im Notiztext finden → `mention`-Kante
  (schlanke `note_entity_mentions`-Tabelle, idempotent neu berechnet je Notiz).
- **Ähnlichkeit:** Top-k nächste Notizen via Embedding (`search_notes`) → als Vorschlags-Kanten
  in den Graph (Kind `similar`), nicht in `brain_links` (kuratiert bleibt kuratiert).

## Frontend — Wissensgraph-Overlay (`apps/desktop/`)
- `knowledge-graph-overlay.ts` — Vollbild-Force-Graph (reuse `renderGraph`), fetcht
  `/api/knowledge/graph`. Filter nach `kind`/Kategorie; Klick auf Knoten → Detail-Panel
  (Titel/Inhalt-Ausschnitt, **Backlinks**, ausgehende Links). Öffnen per Cmd/Ctrl+K-Kachel
  „Wissen" oder Voice-Event. Reine Render-/Filter-Helfer per vitest getestet.

## Phasen (Umsetzung)
1. Folgezettel-IDs (TDD) + Migration + add_note-Integration + `[[id]]`-Resolve.
2. Backlinks + `unified_graph()` (TDD) + Endpoint.
3. Auto-Linking (Erwähnungen + Ähnlichkeit).
4. Frontend Graph-Overlay + Wiring + vitest.

## Nicht-Ziele
- Kein Wegwerfen der Vergessens-/PARA-/Typ-Semantik (Projektion, kein Merge).
- Kein echter Obsidian-Vault / keine Datei-Migration.
