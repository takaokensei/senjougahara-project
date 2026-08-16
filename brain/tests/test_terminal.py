"""
brain/tests/test_terminal.py

Unit tests for terminal command risk classification.

Focused on the chain-operator injection bypass fix: a command that starts with
a safe prefix but contains shell chaining operators must be classified HIGH, not
MEDIUM, to prevent destructive second operations from being auto-approved.
"""

from __future__ import annotations

import pytest

from brain.tools.terminal import classify_command_risk
from brain.tools.registry import RISK_HIGH, RISK_MEDIUM


class TestClassifyCommandRisk:
    # ------------------------------------------------------------------
    # Chained commands must always be HIGH regardless of safe prefix
    # ------------------------------------------------------------------
    @pytest.mark.parametrize("cmd", [
        # Semicolon chains
        r"git status; Remove-Item -Recurse -Force C:\temp",
        r"git log; del /f /q C:\temp\*",
        # && chains
        r"dir && del /f /q C:\temp\*",
        r"echo hi && format C: /y",
        # Single & (cmd.exe background/chain)
        r"echo hi & format C: /y",
        # Pipe — can redirect output to destructive sinks
        r"git log | Out-File C:\evil.ps1",
        r"dir | Remove-Item",
        # PowerShell subexpression
        r"dir; $(Remove-Item -Recurse C:\temp)",
        r"echo test; $(format C: /y)",
        # Backtick (PowerShell line continuation / eval)
        "git status`Remove-Item C:\\foo",
        # Newline injection
        "git status\nRemove-Item C:\\bar",
        # Chains that don't start with a safe prefix
        "Remove-Item -Recurse C:\\foo; echo done",
    ])
    def test_chained_commands_are_high_risk(self, cmd: str) -> None:
        assert classify_command_risk(cmd) == RISK_HIGH, (
            f"Expected RISK_HIGH for chained command: {cmd!r}"
        )

    # ------------------------------------------------------------------
    # Safe single commands must still be MEDIUM
    # ------------------------------------------------------------------
    @pytest.mark.parametrize("cmd", [
        "git status",
        "git log",
        "git diff",
        "git branch",
        "dir",
        "echo hello",
        "echo hello world",
        "where python",
        "whoami",
        "pip list",
        "python --version",
    ])
    def test_safe_single_commands_are_medium_risk(self, cmd: str) -> None:
        assert classify_command_risk(cmd) == RISK_MEDIUM, (
            f"Expected RISK_MEDIUM for safe single command: {cmd!r}"
        )

    # ------------------------------------------------------------------
    # Destructive single commands (no chain operators) must be HIGH
    # ------------------------------------------------------------------
    @pytest.mark.parametrize("cmd", [
        "del /f /q C:\\temp",
        "Remove-Item -Recurse -Force C:\\Users\\foo",
        "format C: /y",
        "pip install evil-package",
        "git push --force",
        "rm -rf /tmp/foo",
    ])
    def test_destructive_single_commands_are_high_risk(self, cmd: str) -> None:
        assert classify_command_risk(cmd) == RISK_HIGH, (
            f"Expected RISK_HIGH for destructive command: {cmd!r}"
        )
