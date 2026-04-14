import aiosqlite
import os

DB_PATH = os.environ.get("CES_DB_PATH", "ces.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    color TEXT NOT NULL DEFAULT '#4f9eff',
    icon TEXT NOT NULL DEFAULT '📁',
    time_available TEXT,
    allow_cross_track BOOLEAN DEFAULT 0,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    layer TEXT NOT NULL CHECK(layer IN ('strategic','tactical','operational','technical')),
    type TEXT NOT NULL CHECK(type IN ('task','idea','problem','hypothesis','instruction','thinking')),
    scope TEXT NOT NULL CHECK(scope IN ('local','cluster','global')),
    cluster TEXT,
    track_id INTEGER REFERENCES tracks(id),
    status TEXT NOT NULL DEFAULT 'inbox' CHECK(status IN ('inbox','next','doing','done','backlog','wishful')),
    priority REAL DEFAULT 0.0,
    energy_required TEXT DEFAULT 'medium' CHECK(energy_required IN ('low','medium','high')),
    duration_minutes INTEGER DEFAULT 30,
    parent_id INTEGER REFERENCES items(id),
    goal_id INTEGER,
    sort_order INTEGER DEFAULT 0,
    -- ADHD scheduling fields
    cognitive_load TEXT DEFAULT 'medium' CHECK(cognitive_load IN ('low','medium','high')),
    dopamine_profile TEXT DEFAULT 'neutral' CHECK(dopamine_profile IN ('quick_reward','delayed_reward','neutral')),
    initiation_friction TEXT DEFAULT 'medium' CHECK(initiation_friction IN ('low','medium','high')),
    completion_visibility TEXT DEFAULT 'visible' CHECK(completion_visibility IN ('visible','invisible')),
    skip_count INTEGER DEFAULT 0,
    resistance_flag BOOLEAN DEFAULT 0,
    -- Expanding task / thinking task fields
    execution_class TEXT DEFAULT 'linear' CHECK(execution_class IN ('linear','modular','expanding')),
    expanded BOOLEAN DEFAULT 0,
    source_idea_id INTEGER REFERENCES items(id),
    thinking_objective TEXT,
    thinking_output_format TEXT,
    thinking_output TEXT,
    revisit_count INTEGER DEFAULT 0,
    complexity_score REAL DEFAULT 5.0,
    depends_on INTEGER REFERENCES items(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS task_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES items(id),
    event TEXT NOT NULL CHECK(event IN ('started','completed','skipped','paused','resumed')),
    elapsed_seconds INTEGER,
    user_energy TEXT,
    user_focus TEXT,
    user_momentum TEXT,
    time_of_day TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    summary TEXT NOT NULL,
    description TEXT,
    cluster TEXT,
    target_date TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','achieved','archived')),
    priority_rank INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS plan_items (
    plan_id INTEGER NOT NULL REFERENCES plans(id),
    item_id INTEGER NOT NULL REFERENCES items(id),
    role TEXT NOT NULL CHECK(role IN ('now','next','later')),
    PRIMARY KEY (plan_id, item_id)
);

CREATE TABLE IF NOT EXISTS inbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_input TEXT NOT NULL,
    parsed_json TEXT,
    approved BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS system_state (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS work_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster TEXT NOT NULL,
    layer TEXT NOT NULL,
    cognitive_load TEXT NOT NULL,
    energy_required TEXT NOT NULL,
    time_of_day TEXT NOT NULL,
    duration_bucket TEXT NOT NULL,
    sample_count INTEGER DEFAULT 1,
    avg_elapsed_seconds REAL NOT NULL,
    avg_estimated_seconds REAL NOT NULL,
    speed_ratio REAL NOT NULL DEFAULT 1.0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_persona (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS checkins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    energy INTEGER NOT NULL CHECK(energy BETWEEN 1 AND 5),
    focus INTEGER NOT NULL CHECK(focus BETWEEN 1 AND 5),
    mood TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS onboarding_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL CHECK(role IN ('assistant','user')),
    content TEXT NOT NULL,
    extracted_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

INITIAL_STATE = [
    ("current_active_task_id", None),
    ("last_plan_version", "0"),
    ("last_cluster_updated", None),
    ("active_track_id", None),
    ("onboarding_complete", None),
]

DEFAULT_TRACKS = [
    ("Work", "#BF2020", "💼", "09:00-17:00", 0, 0),
    ("Personal", "#a78bfa", "🏠", None, 1, 1),
    ("Errands", "#f59e0b", "🛒", "08:00-21:00", 0, 2),
]

DURATION_BUCKETS = [
    (0, 300, "0-5min"),
    (300, 600, "5-10min"),
    (600, 900, "10-15min"),
    (900, 1200, "15-20min"),
    (1200, 1800, "20-30min"),
    (1800, 2700, "30-45min"),
    (2700, 3600, "45-60min"),
]


def get_duration_bucket(seconds: int) -> str:
    for lo, hi, label in DURATION_BUCKETS:
        if lo <= seconds < hi:
            return label
    return "60min+" if seconds >= 3600 else "0-5min"


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db():
    db = await get_db()
    try:
        await db.executescript(SCHEMA)
        for key, value in INITIAL_STATE:
            await db.execute(
                "INSERT OR IGNORE INTO system_state (key, value) VALUES (?, ?)",
                (key, value),
            )
        # Seed default tracks
        for name, color, icon, time_avail, cross, sort in DEFAULT_TRACKS:
            await db.execute(
                "INSERT OR IGNORE INTO tracks (name, color, icon, time_available, allow_cross_track, sort_order) VALUES (?, ?, ?, ?, ?, ?)",
                (name, color, icon, time_avail, cross, sort),
            )
        # Migrations: add columns that may not exist in older databases
        await _run_migrations(db)
        await db.commit()
    finally:
        await db.close()


async def _run_migrations(db):
    """Add columns/tables that were introduced after initial schema."""
    migrations = [
        # Phase 3: Thinking task convergence
        ("items", "thinking_time_budget_minutes", "ALTER TABLE items ADD COLUMN thinking_time_budget_minutes INTEGER DEFAULT 60"),
        ("items", "thinking_time_spent", "ALTER TABLE items ADD COLUMN thinking_time_spent INTEGER DEFAULT 0"),
        # Phase 4: Resistance taxonomy
        ("items", "dominant_skip_reason", "ALTER TABLE items ADD COLUMN dominant_skip_reason TEXT"),
        ("task_history", "skip_reason_category", "ALTER TABLE task_history ADD COLUMN skip_reason_category TEXT"),
        # Phase 5: Goal fields
        ("goals", "description", "ALTER TABLE goals ADD COLUMN description TEXT"),
        ("goals", "target_date", "ALTER TABLE goals ADD COLUMN target_date TEXT"),
        ("goals", "status", "ALTER TABLE goals ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"),
        ("goals", "priority_rank", "ALTER TABLE goals ADD COLUMN priority_rank INTEGER DEFAULT 0"),
        # Dependency DAG
        ("items", "depends_on", "ALTER TABLE items ADD COLUMN depends_on INTEGER REFERENCES items(id)"),
    ]
    for table, column, sql in migrations:
        if sql is None:
            continue
        try:
            await db.execute(sql)
        except Exception:
            pass  # Column already exists
