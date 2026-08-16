"""
brain/memory/facts.py

Long-term facts storage and retrieval via SQLite (standard library).
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class FactMemory:
    """Manages long-term facts stored in SQLite."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def _get_fact_sync(self, key: str) -> str | None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM facts WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else None

    async def get_fact(self, key: str) -> str | None:
        return await asyncio.to_thread(self._get_fact_sync, key)

    def _set_fact_sync(self, key: str, value: str, confidence: float) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO facts (key, value, confidence, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    confidence = excluded.confidence,
                    updated_at = datetime('now')
                """,
                (key, value, confidence),
            )
            conn.commit()

    async def set_fact(self, key: str, value: str, confidence: float = 1.0) -> None:
        await asyncio.to_thread(self._set_fact_sync, key, value, confidence)
        logger.info("Saved fact: %s = %s", key, value)

    def _list_all_facts_sync(self) -> dict[str, str]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM facts ORDER BY updated_at DESC")
            rows = cursor.fetchall()
            return {r[0]: r[1] for r in rows}

    async def list_all_facts(self) -> dict[str, str]:
        return await asyncio.to_thread(self._list_all_facts_sync)

    async def format_for_prompt(self, max_facts: int = 20) -> str:
        facts = await self.list_all_facts()
        if not facts:
            return ""
        items = [f"- {k}: {v}" for k, v in list(facts.items())[:max_facts]]
        return "Known facts about the user / environment:\n" + "\n".join(items)