"""
brain/tools/window_awareness.py

Detection of foreground windows on Windows to allow the avatar
to avoid occluding areas of interest (e.g. fullscreen video or games).
"""

from __future__ import annotations

import ctypes
import logging
import sys
from dataclasses import asdict, dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WindowInfo:
    title: str
    process_name: str
    x: int
    y: int
    width: int
    height: int
    is_foreground: bool
    screen_coverage_pct: float  # 0.0 to 1.0


def is_likely_fullscreen_content(window: WindowInfo | None, threshold: float = 0.85) -> bool:
    """
    Heuristic: A foreground window covering more than `threshold` of the screen
    is treated as high-focus fullscreen content (video, gaming, presentation).
    """
    if window is None:
        return False
    return window.is_foreground and window.screen_coverage_pct >= threshold


def get_foreground_window_info(screen_width: int = 1920, screen_height: int = 1080) -> WindowInfo | None:
    """
    Get metrics of the current foreground window in Windows via Win32 user32.dll.
    """
    if sys.platform != "win32":
        return None

    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None

        # 1. Window Title
        length = user32.GetWindowTextLengthW(hwnd)
        title_buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buff, length + 1)
        title = title_buff.value or ""

        # 2. Window Rect (left, top, right, bottom)
        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        rect = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))

        x = int(rect.left)
        y = int(rect.top)
        width = max(0, int(rect.right - rect.left))
        height = max(0, int(rect.bottom - rect.top))

        # 3. Process Name
        process_name = "unknown"
        try:
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value:
                try:
                    import psutil
                    proc = psutil.Process(pid.value)
                    process_name = proc.name()
                except Exception:
                    pass
        except Exception:
            pass

        # 4. Coverage calculation
        total_screen_area = max(1, screen_width * screen_height)
        window_area = width * height
        coverage_pct = min(1.0, window_area / total_screen_area)

        return WindowInfo(
            title=title,
            process_name=process_name,
            x=x,
            y=y,
            width=width,
            height=height,
            is_foreground=True,
            screen_coverage_pct=round(coverage_pct, 4),
        )

    except Exception as exc:
        logger.debug("Failed to get foreground window info: %s", exc)
        return None
