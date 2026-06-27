"""
Zentrale Datenbank-Schicht für Alfred.
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


def init_pool(minconn: int = 1, maxconn: int = 20) -> None:
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
        author      TEXT DEFAULT 'timo',        -- timo | alfred
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

    # Reiches Task-System (alfred-nativ): Arten, Unteraufgaben, Fortschritt, Archiv
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
    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS assigned_to TEXT DEFAULT 'user';",
    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS alfred_result TEXT;",
    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS rejection_reason TEXT;",
    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS suggestion_status TEXT;",
    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS execution_phase TEXT DEFAULT 'pending';",
    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS clarification_question TEXT;",
    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS clarification_answer TEXT;",
    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS hold_until TIMESTAMPTZ;",

    # Alfred' eigene Agenda (autonome To-dos)
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

    # Event-Log (alles was Alfred tut → fürs Dashboard "Mind"/Activity)
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

    # Health (alfred-nativ, gespeist aus iCloud Health.json – unabhängig von ai-dashboard)
    """
    CREATE TABLE IF NOT EXISTS health_data (
        date             DATE PRIMARY KEY,
        steps            INT,
        active_calories  INT,
        exercise_minutes INT,
        stand_hours      INT,
        distance         DOUBLE PRECISION,
        weight           DOUBLE PRECISION,
        body_fat         DOUBLE PRECISION,
        bmi              DOUBLE PRECISION,
        resting_hr       INT,
        hr_avg           INT,
        hr_max           INT,
        hr_min           INT,
        hrv              DOUBLE PRECISION,
        vo2max           DOUBLE PRECISION,
        sleep_duration   DOUBLE PRECISION,
        sleep_deep       DOUBLE PRECISION,
        sleep_rem        DOUBLE PRECISION,
        sleep_core       DOUBLE PRECISION,
        sleep_awake      DOUBLE PRECISION,
        blood_oxygen     DOUBLE PRECISION,
        body_temp        DOUBLE PRECISION,
        calories         INT,
        protein          DOUBLE PRECISION,
        carbs            DOUBLE PRECISION,
        fat              DOUBLE PRECISION,
        water            DOUBLE PRECISION,
        updated_at       TIMESTAMPTZ DEFAULT NOW()
    );
    """,

    # Kalender (alfred-erstellte Events; gelesene Events kommen live aus ICS)
    """
    CREATE TABLE IF NOT EXISTS calendar_events (
        id          SERIAL PRIMARY KEY,
        uid         TEXT UNIQUE,
        title       TEXT NOT NULL,
        start_ts    TIMESTAMPTZ NOT NULL,
        end_ts      TIMESTAMPTZ,
        all_day     BOOLEAN DEFAULT FALSE,
        location    TEXT,
        notes       TEXT,
        source      TEXT DEFAULT 'alfred',
        created_at  TIMESTAMPTZ DEFAULT NOW()
    );
    """,
    "CREATE INDEX IF NOT EXISTS health_date_idx ON health_data(date DESC);",
    "CREATE INDEX IF NOT EXISTS calevents_start_idx ON calendar_events(start_ts);",

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
    "ALTER TABLE journal_entries ADD COLUMN IF NOT EXISTS prompts_answers JSONB;",
    "ALTER TABLE memories ADD COLUMN IF NOT EXISTS importance FLOAT DEFAULT 0.5;",
    "ALTER TABLE memories ADD COLUMN IF NOT EXISTS recall_count INTEGER DEFAULT 0;",
    "ALTER TABLE memories ADD COLUMN IF NOT EXISTS last_recalled TIMESTAMPTZ;",
    "ALTER TABLE memories ADD COLUMN IF NOT EXISTS kg_linked BOOLEAN DEFAULT FALSE;",
    "CREATE INDEX IF NOT EXISTS agenda_status_idx ON agenda(status, run_after);",
    "CREATE INDEX IF NOT EXISTS events_log_created_idx ON events_log(created_at DESC);",
    "CREATE INDEX IF NOT EXISTS chat_messages_created_idx ON chat_messages(created_at DESC);",

    # Schema-Drift-Fixes: diese Spalten/Tabellen existierten nur noch in der laufenden
    # DB (aus einer älteren, inzwischen entfernten Migration), nicht mehr im Code.
    # Ohne diese Statements würde eine Neuinstallation/ein Restore kaputt starten.
    "ALTER TABLE habits ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'day';",
    "ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS gcal_id TEXT;",
    """
    CREATE TABLE IF NOT EXISTS kg_entities (
        id          SERIAL PRIMARY KEY,
        name        TEXT NOT NULL,
        type        TEXT NOT NULL,
        description TEXT,
        aliases     TEXT[] DEFAULT '{}',
        created_at  TIMESTAMPTZ DEFAULT NOW(),
        updated_at  TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE (name, type)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS kg_relations (
        id          SERIAL PRIMARY KEY,
        subject_id  INTEGER NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
        predicate   TEXT NOT NULL,
        object_id   INTEGER NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
        context     TEXT,
        confidence  FLOAT DEFAULT 0.8,
        source      TEXT DEFAULT 'extract',
        created_at  TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE (subject_id, predicate, object_id)
    );
    """,

    # Web-Push-Subscriptions (PWA-Benachrichtigungen)
    """
    CREATE TABLE IF NOT EXISTS push_subscriptions (
        id          SERIAL PRIMARY KEY,
        endpoint    TEXT NOT NULL UNIQUE,
        p256dh      TEXT NOT NULL,
        auth        TEXT NOT NULL,
        created_at  TIMESTAMPTZ DEFAULT NOW()
    );
    """,

    # Second Brain – Notizen & Verlinkungen
    """
    CREATE TABLE IF NOT EXISTS brain_notes (
        id          SERIAL PRIMARY KEY,
        title       TEXT NOT NULL,
        content     TEXT NOT NULL DEFAULT '',
        category    TEXT NOT NULL DEFAULT 'inbox',
        tags        TEXT[] DEFAULT '{}',
        status      TEXT NOT NULL DEFAULT 'active',
        pinned      BOOLEAN DEFAULT FALSE,
        embedding   vector(768),
        created_at  TIMESTAMPTZ DEFAULT NOW(),
        updated_at  TIMESTAMPTZ DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS brain_links (
        from_id  INTEGER NOT NULL REFERENCES brain_notes(id) ON DELETE CASCADE,
        to_id    INTEGER NOT NULL REFERENCES brain_notes(id) ON DELETE CASCADE,
        PRIMARY KEY (from_id, to_id)
    );
    """,
    "CREATE INDEX IF NOT EXISTS brain_notes_category_idx ON brain_notes (category);",
    "CREATE INDEX IF NOT EXISTS brain_notes_embedding_idx ON brain_notes USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL;",
    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS today_focus BOOLEAN DEFAULT FALSE;",
    """CREATE TABLE IF NOT EXISTS body_measurements (
        id          SERIAL PRIMARY KEY,
        date        DATE NOT NULL DEFAULT CURRENT_DATE,
        weight_kg   FLOAT,
        waist_cm    FLOAT,
        chest_cm    FLOAT,
        hips_cm     FLOAT,
        bicep_cm    FLOAT,
        thigh_cm    FLOAT,
        neck_cm     FLOAT,
        body_fat    FLOAT,
        notes       TEXT,
        created_at  TIMESTAMPTZ DEFAULT NOW()
    );""",
    "CREATE UNIQUE INDEX IF NOT EXISTS body_measurements_date_idx ON body_measurements (date);",
    """CREATE TABLE IF NOT EXISTS training_cycle_events (
        id          SERIAL PRIMARY KEY,
        date        DATE NOT NULL DEFAULT CURRENT_DATE,
        slot        TEXT NOT NULL,
        kind        TEXT NOT NULL,
        created_at  TIMESTAMPTZ DEFAULT NOW()
    );""",
    "CREATE INDEX IF NOT EXISTS training_cycle_events_date_idx ON training_cycle_events (date DESC, id DESC);",
    "ALTER TABLE workout_sets ADD COLUMN IF NOT EXISTS rpe INT;",
    "ALTER TABLE workout_sets ADD COLUMN IF NOT EXISTS is_warmup BOOLEAN DEFAULT FALSE;",
    "ALTER TABLE workout_sets ADD COLUMN IF NOT EXISTS is_failure BOOLEAN DEFAULT FALSE;",
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
    """Schreibt einen Eintrag ins Event-Log (fürs Dashboard 'Alfred Mind')."""
    import json
    try:
        execute(
            "INSERT INTO events_log (type, summary, detail) VALUES (%s, %s, %s)",
            (type_, summary[:500], json.dumps(detail or {})),
        )
    except Exception as e:
        log.debug(f"log_event fehlgeschlagen: {e}")


def log_error(source: str, exc: Exception) -> None:
    """Protokolliert einen Fehler fürs Dashboard-Widget 'Was ist heute schiefgelaufen'.
    Bewusst nur an den wichtigsten Stellen genutzt (nicht jeder der ~200 try/except-Blöcke
    im Code), damit das Widget auf echte Feature-Ausfälle zeigt statt auf Rauschen."""
    log_event("error", f"{source}: {exc}", {"source": source, "error": str(exc)})
