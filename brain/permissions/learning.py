"""
brain/permissions/learning.py

Authority pattern learner and auto-approve suggestion engine.

Inspired by the authority learning pattern in vierisid/jarvis
(studied as architectural reference only, not code-copied; RSALv2 license).
Reimplemented independently in Python.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def infer_action_category(tool_name: str) -> str:
    """Map tool names to action categories."""
    if tool_name in {"launch_app", "focus_window", "list_windows", "type_text", "get_clipboard", "set_clipboard", "press_hotkey", "get_system_info"}:
        return "desktop"
    if tool_name in {"read_file", "write_file", "list_directory", "search_files", "delete_file", "delete_directory", "move_file"}:
        return "filesystem"
    if tool_name in {"run_command"}:
        return "terminal"
    if tool_name in {"open_url", "search_web", "click_element", "get_page_text"}:
        return "browser"
    if tool_name in {"capture_screen"}:
        return "screenshot"
    return "general"


class AuthorityLearner:
    """
    Tracks consecutive user approvals/denials for (action_category, tool_name) pairs.
    When a pair reaches N consecutive approvals without denials, a promotion suggestion
    is generated for auto-approval.
    """

    def __init__(self, db_path: Path, threshold: int = 5) -> None:
        self.db_path = db_path
        self.threshold = threshold
        db_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def record_decision_sync(self, action_category: str, tool_name: str, approved: bool) -> None:
        """Synchronously record an approval or denial decision."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if approved:
                cursor.execute(
                    """
                    INSERT INTO approval_patterns (action_category, tool_name, consecutive_approvals, last_approval_at, suggestion_sent)
                    VALUES (?, ?, 1, datetime('now'), 0)
                    ON CONFLICT(action_category, tool_name) DO UPDATE SET
                        consecutive_approvals = consecutive_approvals + 1,
                        last_approval_at = datetime('now')
                    """,
                    (action_category, tool_name),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO approval_patterns (action_category, tool_name, consecutive_approvals, last_approval_at, suggestion_sent)
                    VALUES (?, ?, 0, datetime('now'), 0)
                    ON CONFLICT(action_category, tool_name) DO UPDATE SET
                        consecutive_approvals = 0,
                        suggestion_sent = 0,
                        last_approval_at = datetime('now')
                    """,
                    (action_category, tool_name),
                )
            conn.commit()

    async def record_decision(self, action_category: str, tool_name: str, approved: bool) -> None:
        """Async wrapper to record an approval/denial decision."""
        await asyncio.to_thread(self.record_decision_sync, action_category, tool_name, approved)

    def get_pending_suggestions_sync(self) -> list[dict[str, Any]]:
        """Return patterns that have reached the threshold and have not yet been suggested."""
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, action_category, tool_name, consecutive_approvals, last_approval_at
                FROM approval_patterns
                WHERE consecutive_approvals >= ? AND suggestion_sent = 0
                ORDER BY consecutive_approvals DESC
                """,
                (self.threshold,),
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_pending_suggestions(self) -> list[dict[str, Any]]:
        """Async wrapper to query pending suggestions."""
        return await asyncio.to_thread(self.get_pending_suggestions_sync)

    def mark_suggestion_sent_sync(self, pattern_id: int | str) -> None:
        """Mark a suggestion as sent/handled."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE approval_patterns SET suggestion_sent = 1 WHERE id = ?",
                (int(pattern_id),),
            )
            conn.commit()

    async def mark_suggestion_sent(self, pattern_id: int | str) -> None:
        """Async wrapper to mark suggestion as sent."""
        await asyncio.to_thread(self.mark_suggestion_sent_sync, pattern_id)

    def get_pattern_sync(self, pattern_id: int | str) -> dict[str, Any] | None:
        """Retrieve a specific pattern by ID."""
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM approval_patterns WHERE id = ?", (int(pattern_id),))
            row = cursor.fetchone()
            return dict(row) if row else None

    async def get_pattern(self, pattern_id: int | str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self.get_pattern_sync, pattern_id)
