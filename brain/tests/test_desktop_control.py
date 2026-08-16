"""
brain/tests/test_desktop_control.py

Unit tests for desktop control and browser executable path resolution.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

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

    @pytest.mark.asyncio
    async def test_launch_app_quotes_path_with_spaces(self):
        """Executable paths containing spaces must be wrapped in quotes so Windows
        CreateProcess correctly identifies where the path ends and arguments begin.
        For example, 'C:\\Program Files\\...' must become
        '"C:\\Program Files\\..." https://...' not 'C:\\Program Files\\... https://...'
        """
        mock_app = MagicMock()
        mock_app.process = 1234

        spaced_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        captured_cmd: list[str] = []

        def capture_start(cmd: str, **_kwargs):
            captured_cmd.append(cmd)
            return mock_app

        with patch("brain.tools.desktop_control._resolve_app_path", return_value=spaced_path), \
             patch("pywinauto.Application") as mock_pywinauto:
            mock_pywinauto.return_value.start.side_effect = capture_start
            result = await launch_app("chrome", ["https://youtube.com"])

        assert "PID: 1234" in result
        assert captured_cmd, "pywinauto.Application().start() should have been called"
        cmd = captured_cmd[0]
        # The quoted path must appear at the start: "C:\Program Files\..."
        assert cmd.startswith(f'"{spaced_path}"'), (
            f"Expected command to start with quoted path, got: {cmd!r}"
        )
        # Arguments must be appended after the quoted path
        assert "https://youtube.com" in cmd

    @pytest.mark.asyncio
    async def test_launch_app_no_quotes_for_path_without_spaces(self):
        """Paths without spaces must NOT get extra quoting (they work fine unquoted
        and extra quotes can confuse some Windows launchers)."""
        mock_app = MagicMock()
        mock_app.process = 5678

        no_space_path = r"C:\Windows\System32\notepad.exe"
        captured_cmd: list[str] = []

        def capture_start(cmd: str, **_kwargs):
            captured_cmd.append(cmd)
            return mock_app

        with patch("brain.tools.desktop_control._resolve_app_path", return_value=no_space_path), \
             patch("pywinauto.Application") as mock_pywinauto:
            mock_pywinauto.return_value.start.side_effect = capture_start
            result = await launch_app("notepad")

        assert "PID: 5678" in result
        cmd = captured_cmd[0]
        assert cmd == no_space_path, (
            f"Path without spaces should be unquoted, got: {cmd!r}"
        )


class TestWriteNoteAndTypeText:
    @pytest.mark.asyncio
    async def test_type_text_with_delay_splits_words(self):
        from brain.tools.desktop_control import type_text

        sent_chunks: list[str] = []

        with patch("pywinauto.keyboard.send_keys", side_effect=lambda chunk, **kw: sent_chunks.append(chunk)):
            result = await type_text("Olá Senjougahara teste", delay_ms=1)

        assert "Typed 22 characters" in result
        assert len(sent_chunks) == 3
        assert "".join(sent_chunks) == "Olá Senjougahara teste"

    @pytest.mark.asyncio
    async def test_write_note_orchestration(self):
        from brain.tools.desktop_control import write_note

        mock_proc = MagicMock()
        mock_proc.pid = 1234

        mock_win = MagicMock()
        mock_win.handle = 5678

        mock_app = MagicMock()
        mock_app.top_window.return_value = mock_win

        with patch("subprocess.Popen", return_value=mock_proc) as mock_popen, \
             patch("pywinauto.Application") as mock_app_cls, \
             patch("ctypes.windll.user32.SetForegroundWindow") as mock_set_fg, \
             patch("ctypes.windll.user32.BringWindowToTop") as mock_bring_top, \
             patch("brain.tools.desktop_control.type_text", new_callable=AsyncMock) as mock_type:

            mock_app_instance = MagicMock()
            mock_app_instance.connect.return_value = mock_app
            mock_app_cls.return_value = mock_app_instance
            mock_type.return_value = "Typed 30 characters successfully."

            result = await write_note("Lembrar de estudar DSP amanha", typing_delay_ms=80)

            assert result == "Nota escrita no Notepad."
            mock_popen.assert_called_once_with(["notepad.exe"])
            mock_type.assert_called_once_with("Lembrar de estudar DSP amanha", delay_ms=80)



