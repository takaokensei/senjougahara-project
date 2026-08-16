"""
brain/memory/db.py

SQLite connection and schema management for the memory module.
Uses Python built-in sqlite3 with async thread wrappers.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path

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
    role              TEXT NOT NULL,
    content           TEXT NOT NULL,
    timestamp         TEXT NOT NULL DEFAULT (datetime('now')),
    summary_batch_id  INTEGER
);

CREATE INDEX IF NOT EXISTS idx_facts_key ON facts(key);
CREATE INDEX IF NOT EXISTS idx_prefs_key ON preferences(key);
CREATE INDEX IF NOT EXISTS idx_log_timestamp ON conversation_log(timestamp);
"""


def _init_sync(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_SCHEMA_SQL)
        conn.commit()


async def initialize_db(db_path: Path) -> None:
    """Initialize the SQLite database and create tables if they don't exist."""
    await asyncio.to_thread(_init_sync, db_path)
    logger.info("Memory database initialized at %s", db_path)