"""
brain/speech/hotkey.py

Global low-level keyboard hook using the `keyboard` library on Windows.
Fires regardless of which application currently has focus.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

logger = logging.getLogger(__name__)


class GlobalHotkeyListener:
    """
    Listens for a global hotkey combination (default: Right Ctrl)
    and invokes an async callback when triggered.
    """

    def __init__(self, key: str = "right ctrl", callback: Callable[[], None] | None = None) -> None:
        self.key = key
        self.callback = callback
        self._hooked = False

    def start(self) -> None:
        if self._hooked:
            return

        try:
            import keyboard

            def _on_hotkey():
                logger.info("Global hotkey triggered: %s", self.key)
                if self.callback:
                    self.callback()

            keyboard.add_hotkey(self.key, _on_hotkey)
            self._hooked = True
            logger.info("Registered global hotkey hook for '%s'", self.key)
        except Exception as exc:
            logger.warning("Could not register global hotkey hook '%s': %s", self.key, exc)

    def stop(self) -> None:
        if not self._hooked:
            return

        try:
            import keyboard
            keyboard.remove_hotkey(self.key)
            self._hooked = False
            logger.info("Unregistered global hotkey hook for '%s'", self.key)
        except Exception as exc:
            logger.debug("Error removing hotkey hook: %s", exc)