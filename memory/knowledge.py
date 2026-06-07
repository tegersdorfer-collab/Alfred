"""
memory/knowledge.py

Wissens-Graph (Knowledge Graph) für Jarvis.
Speichert Entitäten (Personen, Orte, Projekte …) und ihre Relationen relational
in PostgreSQL – ergänzt den Vektor-Store (LZG) um strukturierte Beziehungen.

Beispiel:
    Anna  -[ist_schwester_von]→  Timo
    Jarvis -[ist_projekt_von]→   Timo
    Nürnberg -[ist_wohnort_von]→ Timo

Entity-Typen: person | place | project | organization | concept | habit | goal
Prädikate (Beispiele):
    ist_schwester_von, ist_bruder_von, ist_freund_von, ist_partner_von,
    ist_mutter_von, ist_vater_von, ist_kollege_von,
    wohnt_in, studiert_in, arbeitet_bei,
    arbeitet_an, besitzt, plant, hat_ziel, ist_mitglied_von
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from core import db as _db

log = logging.getLogger(__name__)


@dataclass
class Entity:
    id: int
    name: str
    type: str
    description: Optional[str]
    aliases: list[str]
    created_at: datetime


@dataclass
class Relation:
    id: int
    subject: Entity
    predicate: str
    object: Entity
    context: Optional[str]
    confidence: float
    created_at: datetime


class KnowledgeGraph:
    """
    Relationale Wissensstruktur in PostgreSQL.
    Alle Schreib-Ops sind idempotent (UPSERT / ON CONFLICT DO NOTHING).
    """

    # ── Entitäten ──────────────────────────────────────────────────────────────

    def upsert_entity(
        self,
        name: str,
        type_: str,
        description: str | None = None,
        aliases: list[str] | None = None,
    ) -> int:
        """Legt Entität an oder aktualisiert Beschreibung. Gibt ID zurück."""
        row = _db.query_one(
            "SELECT id FROM kg_entities WHERE name = %s AND type = %s",
            (name, type_),
        )
        if row:
            eid = row["id"]
            if description:
                _db.execute(
                    "UPDATE kg_entities SET description = %s, updated_at = NOW() WHERE id = %s",
                    (description, eid),
                )
            if aliases:
                _db.execute(
                    "UPDATE kg_entities SET aliases = aliases || %s::text[], updated_at = NOW() WHERE id = %s",
                    (aliases, eid),
                )
            return eid
        with _db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO kg_entities (name, type, description, aliases)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (name, type) DO UPDATE
                    SET description = COALESCE(EXCLUDED.description, kg_entities.description),
                        updated_at  = NOW()
                RETURNING id
                """,
                (name, type_, description, aliases or []),
            )
            return cur.fetchone()["id"]

    def get_entity(self, name: str, type_: str | None = None) -> Entity | None:
        if type_:
            row = _db.query_one(
                "SELECT * FROM kg_entities WHERE name ILIKE %s AND type = %s LIMIT 1",
                (name, type_),
            )
        else:
            row = _db.query_one(
                "SELECT * FROM kg_entities WHERE name ILIKE %s LIMIT 1",
                (name,),
            )
        return _row_to_entity(row) if row else None

    def search_entities(self, query: str) -> list[Entity]:
        """Findet Entitäten per Namens-Suche (auch Aliases)."""
        rows = _db.query(
            """
            SELECT * FROM kg_entities
            WHERE name ILIKE %s OR %s ILIKE ANY(aliases)
            ORDER BY updated_at DESC LIMIT 10
            """,
            (f"%{query}%", query),
        )
        return [_row_to_entity(r) for r in rows]

    # ── Relationen ─────────────────────────────────────────────────────────────

    def upsert_relation(
        self,
        subject_id: int,
        predicate: str,
        object_id: int,
        context: str | None = None,
        confidence: float = 0.8,
        source: str = "extract",
    ) -> int:
        """Legt Relation an oder ignoriert Duplikat. Gibt ID zurück."""
        with _db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO kg_relations (subject_id, predicate, object_id, context, confidence, source)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (subject_id, predicate, object_id) DO UPDATE
                    SET confidence = GREATEST(kg_relations.confidence, EXCLUDED.confidence),
                        context    = COALESCE(EXCLUDED.context, kg_relations.context)
                RETURNING id
                """,
                (subject_id, predicate, object_id, context, confidence, source),
            )
            return cur.fetchone()["id"]

    def get_relations(
        self,
        entity_id: int,
        direction: str = "both",  # "out" | "in" | "both"
    ) -> list[Relation]:
        """Alle Relationen einer Entität."""
        if direction == "out":
            where = "r.subject_id = %s"
        elif direction == "in":
            where = "r.object_id = %s"
        else:
            where = "(r.subject_id = %s OR r.object_id = %s)"

        params = (entity_id,) if direction != "both" else (entity_id, entity_id)
        rows = _db.query(
            f"""
            SELECT r.*,
                   s.id as s_id, s.name as s_name, s.type as s_type,
                   s.description as s_desc, s.aliases as s_aliases, s.created_at as s_created,
                   o.id as o_id, o.name as o_name, o.type as o_type,
                   o.description as o_desc, o.aliases as o_aliases, o.created_at as o_created
            FROM kg_relations r
            JOIN kg_entities s ON r.subject_id = s.id
            JOIN kg_entities o ON r.object_id   = o.id
            WHERE {where}
            ORDER BY r.confidence DESC, r.created_at DESC
            """,
            params,
        )
        return [_row_to_relation(r) for r in rows]

    def context_for_names(self, names: list[str]) -> str:
        """
        Gibt Wissens-Graph-Kontext für genannte Namen zurück.
        Wird in den System-Prompt eingefügt wenn Timo über bekannte Personen/Orte spricht.
        """
        if not names:
            return ""
        lines = []
        for name in names:
            entities = self.search_entities(name)
            for ent in entities[:1]:  # nur bester Treffer pro Name
                rels = self.get_relations(ent.id)
                if not rels:
                    lines.append(f"- {ent.name} ({ent.type})")
                    continue
                for r in rels[:4]:
                    subj = r.subject.name
                    obj  = r.object.name
                    pred = r.predicate.replace("_", " ")
                    lines.append(f"- {subj} {pred} {obj}")
        if not lines:
            return ""
        return "## Bekannte Personen & Orte\n" + "\n".join(lines)

    # ── Memory-Verknüpfung ─────────────────────────────────────────────────────

    def link_memory(self, memory_id: int, entity_id: int) -> None:
        """Verknüpft eine Memory mit einer Entität (schützt sie vor Vergessen)."""
        _db.execute(
            """
            INSERT INTO kg_memory_entities (memory_id, entity_id)
            VALUES (%s, %s) ON CONFLICT DO NOTHING
            """,
            (memory_id, entity_id),
        )
        _db.execute(
            "UPDATE memories SET kg_linked = TRUE WHERE id = %s",
            (memory_id,),
        )

    def get_all_entities(self, type_: str | None = None) -> list[Entity]:
        if type_:
            rows = _db.query(
                "SELECT * FROM kg_entities WHERE type = %s ORDER BY name",
                (type_,),
            )
        else:
            rows = _db.query("SELECT * FROM kg_entities ORDER BY type, name")
        return [_row_to_entity(r) for r in rows]

    def format_for_context(self) -> str:
        """Kompakter Überblick aller KG-Entitäten und Relationen für den System-Prompt."""
        entities = self.get_all_entities()
        if not entities:
            return ""
        lines = ["## Wissens-Graph"]
        for ent in entities:
            rels = self.get_relations(ent.id, direction="out")
            if rels:
                for r in rels[:3]:
                    lines.append(f"- {r.subject.name} → {r.predicate.replace('_',' ')} → {r.object.name}")
            elif ent.description:
                lines.append(f"- {ent.name} ({ent.type}): {ent.description}")
            else:
                lines.append(f"- {ent.name} ({ent.type})")
        return "\n".join(lines)


# ── Helfer ─────────────────────────────────────────────────────────────────────

def _row_to_entity(r: dict) -> Entity:
    return Entity(
        id=r["id"], name=r["name"], type=r["type"],
        description=r.get("description"),
        aliases=r.get("aliases") or [],
        created_at=r["created_at"],
    )


def _row_to_relation(r: dict) -> Relation:
    subj = Entity(id=r["s_id"], name=r["s_name"], type=r["s_type"],
                  description=r.get("s_desc"), aliases=r.get("s_aliases") or [],
                  created_at=r["s_created"])
    obj  = Entity(id=r["o_id"], name=r["o_name"], type=r["o_type"],
                  description=r.get("o_desc"), aliases=r.get("o_aliases") or [],
                  created_at=r["o_created"])
    return Relation(
        id=r["id"], subject=subj, predicate=r["predicate"], object=obj,
        context=r.get("context"), confidence=r["confidence"],
        created_at=r["created_at"],
    )
