"""
brain/tests/test_quick_override.py

Unit tests for apply_quick_override and category permission gating.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from brain.permissions.policy import PermissionEngine
from brain.permissions.quick_override import apply_quick_override


class TestQuickOverride:
    def test_apply_quick_override_idempotence(self):
        initial = {"read_file": "LOW"}

        first_pass = apply_quick_override(initial, "desktop", allow=True)
        second_pass = apply_quick_override(first_pass, "desktop", allow=True)

        assert first_pass == second_pass
        assert first_pass.get("type_text") == "LOW"
        assert first_pass.get("focus_window") == "LOW"

    def test_never_auto_approve_invariant_preserved(self):
        initial = {}
        # Try to allow filesystem
        overrides = apply_quick_override(initial, "delete_file", allow=True)
        # delete_file should not be downgraded to LOW
        assert overrides.get("delete_file") != "LOW"

    @pytest.mark.asyncio
    async def test_permission_engine_respects_category_override(self, tmp_path: Path):
        overrides = apply_quick_override({}, "desktop", allow=True)

        engine = PermissionEngine(
            audit_log_path=tmp_path / "audit.jsonl",
            policy_overrides=overrides,
        )

        # Base risk of type_text is MEDIUM, but override makes it LOW (auto-approved without confirmation)
        effective = engine.effective_risk("type_text", base_risk="MEDIUM")
        assert effective == "LOW"

        allowed = await engine.check_and_gate("type_text", "MEDIUM", {"text": "hello"})
        assert allowed is True

    @pytest.mark.asyncio
    async def test_permission_engine_respects_deny_category_override(self, tmp_path: Path):
        # Elevate desktop category to HIGH
        overrides = apply_quick_override({}, "desktop", allow=False)

        engine = PermissionEngine(
            audit_log_path=tmp_path / "audit.jsonl",
            policy_overrides=overrides,
            confirmation_callback=None,  # No callback means HIGH is auto-denied
        )

        effective = engine.effective_risk("focus_window", base_risk="LOW")
        assert effective == "HIGH"

        allowed = await engine.check_and_gate("focus_window", "LOW", {"title_pattern": "test"})
        assert allowed is False
