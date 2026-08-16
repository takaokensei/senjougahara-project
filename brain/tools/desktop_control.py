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
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from brain.tools.registry import RISK_LOW, RISK_MEDIUM, tool

logger = logging.getLogger(__name__)

_BROWSER_CANDIDATES: dict[str, list[str]] = {
    "chrome": [
        r"{programfiles}\Google\Chrome\Application\chrome.exe",
        r"{programfilesx86}\Google\Chrome\Application\chrome.exe",
        r"{localappdata}\Google\Chrome\Application\chrome.exe",
    ],
    "brave": [
        r"{programfiles}\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"{localappdata}\BraveSoftware\Brave-Browser\Application\brave.exe",
    ],
    "edge": [
        r"{programfiles}\Microsoft\Edge\Application\msedge.exe",
        r"{programfilesx86}\Microsoft\Edge\Application\msedge.exe",
    ],
    "firefox": [
        r"{programfiles}\Mozilla Firefox\firefox.exe",
        r"{programfilesx86}\Mozilla Firefox\firefox.exe",
    ],
}


def _resolve_app_path(app_name: str) -> str:
    """
    Resolve a friendly application name to an absolute executable path.

    Order of resolution:
    1. If app_name is already a valid file or on PATH (via shutil.which), use it.
    2. If in known browser mappings, check common installation candidates.
    3. If not found, raise a clear RuntimeError with inspected paths.
    """
    which_result = shutil.which(app_name)
    if which_result:
        return which_result
    if os.path.isfile(app_name):
        return app_name

    key = app_name.strip().lower()
    candidates = _BROWSER_CANDIDATES.get(key, [])
    env_map = {
        "programfiles": os.environ.get("ProgramFiles", r"C:\Program Files"),
        "programfilesx86": os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        "localappdata": os.environ.get("LocalAppData", ""),
    }
    for template in candidates:
        candidate_path = template.format(**env_map)
        if os.path.isfile(candidate_path):
            return candidate_path

    tried = ", ".join(t.format(**env_map) for t in candidates) or "PATH"
    raise RuntimeError(
        f"Não foi possível localizar o executável de '{app_name}'. "
        f"Locais verificados: {tried}"
    )


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
        resolved_path = _resolve_app_path(app_name)

        import pywinauto

        cmd = f'"{resolved_path}"' if " " in resolved_path else resolved_path
        if args:
            cmd = f'{cmd} {" ".join(args)}'

        app = pywinauto.Application().start(cmd, wait_for_idle=False)
        pid = app.process
        logger.info("Launched app: %s -> %s (pid=%s)", app_name, resolved_path, pid)
        return f"Launched '{app_name}' successfully (PID: {pid})."

    except ImportError:
        resolved_path = _resolve_app_path(app_name)
        cmd_list = [resolved_path] + (args or [])
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
    description=(
        "Type text into the currently focused window, as if the user typed it on the keyboard. "
        "Optional delay_ms enables realistic typing rhythm by sending words with pauses."
    ),
    risk=RISK_MEDIUM,
    parameters={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Text to type.",
            },
            "delay_ms": {
                "type": "integer",
                "description": "Delay in milliseconds between words for realistic typing pacing. Default 0 (instant).",
                "default": 0,
            },
        },
        "required": ["text"],
    },
)
async def type_text(text: str, delay_ms: int = 0) -> str:
    """Type text into the focused window using pywinauto keyboard simulation."""
    try:
        import pywinauto.keyboard as kb  # type: ignore[import]

        # Small delay to ensure focus is established
        await asyncio.sleep(0.1)
        if delay_ms > 0:
            words = text.split(" ")
            for i, word in enumerate(words):
                chunk = word + (" " if i < len(words) - 1 else "")
                kb.send_keys(chunk, with_spaces=True, with_tabs=True, with_newlines=True)
                await asyncio.sleep(delay_ms / 1000.0)
        else:
            kb.send_keys(text, with_spaces=True, with_tabs=True, with_newlines=True)
        logger.info("Typed %d characters (delay_ms=%d)", len(text), delay_ms)
        return f"Typed {len(text)} characters successfully."
    except Exception as exc:
        logger.error("Failed to type text: %s", exc)
        raise RuntimeError(f"Could not type text: {exc}") from exc


