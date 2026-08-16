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
            cursor.execute(
                "SELECT value FROM facts WHERE key = ? AND (expires_at IS NULL OR expires_at > datetime('now'))",
                (key,),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    async def get_fact(self, key: str) -> str | None:
        return await asyncio.to_thread(self._get_fact_sync, key)

    def _set_fact_sync(
        self,
        key: str,
        value: str,
        confidence: float,
        category: str,
        expires_at: str | None,
    ) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO facts (key, value, confidence, category, expires_at, updated_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    confidence = excluded.confidence,
                    category = excluded.category,
                    expires_at = excluded.expires_at,
                    updated_at = datetime('now')
                """,
                (key, value, confidence, category, expires_at),
            )
            conn.commit()

    async def set_fact(
        self,
        key: str,
        value: str,
        confidence: float = 1.0,
        category: str = "general",
        expires_at: str | None = None,
    ) -> None:
        await asyncio.to_thread(self._set_fact_sync, key, value, confidence, category, expires_at)
        logger.info("Saved fact [%s]: %s = %s (expires: %s)", category, key, value, expires_at)

    def _list_all_facts_sync(self) -> dict[str, str]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT key, value FROM facts
                WHERE expires_at IS NULL OR expires_at > datetime('now')
                ORDER BY updated_at DESC
                """
            )
            rows = cursor.fetchall()
            return {r[0]: r[1] for r in rows}

    async def list_all_facts(self) -> dict[str, str]:
        return await asyncio.to_thread(self._list_all_facts_sync)

    def _list_active_fact_records_sync(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT key, value, confidence, category, expires_at FROM facts
                WHERE expires_at IS NULL OR expires_at > datetime('now')
                ORDER BY updated_at DESC
                """
            )
            rows = cursor.fetchall()
            return [
                {
                    "key": r[0],
                    "value": r[1],
                    "confidence": r[2],
                    "category": r[3],
                    "expires_at": r[4],
                }
                for r in rows
            ]

    async def list_active_fact_records(self) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._list_active_fact_records_sync)

    def _purge_expired_sync(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM facts WHERE expires_at IS NOT NULL AND expires_at <= datetime('now')")
            deleted = cursor.rowcount
            conn.commit()
            return max(0, deleted)

    async def purge_expired(self) -> int:
        deleted = await asyncio.to_thread(self._purge_expired_sync)
        if deleted > 0:
            logger.info("Purged %d expired facts from memory.", deleted)
        return deleted

    async def format_for_prompt(self, max_facts: int = 20) -> str:
        records = await self.list_active_fact_records()
        if not records:
            return ""
        items = [f"- [{r['category']}] {r['key']}: {r['value']}" for r in records[:max_facts]]
        return "Known facts about the user / environment:\n" + "\n".join(items)