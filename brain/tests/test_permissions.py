"""
brain/tests/test_permissions.py

Unit tests for the permission engine.
This module tests safety-critical behavior, especially:
  - NEVER_AUTO_APPROVE_TOOLS cannot be silently bypassed
  - Confirmation timeout fails safe (cancels, not approves)
  - Risk tier overrides work correctly for non-fixed tools
"""

import asyncio
import json
from pathlib import Path

import pytest

from brain.permissions.policy import (
    NEVER_AUTO_APPROVE_TOOLS,
    PermissionEngine,
    load_policy_overrides,
)
from brain.tools.registry import RISK_HIGH, RISK_LOW, RISK_MEDIUM


@pytest.fixture
def audit_log(tmp_path: Path) -> Path:
    return tmp_path / "audit.jsonl"


@pytest.fixture
def engine_no_confirm(audit_log: Path) -> PermissionEngine:
    return PermissionEngine(
        audit_log_path=audit_log,
        confirmation_callback=None,
    )


@pytest.fixture
def engine_auto_approve(audit_log: Path) -> PermissionEngine:
    async def always_approve(request_id, tool_name, description) -> bool:
        return True

    return PermissionEngine(
        audit_log_path=audit_log,
        confirmation_callback=always_approve,
    )


@pytest.fixture
def engine_auto_deny(audit_log: Path) -> PermissionEngine:
    async def always_deny(request_id, tool_name, description) -> bool:
        return False

    return PermissionEngine(
        audit_log_path=audit_log,
        confirmation_callback=always_deny,
    )


class TestRiskTiers:
    def test_low_risk_auto_approved(self, engine_no_confirm, audit_log):
        result = asyncio.run(engine_no_confirm.check_and_gate("read_file", RISK_LOW, {}))
        assert result is True
        log = audit_log.read_text()
        entry = json.loads(log.strip())
        assert entry["outcome"] == "auto_approved"

    def test_medium_risk_notify_proceed_by_default(self, engine_no_confirm, audit_log):
        result = asyncio.run(engine_no_confirm.check_and_gate("write_file", RISK_MEDIUM, {}))
        assert result is True
        log = audit_log.read_text()
        entry = json.loads(log.strip())
        assert entry["outcome"] == "notify_proceed"

    def test_high_risk_denied_without_callback(self, engine_no_confirm, audit_log):
        result = asyncio.run(engine_no_confirm.check_and_gate("run_command", RISK_HIGH, {}))
        assert result is False
        log = audit_log.read_text()
        entry = json.loads(log.strip())
        assert entry["outcome"] == "denied_no_callback"

    def test_high_risk_approved_with_callback(self, engine_auto_approve, audit_log):
        result = asyncio.run(engine_auto_approve.check_and_gate("run_command", RISK_HIGH, {}))
        assert result is True
        log = audit_log.read_text()
        entry = json.loads(log.strip())
        assert entry["outcome"] == "confirmed"

    def test_high_risk_denied_with_deny_callback(self, engine_auto_deny, audit_log):
        result = asyncio.run(engine_auto_deny.check_and_gate("run_command", RISK_HIGH, {}))
        assert result is False


class TestNeverAutoApprove:
    def test_never_auto_approve_set_is_non_empty(self):
        assert len(NEVER_AUTO_APPROVE_TOOLS) > 0

    def test_delete_file_in_never_approve(self):
        assert "delete_file" in NEVER_AUTO_APPROVE_TOOLS

    def test_send_email_in_never_approve(self):
        assert "send_email" in NEVER_AUTO_APPROVE_TOOLS

    def test_never_auto_approve_tool_stays_high_even_with_override(self, audit_log):
        engine = PermissionEngine(
            audit_log_path=audit_log,
            policy_overrides={"delete_file": RISK_LOW},
            confirmation_callback=None,
        )
        effective = engine.effective_risk("delete_file", RISK_LOW)
        assert effective == RISK_HIGH

    def test_never_auto_approve_is_denied_without_callback(self, engine_no_confirm, audit_log):
        result = asyncio.run(engine_no_confirm.check_and_gate("delete_file", RISK_LOW, {}))
        assert result is False


class TestPolicyOverrides:
    def test_low_override_auto_approves(self, audit_log):
        engine = PermissionEngine(
            audit_log_path=audit_log,
            policy_overrides={"type_text": RISK_LOW},
        )
        result = asyncio.run(engine.check_and_gate("type_text", RISK_MEDIUM, {}))
        assert result is True

    def test_high_override_requires_confirm(self, audit_log):
        engine = PermissionEngine(
            audit_log_path=audit_log,
            policy_overrides={"read_file": RISK_HIGH},
            confirmation_callback=None,
        )
        result = asyncio.run(engine.check_and_gate("read_file", RISK_LOW, {}))
        assert result is False


class TestConfirmationTimeout:
    def test_timeout_fails_safe(self, audit_log):
        async def slow_callback(request_id, tool_name, description) -> bool:
            await asyncio.sleep(10)
            return True

        engine = PermissionEngine(
            audit_log_path=audit_log,
            confirmation_callback=slow_callback,
            confirmation_timeout_seconds=0.05,
        )
        result = asyncio.run(engine.check_and_gate("run_command", RISK_HIGH, {}))
        assert result is False
        log = audit_log.read_text()
        entry = json.loads(log.strip())
        assert entry["outcome"] == "denied_timeout"


class TestAuditLog:
    def test_all_executions_logged(self, engine_no_confirm, audit_log):
        asyncio.run(engine_no_confirm.check_and_gate("read_file", RISK_LOW, {"path": "/tmp/test"}))
        asyncio.run(engine_no_confirm.check_and_gate("run_command", RISK_HIGH, {"command": "ls"}))

        lines = audit_log.read_text().strip().split("\n")
        assert len(lines) == 2

        entries = [json.loads(l) for l in lines]
        tool_names = {e["tool"] for e in entries}
        assert tool_names == {"read_file", "run_command"}

    def test_audit_includes_args(self, engine_no_confirm, audit_log):
        asyncio.run(engine_no_confirm.check_and_gate("read_file", RISK_LOW, {"path": "/home/user/doc.txt"}))
        entry = json.loads(audit_log.read_text().strip())
        assert entry["args"]["path"] == "/home/user/doc.txt"


class TestLoadPolicyOverrides:
    def test_load_empty_yaml(self, tmp_path: Path):
        yaml_file = tmp_path / "policy.yaml"
        yaml_file.write_text("overrides: {}\n")
        overrides = load_policy_overrides(yaml_file)
        assert overrides == {}

    def test_load_valid_overrides(self, tmp_path: Path):
        yaml_file = tmp_path / "policy.yaml"
        yaml_file.write_text("overrides:\n  type_text: LOW\n  write_file: HIGH\n")
        overrides = load_policy_overrides(yaml_file)
        assert overrides["type_text"] == "LOW"
        assert overrides["write_file"] == "HIGH"

    def test_invalid_tier_ignored(self, tmp_path: Path):
        yaml_file = tmp_path / "policy.yaml"
        yaml_file.write_text("overrides:\n  read_file: SUPERLOW\n")
        overrides = load_policy_overrides(yaml_file)
        assert "read_file" not in overrides

    def test_missing_file_returns_empty(self, tmp_path: Path):
        overrides = load_policy_overrides(tmp_path / "nonexistent.yaml")
        assert overrides == {}