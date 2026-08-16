"""
brain/memory/db.py

SQLite connection and schema management for the memory module.

Phase 5+ feature. This file creates the schema but memory is disabled
until config.memory.enabled is True.

Database lives at: %LOCALAPPDATA%\Senjougahara\memory.db
(determined by AppConfig.appdata_dir, never configurable to avoid path traversal)

Schema:
  facts(id, key, value, confidence, created_at, updated_at)
  preferences(id, key, value, created_at, updated_at)
  conversation_log(id, role, content, timestamp, summary_batch_id)
"""

from __future__ import annotations

import logging
from pathlib import Path

try:
    import aiosqlite
except ImportError:
    aiosqlite = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS facts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT NOT NULL UNIQUE,
    value       TEXT NOT NULL,
    confidence  REAL NOT NULL DEFAULT 1.0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS preferences (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT NOT NULL UNIQUE,
    value       TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conversation_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    role              TEXT NOT NULL,      -- 'user' | 'assistant' | 'tool'
    content           TEXT NOT NULL,
    timestamp         TEXT NOT NULL DEFAULT (datetime('now')),
    summary_batch_id  INTEGER             -- groups turns that were summarized together
);

CREATE INDEX IF NOT EXISTS idx_facts_key ON facts(key);
CREATE INDEX IF NOT EXISTS idx_prefs_key ON preferences(key);
CREATE INDEX IF NOT EXISTS idx_log_timestamp ON conversation_log(timestamp);
"""


async def initialize_db(db_path: Path) -> None:
    """
    Initialize the SQLite database and create tables if they don't exist.
    Call once at startup if memory is enabled.
    """
    if aiosqlite is None:
        logger.warning("aiosqlite not installed — memory disabled.")
        return

    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_SCHEMA_SQL)
        await db.commit()
    logger.info("Memory database initialized at %s", db_path)