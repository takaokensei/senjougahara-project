"""
brain/tests/test_desktop_control.py

Unit tests for desktop control and browser executable path resolution.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from brain.tools.desktop_control import _resolve_app_path, launch_app


class TestDesktopControlResolution:
    def test_resolve_app_path_from_path_env(self):
        """If application is found in PATH via shutil.which, return it directly."""
        with patch("shutil.which", return_value=r"C:\Windows\System32\notepad.exe"):
            path = _resolve_app_path("notepad")
            assert path == r"C:\Windows\System32\notepad.exe"

    def test_resolve_app_path_direct_file(self):
        """If application name is already an existing file path, return it directly."""
        with patch("shutil.which", return_value=None), \
             patch("os.path.isfile", return_value=True):
            path = _resolve_app_path(r"C:\Custom\app.exe")
            assert path == r"C:\Custom\app.exe"

    def test_resolve_app_path_browser_candidate_match(self):
        """If application is a known browser, check common ProgramFiles / LocalAppData candidates."""
        def mock_isfile(candidate: str) -> bool:
            return "Google\\Chrome\\Application\\chrome.exe" in candidate

        with patch("shutil.which", return_value=None), \
             patch("os.path.isfile", side_effect=mock_isfile):
            path = _resolve_app_path("chrome")
            assert "chrome.exe" in path

    def test_resolve_app_path_unknown_app_raises_error(self):
        """If application is not found, raise a clear RuntimeError with inspected paths."""
        with patch("shutil.which", return_value=None), \
             patch("os.path.isfile", return_value=False):
            with pytest.raises(RuntimeError) as exc_info:
                _resolve_app_path("non_existent_app_12345")
            assert "Não foi possível localizar o executável" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_launch_app_success(self):
        """launch_app resolves path and starts process."""
        mock_app = MagicMock()
        mock_app.process = 9999

        with patch("brain.tools.desktop_control._resolve_app_path", return_value=r"C:\Program Files\Google\Chrome\Application\chrome.exe"), \
             patch("pywinauto.Application") as mock_pywinauto:
            mock_pywinauto.return_value.start.return_value = mock_app
            result = await launch_app("chrome", ["https://youtube.com"])
            assert "PID: 9999" in result
            mock_pywinauto.return_value.start.assert_called_once()
