"""
brain/tests/test_window_awareness.py

Unit tests for window awareness and fullscreen content avoidance heuristic.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from brain.tools.window_awareness import (
    WindowInfo,
    get_foreground_window_info,
    is_likely_fullscreen_content,
)


class TestWindowAwareness:
    def test_fullscreen_detection_heuristic(self):
        """Window covering >= 85% of screen is treated as fullscreen content."""
        # 1. Fullscreen window (1920x1080 on 1920x1080 -> 100% coverage)
        fs_win = WindowInfo(
            title="YouTube - Google Chrome",
            process_name="chrome.exe",
            x=0,
            y=0,
            width=1920,
            height=1080,
            is_foreground=True,
            screen_coverage_pct=1.0,
        )
        assert is_likely_fullscreen_content(fs_win) is True

        # 2. Large window (88% coverage)
        large_win = WindowInfo(
            title="Video Player",
            process_name="vlc.exe",
            x=50,
            y=50,
            width=1800,
            height=1000,
            is_foreground=True,
            screen_coverage_pct=0.88,
        )
        assert is_likely_fullscreen_content(large_win) is True

        # 3. Small/Normal window (30% coverage)
        normal_win = WindowInfo(
            title="Notepad",
            process_name="notepad.exe",
            x=200,
            y=200,
            width=800,
            height=600,
            is_foreground=True,
            screen_coverage_pct=0.23,
        )
        assert is_likely_fullscreen_content(normal_win) is False

        # 4. Background window with high coverage
        bg_win = WindowInfo(
            title="Game",
            process_name="game.exe",
            x=0,
            y=0,
            width=1920,
            height=1080,
            is_foreground=False,
            screen_coverage_pct=1.0,
        )
        assert is_likely_fullscreen_content(bg_win) is False

        # 5. None window
        assert is_likely_fullscreen_content(None) is False

    @patch("brain.tools.window_awareness.sys.platform", "win32")
    def test_get_foreground_window_info_mock(self):
        """Verify Win32 window metrics extraction using mocked user32 ctypes."""
        mock_user32 = MagicMock()
        mock_user32.GetForegroundWindow.return_value = 12345
        mock_user32.GetWindowTextLengthW.return_value = 10

        # Simulate GetWindowRect setting rect values
        def mock_get_window_rect(hwnd, rect_ptr):
            rect = rect_ptr._obj
            rect.left = 0
            rect.top = 0
            rect.right = 1920
            rect.bottom = 1080
            return 1

        mock_user32.GetWindowRect.side_effect = mock_get_window_rect

        with patch("ctypes.windll.user32", mock_user32, create=True):
            info = get_foreground_window_info(screen_width=1920, screen_height=1080)
            assert info is not None
            assert info.width == 1920
            assert info.height == 1080
            assert info.screen_coverage_pct == 1.0
            assert info.is_foreground is True
