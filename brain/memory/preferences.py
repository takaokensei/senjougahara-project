"""
brain/memory/preferences.py

User preferences storage and retrieval via SQLite (standard library).
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PreferenceMemory:
    """Manages explicit user preferences stored in SQLite."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def _get_pref_sync(self, key: str) -> str | None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM preferences WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else None

    async def get_preference(self, key: str) -> str | None:
        return await asyncio.to_thread(self._get_pref_sync, key)

    def _set_pref_sync(self, key: str, value: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO preferences (key, value, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = datetime('now')
                """,
                (key, value),
            )
            conn.commit()

    async def set_preference(self, key: str, value: str) -> None:
        await asyncio.to_thread(self._set_pref_sync, key, value)
        logger.info("Saved preference: %s = %s", key, value)

    def _list_all_sync(self) -> dict[str, str]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM preferences ORDER BY updated_at DESC")
            rows = cursor.fetchall()
            return {r[0]: r[1] for r in rows}

    async def list_all_preferences(self) -> dict[str, str]:
        return await asyncio.to_thread(self._list_all_sync)

    async def format_for_prompt(self) -> str:
        prefs = await self.list_all_preferences()
        if not prefs:
            return ""
        items = [f"- {k}: {v}" for k, v in prefs.items()]
        return "User preferences:\n" + "\n".join(items)