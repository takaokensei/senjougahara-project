"""
brain/memory/conversation_log.py

Rolling conversation history logger with SQLite persistence (standard library).
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ConversationLog:
    """Logs conversation turns to SQLite."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def _log_turn_sync(self, role: str, content: str, summary_batch_id: int | None) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO conversation_log (role, content, summary_batch_id)
                VALUES (?, ?, ?)
                """,
                (role, content, summary_batch_id),
            )
            conn.commit()

    async def log_turn(self, role: str, content: str, summary_batch_id: int | None = None) -> None:
        await asyncio.to_thread(self._log_turn_sync, role, content, summary_batch_id)

    def _get_recent_turns_sync(self, limit: int) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT role, content, timestamp
                FROM conversation_log
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in reversed(rows)]

    async def get_recent_turns(self, limit: int = 20) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._get_recent_turns_sync, limit)