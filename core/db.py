"""
Zentrale Datenbank-Schicht für Jarvis.
- Connection-Pool (thread-safe)
- pgvector-Registrierung pro Connection
- Sync- und Async-Helfer (Async läuft im Thread-Executor)
- Idempotenter Migrations-Runner
"""
import asyncio
import logging
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
import psycopg2.pool
from pgvector.psycopg2 import register_vector

import config

log = logging.getLogger(__name__)

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def init_pool(minconn: int = 1, maxconn: int = 8) -> None:
    global _pool
    if _pool is not None:
        return
    _pool = psycopg2.pool.ThreadedConnectionPool(
        minconn, maxconn, dsn=config.DATABASE_URL
    )
    log.info(f"DB-Pool initialisiert ({minconn}-{maxconn} Connections)")


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


@contextmanager
def cursor(dict_rows: bool = True, vector: bool = False):
    """Borgt eine Connection aus dem Pool, gibt einen Cursor, committet automatisch."""
    if _pool is None:
        init_pool()
    conn = _pool.getconn()
    try:
        if vector:
            register_vector(conn)
        factory = psycopg2.extras.RealDictCursor if dict_rows else None
        cur = conn.cursor(cursor_factory=factory)
        try:
            yield cur
            conn.commit()
        finally:
            cur.close()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


# ── Sync-Helfer ──────────────────────────────────────────────────────────────

def query(sql: str, params: tuple = ()) -> list[dict]:
    with cursor() as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def query_one(sql: str, params: tuple = ()) -> dict | None:
    with cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None


def execute(sql: str, params: tuple = ()) -> int:
    with cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount


def insert_returning(sql: str, params: tuple = ()):
    with cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        if row is None:
            return None
        # RealDictCursor → erstes Value
        return list(row.values())[0]


# ── Async-Helfer (DB-Calls in Thread, damit Event-Loop frei bleibt) ──────────

async def aquery(sql: str, params: tuple = ()) -> list[dict]:
    return await asyncio.to_thread(query, sql, params)


async def aquery_one(sql: str, params: tuple = ()) -> dict | None:
    return await asyncio.to_thread(query_one, sql, params)


async def aexecute(sql: str, params: tuple = ()) -> int:
    return await asyncio.to_thread(execute, sql, params)


async def ainsert_returning(sql: str, params: tuple = ()):
    return await asyncio.to_thread(insert_returning, sql, params)


# ── Migrationen ──────────────────────────────────────────────────────────────

