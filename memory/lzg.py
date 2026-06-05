"""
Langzeitgedächtnis (LZG) – persistente Vektordatenbank via pgvector.
Speichert komprimierte Fakten, Muster und Erkenntnisse über Timo.
"""
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np
import psycopg2
from pgvector.psycopg2 import register_vector

import config


@dataclass
class Memory:
    id: int
    content: str
    category: str          # "fact" | "pattern" | "goal" | "correction" | "context"
    confidence: float      # 0.0 – 1.0
    created_at: datetime
    last_verified: Optional[datetime]
    metadata: dict


class LZG:
    """
    Langzeitgedächtnis mit semantischer Suche (pgvector).
    Alle Fakten und Erkenntnisse über Timo werden hier gespeichert.
    """

    def __init__(self):
        self._conn = None

    def close(self) -> None:
        if self._conn and not self._conn.closed:
            self._conn.close()
            self._conn = None

    def _get_conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(config.DATABASE_URL)
            register_vector(self._conn)
        return self._conn

    def setup(self) -> None:
        """Erstellt Tabellen falls nicht vorhanden."""
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id           SERIAL PRIMARY KEY,
                    content      TEXT NOT NULL,
                    embedding    vector(768),
                    category     TEXT DEFAULT 'fact',
                    confidence   FLOAT DEFAULT 0.8,
                    created_at   TIMESTAMPTZ DEFAULT NOW(),
                    last_verified TIMESTAMPTZ,
                    metadata     JSONB DEFAULT '{}'
                );
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS memories_embedding_idx
                ON memories USING hnsw (embedding vector_cosine_ops);
            """)
            # KZG-Persistenz: letzte Gespräche über Restarts hinweg
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kzg_sessions (
                    id         SERIAL PRIMARY KEY,
                    role       TEXT NOT NULL,
                    content    TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            conn.commit()

    def save(
        self,
        content: str,
        embedding: list[float] | np.ndarray,
        category: str = "fact",
        confidence: float = 0.8,
        metadata: dict | None = None,
    ) -> int:
        """Speichert eine neue Erinnerung. Gibt ID zurück."""
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO memories (content, embedding, category, confidence, metadata)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (content, np.array(embedding), category, confidence,
                 json.dumps(metadata or {})),
            )
            memory_id = cur.fetchone()[0]
            conn.commit()
            return memory_id

    def search(
        self,
        query_embedding: list[float] | np.ndarray,
        top_k: int | None = None,
        category: str | None = None,
        min_confidence: float = 0.3,
    ) -> list[Memory]:
        """Semantische Suche im Langzeitgedächtnis."""
        k = top_k or config.LZG_TOP_K
        conn = self._get_conn()

        where = "confidence >= %s"
        params: list = [min_confidence]

        if category:
            where += " AND category = %s"
            params.append(category)

        params.append(np.array(query_embedding))
        params.append(k)

        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, content, category, confidence,
                       created_at, last_verified, metadata
                FROM memories
                WHERE {where}
                ORDER BY embedding <=> %s
                LIMIT %s
                """,
                params,
            )
            rows = cur.fetchall()

        return [
            Memory(
                id=r[0], content=r[1], category=r[2],
                confidence=r[3], created_at=r[4],
                last_verified=r[5], metadata=r[6] or {},
            )
            for r in rows
        ]

    def get_all(self, category: str | None = None, limit: int = 50) -> list[Memory]:
        """Alle Memories abrufen (ohne Vektor-Suche)."""
        conn = self._get_conn()
        with conn.cursor() as cur:
            if category:
                cur.execute(
                    """
                    SELECT id, content, category, confidence,
                           created_at, last_verified, metadata
                    FROM memories
                    WHERE category = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (category, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT id, content, category, confidence,
                           created_at, last_verified, metadata
                    FROM memories
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
            rows = cur.fetchall()

        return [
            Memory(
                id=r[0], content=r[1], category=r[2],
                confidence=r[3], created_at=r[4],
                last_verified=r[5], metadata=r[6] or {},
            )
            for r in rows
        ]

    def find_similar(
        self,
        embedding: list[float] | np.ndarray,
        threshold: float = 0.12,   # cosine distance (0 = identisch, <0.15 = sehr ähnlich)
        top_k: int = 3,
    ) -> list[tuple["Memory", float]]:
        """
        Findet Memories die semantisch sehr ähnlich sind.
        Gibt Liste von (Memory, distance) zurück – kleinste distance = ähnlichster.
        """
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, content, category, confidence,
                       created_at, last_verified, metadata,
                       embedding <=> %s AS distance
                FROM memories
                ORDER BY embedding <=> %s
                LIMIT %s
                """,
                (np.array(embedding), np.array(embedding), top_k),
            )
            rows = cur.fetchall()

        result = []
        for r in rows:
            dist = float(r[7])
            if dist <= threshold:
                mem = Memory(
                    id=r[0], content=r[1], category=r[2],
                    confidence=r[3], created_at=r[4],
                    last_verified=r[5], metadata=r[6] or {},
                )
                result.append((mem, dist))
        return result

    def update_confidence(self, memory_id: int, confidence: float) -> None:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE memories SET confidence = %s, last_verified = NOW() WHERE id = %s",
                (confidence, memory_id),
            )
            conn.commit()

    def delete(self, memory_id: int) -> None:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM memories WHERE id = %s", (memory_id,))
            conn.commit()

    # ── KZG-Session-Persistenz ──────────────────────────────────────────────

    def save_kzg_turn(self, role: str, content: str) -> None:
        """Speichert einen KZG-Turn persistent in der DB."""
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO kzg_sessions (role, content) VALUES (%s, %s)",
                (role, content),
            )
            conn.commit()

    def load_recent_kzg(self, max_turns: int = 10) -> list[dict]:
        """Lädt die letzten N Turns aus der letzten Session."""
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT role, content FROM kzg_sessions
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (max_turns,),
            )
            rows = cur.fetchall()
        # Umkehren damit älteste zuerst (Chronologie)
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

    def clear_kzg_sessions(self, keep_last: int = 20) -> None:
        """Löscht alte KZG-Turns, behält nur die letzten N."""
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM kzg_sessions
                WHERE id NOT IN (
                    SELECT id FROM kzg_sessions
                    ORDER BY created_at DESC
                    LIMIT %s
                )
                """,
                (keep_last,),
            )
            conn.commit()

    def format_for_context(self, memories: list[Memory]) -> str:
        """Formatiert Memories als lesbaren Kontext für System-Prompt."""
        if not memories:
            return "Noch keine Langzeiterinnerungen vorhanden."
        lines = []
        for m in memories:
            conf_str = f"({int(m.confidence * 100)}% sicher)"
            lines.append(f"[{m.category.upper()}] {m.content} {conf_str}")
        return "\n".join(lines)
