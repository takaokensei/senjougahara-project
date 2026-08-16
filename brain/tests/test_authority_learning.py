"""
brain/tests/test_authority_learning.py

Unit and integration tests for AuthorityLearner and auto-approve suggestions.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.memory.db import initialize_db
from brain.permissions.learning import AuthorityLearner, infer_action_category
from brain.permissions.policy import PermissionEngine


class TestAuthorityLearner:
    @pytest.mark.asyncio
    async def test_record_approval_and_denial(self, tmp_path: Path):
        db_path = tmp_path / "memory.db"
        await initialize_db(db_path)

        learner = AuthorityLearner(db_path=db_path, threshold=3)

        # 1. First approval
        await learner.record_decision("desktop", "focus_window", True)
        suggestions = await learner.get_pending_suggestions()
        assert len(suggestions) == 0

        # 2. Second approval
        await learner.record_decision("desktop", "focus_window", True)
        assert len(await learner.get_pending_suggestions()) == 0

        # 3. Third approval (reaches threshold 3)
        await learner.record_decision("desktop", "focus_window", True)
        suggestions = await learner.get_pending_suggestions()
        assert len(suggestions) == 1
        assert suggestions[0]["tool_name"] == "focus_window"
        assert suggestions[0]["consecutive_approvals"] == 3

        # 4. Mark suggestion sent
        pattern_id = suggestions[0]["id"]
        await learner.mark_suggestion_sent(pattern_id)
        assert len(await learner.get_pending_suggestions()) == 0

        # 5. Denial resets counter and suggestion_sent flag
        await learner.record_decision("desktop", "focus_window", False)
        pattern = await learner.get_pattern(pattern_id)
        assert pattern is not None
        assert pattern["consecutive_approvals"] == 0
        assert pattern["suggestion_sent"] == 0

    @pytest.mark.asyncio
    async def test_permission_engine_integration(self, tmp_path: Path):
        db_path = tmp_path / "memory.db"
        await initialize_db(db_path)

        learner = AuthorityLearner(db_path=db_path, threshold=2)
        callback = AsyncMock(return_value=True)

        engine = PermissionEngine(
            audit_log_path=tmp_path / "audit.jsonl",
            confirmation_callback=callback,
            authority_learner=learner,
            medium_risk_requires_confirmation=True,
        )

        # Confirm 2 times
        allowed1 = await engine.check_and_gate("type_text", "MEDIUM", {"text": "hello"})
        assert allowed1 is True
        allowed2 = await engine.check_and_gate("type_text", "MEDIUM", {"text": "world"})
        assert allowed2 is True

        suggestions = await learner.get_pending_suggestions()
        assert len(suggestions) == 1
        assert suggestions[0]["tool_name"] == "type_text"
        assert suggestions[0]["consecutive_approvals"] == 2

    def test_infer_action_category(self):
        assert infer_action_category("launch_app") == "desktop"
        assert infer_action_category("read_file") == "filesystem"
        assert infer_action_category("run_command") == "terminal"
        assert infer_action_category("open_url") == "browser"
        assert infer_action_category("capture_screen") == "screenshot"
        assert infer_action_category("unknown_xyz") == "general"
