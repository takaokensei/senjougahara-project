"""
brain/permissions/emergency.py

Emergency controller and kill switch for execution gating.

Inspired by the EmergencyController pattern in vierisid/jarvis
(studied as architectural reference only, not code-copied; RSALv2 license).
Reimplemented independently in Python.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class EmergencyState(str, Enum):
    NORMAL = "normal"
    PAUSED = "paused"
    KILLED = "killed"


class EmergencyController:
    """
    Coordinates global execution safety states across agent loops and background tools.

    States:
      - NORMAL: Normal operation. Tools execute per standard permission engine rules.
      - PAUSED: Tool calls are temporarily suspended. Easily resumed via resume().
      - KILLED: Hard stop. All execution is locked down. Requires explicit reset() to recover.
    """

    def __init__(self) -> None:
        self._state: EmergencyState = EmergencyState.NORMAL
        self._reason: str = ""
        self._updated_at: str = datetime.now(timezone.utc).isoformat()

    @property
    def state(self) -> EmergencyState:
        return self._state

    @property
    def is_normal(self) -> bool:
        return self._state == EmergencyState.NORMAL

    @property
    def is_paused(self) -> bool:
        return self._state == EmergencyState.PAUSED

    @property
    def is_killed(self) -> bool:
        return self._state == EmergencyState.KILLED

    def pause(self, reason: str = "User requested emergency pause") -> None:
        """Temporarily suspend tool execution."""
        if self._state == EmergencyState.KILLED:
            logger.warning("[EMERGENCY] Cannot pause while KILLED. Use reset() first.")
            return

        self._state = EmergencyState.PAUSED
        self._reason = reason
        self._updated_at = datetime.now(timezone.utc).isoformat()
        logger.warning("[EMERGENCY] Execution PAUSED: %s", reason)

    def resume(self) -> bool:
        """Resume normal operation from PAUSED state. Cannot resume from KILLED."""
        if self._state == EmergencyState.KILLED:
            logger.warning("[EMERGENCY] Cannot resume while in KILLED state. Explicit reset() required.")
            return False

        self._state = EmergencyState.NORMAL
        self._reason = ""
        self._updated_at = datetime.now(timezone.utc).isoformat()
        logger.info("[EMERGENCY] Execution RESUMED (Normal).")
        return True

    def kill(self, reason: str = "Emergency kill switch engaged") -> None:
        """Engage hard kill switch. Gated actions are blocked until reset()."""
        self._state = EmergencyState.KILLED
        self._reason = reason
        self._updated_at = datetime.now(timezone.utc).isoformat()
        logger.critical("[EMERGENCY] KILL SWITCH ENGAGED: %s", reason)

    def reset(self) -> None:
        """Reset emergency controller to NORMAL state."""
        self._state = EmergencyState.NORMAL
        self._reason = ""
        self._updated_at = datetime.now(timezone.utc).isoformat()
        logger.info("[EMERGENCY] Controller RESET to normal state.")

    def can_execute(self) -> tuple[bool, str]:
        """
        Check if tool execution is currently allowed.

        Returns:
            (True, "") if allowed.
            (False, reason_message) if suspended by pause or kill switch.
        """
        if self._state == EmergencyState.NORMAL:
            return True, ""
        if self._state == EmergencyState.PAUSED:
            return False, f"Tool execution is currently PAUSED ({self._reason})"
        if self._state == EmergencyState.KILLED:
            return False, f"Emergency KILL SWITCH is active ({self._reason}). Reset required."
        return False, "Unknown emergency state"

    @property
    def status(self) -> dict[str, Any]:
        return {
            "state": self._state.value,
            "reason": self._reason,
            "updated_at": self._updated_at,
        }
