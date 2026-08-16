"""
brain/permissions/policy.py

Risk-tiered permission engine.

Implements a three-tier model (inspired by the authority-engine pattern in
vierisid/jarvis — studied as architectural reference only, not code-copied;
RSALv2 license):

  LOW    → Execute automatically, log to audit trail.
  MEDIUM → Notify user and proceed (default); or require confirmation (configurable).
  HIGH   → ALWAYS require explicit confirmation. Cannot be silently auto-approved.

Security invariants:
  1. The risk tier is set at tool registration time, NOT by the LLM.
  2. Items in NEVER_AUTO_APPROVE_TOOLS cannot be downgraded to silent via policy overrides.
  3. Confirmation timeout always cancels (fails safe) rather than auto-approves.
  4. Every tool execution (any tier) is appended to the audit log.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Coroutine

import yaml

from brain.tools.registry import RISK_HIGH, RISK_LOW, RISK_MEDIUM

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hard-coded set of tools that can NEVER be silently auto-approved.
# policy.yaml overrides cannot move these below HIGH-tier confirmation.
# This is a defense-in-depth measure against compromised/malformed config files.
# ---------------------------------------------------------------------------
NEVER_AUTO_APPROVE_TOOLS: frozenset[str] = frozenset({
    # Destructive filesystem operations
    "delete_file",
    "delete_directory",
    "move_file",
    # System/security mutations
    "modify_registry",
    "change_firewall_rule",
    "install_software",
    "uninstall_software",
    # External communication on user's behalf
    "send_email",
    "send_message",
    "post_tweet",
    "submit_form_payment",
    # Dangerous terminal commands (regardless of classify_command_risk)
    # handled separately in the terminal tool
})


class PermissionEngine:
    """
    Evaluates tool call risk and gates execution accordingly.

    In Phase 1, confirmation is handled by a configurable async callback
    (in production, this callback talks to the avatar bridge; in tests, it
    can be a simple lambda that returns True).
    """

    def __init__(
        self,
        audit_log_path: Path,
        policy_overrides: dict[str, str] | None = None,
        confirmation_callback: Callable[[str, str, str], Coroutine[Any, Any, bool]] | None = None,
        confirmation_timeout_seconds: float = 30.0,
        medium_risk_requires_confirmation: bool = False,
    ) -> None:
        """
        Args:
            audit_log_path: Path to audit.jsonl file.
            policy_overrides: Dict of {tool_name: tier_override} from config.
            confirmation_callback: Async callable(request_id, tool_name, description) -> bool.
                Returns True if the user confirmed, False if denied/timed out.
                If None, HIGH-risk calls are auto-denied in Phase 1.
            confirmation_timeout_seconds: How long to wait for confirmation before cancelling.
            medium_risk_requires_confirmation: If True, MEDIUM tools also require confirmation.
        """
        self._audit_log_path = audit_log_path
        self._policy_overrides: dict[str, str] = policy_overrides or {}
        self._confirmation_callback = confirmation_callback
        self._confirmation_timeout = confirmation_timeout_seconds
        self._medium_requires_confirm = medium_risk_requires_confirmation
        audit_log_path.parent.mkdir(parents=True, exist_ok=True)

    def effective_risk(self, tool_name: str, base_risk: str) -> str:
        """
        Compute the effective risk tier for a tool, applying policy overrides.
        Items in NEVER_AUTO_APPROVE_TOOLS always remain HIGH.
        """
        if tool_name in NEVER_AUTO_APPROVE_TOOLS:
            return RISK_HIGH

        override = self._policy_overrides.get(tool_name)
        if override and override in (RISK_LOW, RISK_MEDIUM, RISK_HIGH):
            # Overrides can only be specified in the known tier set
            return override

        return base_risk

    async def check_and_gate(
        self,
        tool_name: str,
        base_risk: str,
        arguments: dict[str, Any],
        action_description: str | None = None,
    ) -> bool:
        """
        Gate a tool execution based on its risk tier.

        Returns True if the call should proceed, False if denied/timed-out.
        Always appends to the audit log.
        """
        risk = self.effective_risk(tool_name, base_risk)
        description = action_description or f"Execute tool '{tool_name}'"

        if risk == RISK_LOW:
            self._audit(tool_name, risk, arguments, "auto_approved")
            logger.debug("[PERM] LOW risk auto-approved: %s", tool_name)
            return True

        if risk == RISK_MEDIUM and not self._medium_requires_confirm:
            # MEDIUM default: notify-and-proceed (no blocking wait)
            self._audit(tool_name, risk, arguments, "notify_proceed")
            logger.info("[PERM] MEDIUM risk notify-proceed: %s", tool_name)
            return True

        # HIGH (or MEDIUM with confirmation required) — must get explicit user approval
        if self._confirmation_callback is None:
            # No callback registered (e.g., Phase 1 text-only mode)
            self._audit(tool_name, risk, arguments, "denied_no_callback")
            logger.warning(
                "[PERM] %s risk denied (no confirmation callback): %s", risk, tool_name
            )
            return False

        request_id = str(uuid.uuid4())
        try:
            confirmed = await asyncio.wait_for(
                self._confirmation_callback(request_id, tool_name, description),
                timeout=self._confirmation_timeout,
            )
        except asyncio.TimeoutError:
            # Fail safe: cancel, never auto-approve on timeout
            self._audit(tool_name, risk, arguments, "denied_timeout")
            logger.warning("[PERM] Confirmation timed out for %s — DENIED", tool_name)
            return False

        outcome = "confirmed" if confirmed else "denied_by_user"
        self._audit(tool_name, risk, arguments, outcome)
        return confirmed

    def _audit(self, tool_name: str, risk: str, arguments: dict[str, Any], outcome: str) -> None:
        """Append a line to the audit log."""
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": tool_name,
            "risk": risk,
            "args": arguments,
            "outcome": outcome,
        }
        try:
            with self._audit_log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as exc:
            # Audit log failure is logged but not fatal
            logger.error("Failed to write audit log: %s", exc)


def load_policy_overrides(policy_yaml_path: Path) -> dict[str, str]:
    """
    Load per-tool risk tier overrides from policy.yaml.
    Validates that override values are valid tier strings.
    """
    if not policy_yaml_path.exists():
        return {}

    with policy_yaml_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    overrides: dict[str, str] = {}
    raw_overrides = data.get("overrides", {})
    valid_tiers = {RISK_LOW, RISK_MEDIUM, RISK_HIGH}

    for tool_name, tier in raw_overrides.items():
        if tier not in valid_tiers:
            logger.warning("Invalid tier override for '%s': %s (ignored)", tool_name, tier)
            continue
        overrides[tool_name] = tier

    return overrides