@tool(
    name="write_note",
    description=(
        "Open Windows Notepad and type content with a visible, realistic typing effect. "
        "Use this when the user asks to write a note, take notes, or record thoughts."
    ),
    risk=RISK_MEDIUM,
    parameters={
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "The note content to type into Notepad.",
            },
            "typing_delay_ms": {
                "type": "integer",
                "description": "Delay in ms between words for typing rhythm. Default 80ms.",
                "default": 80,
            },
        },
        "required": ["content"],
    },
)
async def write_note(content: str, typing_delay_ms: int = 80) -> str:
    """Launch Notepad, bring it to the foreground, then type content with realistic pacing."""
    import subprocess
    import ctypes
    import time as _time

    try:
        # Launch Notepad via subprocess so we get its PID reliably
        proc = await asyncio.to_thread(
            subprocess.Popen, ["notepad.exe"]
        )
        pid = proc.pid
        logger.info("Launched Notepad (pid=%d)", pid)

        # Poll up to 3 seconds for the Notepad window to appear and become usable
        import pywinauto
        deadline = _time.monotonic() + 3.0
        app = None
        while _time.monotonic() < deadline:
            try:
                app = pywinauto.Application(backend="uia").connect(process=pid, timeout=0.5)
                break
            except Exception:
                await asyncio.sleep(0.2)

        if app is None:
            raise RuntimeError("Notepad window did not appear within 3 seconds.")

        # Bring the Notepad window to the foreground using Win32
        win = app.top_window()
        handle = win.handle
        await asyncio.to_thread(ctypes.windll.user32.SetForegroundWindow, handle)
        await asyncio.to_thread(ctypes.windll.user32.BringWindowToTop, handle)
        await asyncio.sleep(0.3)  # Let Windows process the focus change

        logger.info("Notepad is in the foreground — starting to type")
        await type_text(content, delay_ms=typing_delay_ms)
        return "Nota escrita no Notepad."
    except Exception as exc:
        logger.error("Failed to write note: %s", exc)
        raise RuntimeError(f"Could not write note: {exc}") from exc




@tool(
    name="get_clipboard",
    description="Get the current text content from the Windows clipboard.",
    risk=RISK_LOW,
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
async def get_clipboard() -> str:
    """Read text from the clipboard."""
    try:
        import pyperclip
        text = await asyncio.to_thread(pyperclip.paste)
        return text or "(clipboard is empty)"
    except Exception as exc:
        logger.error("Failed to read clipboard: %s", exc)
        raise RuntimeError(f"Could not read clipboard: {exc}") from exc


@tool(
    name="set_clipboard",
    description="Copy text to the Windows clipboard.",
    risk=RISK_LOW,
    parameters={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Text to copy to the clipboard.",
            },
        },
        "required": ["text"],
    },
)
async def set_clipboard(text: str) -> str:
    """Write text to the clipboard."""
    try:
        import pyperclip
        await asyncio.to_thread(pyperclip.copy, text)
        return f"Copied {len(text)} characters to clipboard."
    except Exception as exc:
        logger.error("Failed to write to clipboard: %s", exc)
        raise RuntimeError(f"Could not write to clipboard: {exc}") from exc


@tool(
    name="press_hotkey",
    description="Simulate pressing a keyboard shortcut (e.g. ['ctrl', 'c'], ['alt', 'f4'], ['volume_up'], ['volume_down'], ['volume_mute'], ['play_pause']).",
    risk=RISK_MEDIUM,
    parameters={
        "type": "object",
        "properties": {
            "keys": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of keys to press simultaneously (e.g. ['ctrl', 'v'] or ['alt', 'tab']).",
            },
        },
        "required": ["keys"],
    },
)
async def press_hotkey(keys: list[str]) -> str:
    """Send key combination or multimedia keypress."""
    try:
        import keyboard
        combo = "+".join(keys)
        await asyncio.to_thread(keyboard.send, combo)
        logger.info("Pressed hotkey combo: %s", combo)
        return f"Pressed hotkey combo: {combo}"
    except Exception as exc:
        logger.error("Failed to press hotkey %s: %s", keys, exc)
        raise RuntimeError(f"Could not press hotkey: {exc}") from exc


@tool(
    name="get_system_info",
    description="Get current Windows system status including active window title, platform version, and time.",
    risk=RISK_LOW,
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
async def get_system_info() -> dict[str, Any]:
    """Return system information."""
    import platform
    from datetime import datetime, timezone

    active_title = ""
    try:
        import pygetwindow as gw  # type: ignore[import]
        active_win = gw.getActiveWindow()
        if active_win:
            active_title = active_win.title
    except Exception:
        pass

    return {
        "os": f"{platform.system()} {platform.release()}",
        "machine": platform.machine(),
        "active_window": active_title or "(none)",
        "current_time_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }