"""
brain/tools/desktop_control.py

Windows desktop automation tools using pywinauto (Win32 + UIA backends).

Risk tiers:
  LOW:    Reading window state, taking focus, launching apps from the start menu
  MEDIUM: Sending keystrokes, clicking UI elements, resizing/moving windows
  HIGH:   Killing processes, sending keystrokes that could modify system settings
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from typing import Any

from brain.tools.registry import RISK_LOW, RISK_MEDIUM, tool

logger = logging.getLogger(__name__)


@tool(
    name="launch_app",
    description="Launch an application by its executable name or full path. Returns the process ID on success.",
    risk=RISK_LOW,
    parameters={
        "type": "object",
        "properties": {
            "app_name": {
                "type": "string",
                "description": "Application name (e.g., 'notepad', 'code', 'chrome') or full path to executable.",
            },
            "args": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional command-line arguments.",
                "default": [],
            },
        },
        "required": ["app_name"],
    },
)
async def launch_app(app_name: str, args: list[str] | None = None) -> str:
    """
    Launch an application. Uses pywinauto's Application.start() which is
    more reliable than subprocess for GUI apps (handles UAC prompts differently).
    """
    try:
        # Use pywinauto for GUI app launching when available
        import pywinauto

        cmd = app_name
        if args:
            cmd = f'{app_name} {" ".join(args)}'

        app = pywinauto.Application().start(cmd, wait_for_idle=False)
        pid = app.process
        logger.info("Launched app: %s (pid=%s)", app_name, pid)
        return f"Launched '{app_name}' successfully (PID: {pid})."

    except ImportError:
        # Fallback to subprocess if pywinauto is not available
        cmd_list = [app_name] + (args or [])
        proc = await asyncio.create_subprocess_exec(*cmd_list)
        return f"Launched '{app_name}' (PID: {proc.pid})."
    except Exception as exc:
        logger.error("Failed to launch %s: %s", app_name, exc)
        raise RuntimeError(f"Could not launch '{app_name}': {exc}") from exc


@tool(
    name="focus_window",
    description="Bring a window to the foreground and give it keyboard focus. Matches by window title (partial match).",
    risk=RISK_LOW,
    parameters={
        "type": "object",
        "properties": {
            "title_pattern": {
                "type": "string",
                "description": "Partial window title to match (case-insensitive).",
            },
        },
        "required": ["title_pattern"],
    },
)
async def focus_window(title_pattern: str) -> str:
    """Bring a matching window to the foreground."""
    try:
        import pygetwindow as gw  # type: ignore[import]

        windows = gw.getWindowsWithTitle(title_pattern)
        if not windows:
            return f"No window found matching '{title_pattern}'."

        win = windows[0]
        win.activate()
        logger.info("Focused window: %s", win.title)
        return f"Focused window: '{win.title}'."
    except Exception as exc:
        logger.error("Failed to focus window '%s': %s", title_pattern, exc)
        raise RuntimeError(f"Could not focus window '{title_pattern}': {exc}") from exc


@tool(
    name="list_windows",
    description="List all currently open windows with their titles.",
    risk=RISK_LOW,
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
async def list_windows() -> list[str]:
    """Return a list of all open window titles."""
    try:
        import pygetwindow as gw  # type: ignore[import]

        titles = [w.title for w in gw.getAllWindows() if w.title.strip()]
        logger.info("Listed %d windows", len(titles))
        return titles
    except Exception as exc:
        logger.error("Failed to list windows: %s", exc)
        raise RuntimeError(f"Could not list windows: {exc}") from exc


@tool(
    name="type_text",
    description="Type text into the currently focused window, as if the user typed it on the keyboard.",
    risk=RISK_MEDIUM,
    parameters={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Text to type.",
            },
        },
        "required": ["text"],
    },
)
async def type_text(text: str) -> str:
    """Type text into the focused window using pywinauto keyboard simulation."""
    try:
        import pywinauto.keyboard as kb  # type: ignore[import]

        # Small delay to ensure focus is established
        await asyncio.sleep(0.1)
        kb.send_keys(text, with_spaces=True, with_tabs=True, with_newlines=True)
        logger.info("Typed %d characters", len(text))
        return f"Typed {len(text)} characters successfully."
    except Exception as exc:
        logger.error("Failed to type text: %s", exc)
        raise RuntimeError(f"Could not type text: {exc}") from exc