MIGRATIONS = [
    # pgvector + Memories existieren bereits via LZG.setup(); hier alles Neue.

    # Habits
    """
    CREATE TABLE IF NOT EXISTS habits (
        id          SERIAL PRIMARY KEY,
        name        TEXT NOT NULL,
        emoji       TEXT DEFAULT '✅',
        cadence     TEXT DEFAULT 'daily',      -- daily | weekly | custom
        target_per_week INT DEFAULT 7,
        color       TEXT DEFAULT '#0ea5e9',
        active      BOOLEAN DEFAULT TRUE,
        sort_order  INT DEFAULT 0,
        created_at  TIMESTAMPTZ DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS habit_logs (
        id        SERIAL PRIMARY KEY,
        habit_id  INT REFERENCES habits(id) ON DELETE CASCADE,
        date      DATE NOT NULL,
        done      BOOLEAN DEFAULT TRUE,
        note      TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE (habit_id, date)
    );
    """,

    # Fitness
    """
    CREATE TABLE IF NOT EXISTS exercises (
        id          SERIAL PRIMARY KEY,
        name        TEXT NOT NULL UNIQUE,
        category    TEXT DEFAULT 'strength',   -- strength | cardio | mobility
        muscle      TEXT,
        unit        TEXT DEFAULT 'reps',       -- reps | km | min
        created_at  TIMESTAMPTZ DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS workouts (
        id          SERIAL PRIMARY KEY,
        date        DATE NOT NULL DEFAULT CURRENT_DATE,
        title       TEXT,
        type        TEXT DEFAULT 'strength',   -- strength | run | mobility | other
        duration_min INT,
        distance_km DOUBLE PRECISION,
        notes       TEXT,
        rpe         INT,                        -- rate of perceived exertion 1-10
        created_at  TIMESTAMPTZ DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS workout_sets (
        id          SERIAL PRIMARY KEY,
        workout_id  INT REFERENCES workouts(id) ON DELETE CASCADE,
        exercise_id INT REFERENCES exercises(id),
        set_index   INT DEFAULT 1,
        reps        INT,
        weight_kg   DOUBLE PRECISION,
        distance_km DOUBLE PRECISION,
        duration_s  INT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS training_plans (
        id          SERIAL PRIMARY KEY,
        name        TEXT NOT NULL,
        goal        TEXT,
        weeks       INT DEFAULT 8,
        plan_json   JSONB DEFAULT '{}',
        active      BOOLEAN DEFAULT TRUE,
        created_at  TIMESTAMPTZ DEFAULT NOW()
    );
    """,

    # Journal
    """
    CREATE TABLE IF NOT EXISTS journal_entries (
        id          SERIAL PRIMARY KEY,
        date        DATE NOT NULL DEFAULT CURRENT_DATE,
        mood        INT,                        -- 1-5
        energy      INT,                        -- 1-5
        content     TEXT,
        tags        TEXT[],
        author      TEXT DEFAULT 'timo',        -- timo | jarvis
        created_at  TIMESTAMPTZ DEFAULT NOW()
    );
    """,

    # Ernährung
    """
    CREATE TABLE IF NOT EXISTS meals (
        id          SERIAL PRIMARY KEY,
        date        DATE NOT NULL DEFAULT CURRENT_DATE,
        meal_type   TEXT DEFAULT 'snack',       -- breakfast | lunch | dinner | snack
        description TEXT NOT NULL,
        calories    INT,
        protein_g   DOUBLE PRECISION,
        carbs_g     DOUBLE PRECISION,
        fat_g       DOUBLE PRECISION,
        created_at  TIMESTAMPTZ DEFAULT NOW()
    );
    """,

    # Ziele
    """
    CREATE TABLE IF NOT EXISTS goals (
        id          SERIAL PRIMARY KEY,
        title       TEXT NOT NULL,
        category    TEXT DEFAULT 'general',     -- fitness | career | finance | personal
        target_value DOUBLE PRECISION,
        current_value DOUBLE PRECISION DEFAULT 0,
        unit        TEXT,
        deadline    DATE,
        status      TEXT DEFAULT 'active',      -- active | done | paused | dropped
        progress_pct INT DEFAULT 0,
        notes       TEXT,
        created_at  TIMESTAMPTZ DEFAULT NOW(),
        updated_at  TIMESTAMPTZ DEFAULT NOW()
    );
    """,

    # Reiches Task-System (jarvis-nativ): Arten, Unteraufgaben, Fortschritt, Archiv
    """
    CREATE TABLE IF NOT EXISTS tasks (
        id           SERIAL PRIMARY KEY,
        title        TEXT NOT NULL,
        notes        TEXT,
        kind         TEXT DEFAULT 'task',       -- task | project | checklist
        status       TEXT DEFAULT 'todo',       -- todo | in_progress | done | archived
        priority     TEXT DEFAULT 'medium',     -- high | medium | low
        progress_pct INT DEFAULT 0,
        parent_id    INT REFERENCES tasks(id) ON DELETE CASCADE,
        due          TIMESTAMPTZ,
        sort_order   INT DEFAULT 0,
        created_at   TIMESTAMPTZ DEFAULT NOW(),
        completed_at TIMESTAMPTZ
    );
    """,
    "CREATE INDEX IF NOT EXISTS tasks_status_idx ON tasks(status);",
    "CREATE INDEX IF NOT EXISTS tasks_parent_idx ON tasks(parent_id);",

    # Jarvis' eigene Agenda (autonome To-dos)
    """
    CREATE TABLE IF NOT EXISTS agenda (
        id          SERIAL PRIMARY KEY,
        kind        TEXT NOT NULL,              -- briefing | checkin | research | nudge | review
        title       TEXT NOT NULL,
        payload     JSONB DEFAULT '{}',
        priority    INT DEFAULT 5,              -- 1 hoch .. 9 niedrig
        run_after   TIMESTAMPTZ DEFAULT NOW(),
        status      TEXT DEFAULT 'pending',     -- pending | done | skipped
        result      TEXT,
        created_at  TIMESTAMPTZ DEFAULT NOW(),
        done_at     TIMESTAMPTZ
    );
    """,

    # Selbst-Reflexionen
    """
    CREATE TABLE IF NOT EXISTS reflections (
        id          SERIAL PRIMARY KEY,
        kind        TEXT DEFAULT 'daily',       -- daily | interaction | weekly
        content     TEXT NOT NULL,
        insights    JSONB DEFAULT '{}',
        created_at  TIMESTAMPTZ DEFAULT NOW()
    );
    """,

    # Chat-Nachrichten (für Dashboard-Chat, kanalübergreifend)
    """
    CREATE TABLE IF NOT EXISTS chat_messages (
        id          SERIAL PRIMARY KEY,
        role        TEXT NOT NULL,              -- user | assistant
        content     TEXT NOT NULL,
        channel     TEXT DEFAULT 'telegram',    -- telegram | dashboard | autopilot
        meta        JSONB DEFAULT '{}',
        created_at  TIMESTAMPTZ DEFAULT NOW()
    );
    """,

    # Event-Log (alles was Jarvis tut → fürs Dashboard "Mind"/Activity)
    """
    CREATE TABLE IF NOT EXISTS events_log (
        id          SERIAL PRIMARY KEY,
        type        TEXT NOT NULL,              -- thought | action | tool | reflection | briefing | error
        summary     TEXT NOT NULL,
        detail      JSONB DEFAULT '{}',
        created_at  TIMESTAMPTZ DEFAULT NOW()
    );
    """,

    # Tägliche Metrik-Snapshots (fürs Dashboard-Trending, schnell)
    """
    CREATE TABLE IF NOT EXISTS metrics_snapshots (
        id          SERIAL PRIMARY KEY,
        date        DATE NOT NULL DEFAULT CURRENT_DATE,
        data        JSONB DEFAULT '{}',
        created_at  TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE (date)
    );
    """,

    # Settings (Key-Value, fürs Dashboard-Konfigurieren)
    """
    CREATE TABLE IF NOT EXISTS settings (
        key         TEXT PRIMARY KEY,
        value       JSONB NOT NULL,
        updated_at  TIMESTAMPTZ DEFAULT NOW()
    );
    """,

    # Indizes
    "CREATE INDEX IF NOT EXISTS habit_logs_date_idx ON habit_logs(date);",
    "CREATE INDEX IF NOT EXISTS workouts_date_idx ON workouts(date);",
    "CREATE INDEX IF NOT EXISTS meals_date_idx ON meals(date);",
    "CREATE INDEX IF NOT EXISTS journal_date_idx ON journal_entries(date);",
    "CREATE INDEX IF NOT EXISTS agenda_status_idx ON agenda(status, run_after);",
    "CREATE INDEX IF NOT EXISTS events_log_created_idx ON events_log(created_at DESC);",
    "CREATE INDEX IF NOT EXISTS chat_messages_created_idx ON chat_messages(created_at DESC);",
]


def run_migrations() -> None:
    """Führt alle Migrationen idempotent aus."""
    init_pool()
    with cursor(dict_rows=False) as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        for stmt in MIGRATIONS:
            cur.execute(stmt)
    log.info(f"Migrationen ausgeführt ({len(MIGRATIONS)} Statements)")


# ── Settings-Helfer ──────────────────────────────────────────────────────────

def get_setting(key: str, default=None):
    row = query_one("SELECT value FROM settings WHERE key = %s", (key,))
    return row["value"] if row else default


def set_setting(key: str, value) -> None:
    import json
    execute(
        """
        INSERT INTO settings (key, value, updated_at) VALUES (%s, %s, NOW())
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
        """,
        (key, json.dumps(value)),
    )


def log_event(type_: str, summary: str, detail: dict | None = None) -> None:
    """Schreibt einen Eintrag ins Event-Log (fürs Dashboard 'Jarvis Mind')."""
    import json
    try:
        execute(
            "INSERT INTO events_log (type, summary, detail) VALUES (%s, %s, %s)",
            (type_, summary[:500], json.dumps(detail or {})),
        )
    except Exception as e:
        log.debug(f"log_event fehlgeschlagen: {e}")
