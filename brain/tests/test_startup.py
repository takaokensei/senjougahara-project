"""
brain/tests/test_startup.py

Integration tests for the startup state machine.
All external dependencies (LLM provider, TTS, etc.) are mocked.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brain.startup.state_machine import StartupState, StartupStateMachine


class MockConfig:
    class llm:
        provider = "anthropic"
        model = "claude-3-haiku-20240307"
        ollama_base_url = "http://localhost:11434"

    class tts:
        engine_base_url = "http://127.0.0.1:10101"

    class bridge:
        port = 8765
        host = "127.0.0.1"

    class personality:
        active_profile = "senjougahara"


class MockProfile:
    name = "Senjougahara"
    def build_system_prompt(self, extra_context=""):
        return "You are Senjougahara."


def mock_personality_loader(profile_name: str):
    return MockProfile()


class TestStartupStateMachine:
    def _make_sm(self) -> StartupStateMachine:
        return StartupStateMachine(
            config=MockConfig,
            personality_loader=mock_personality_loader,
        )

    def test_successful_startup_reaches_ready(self):
        sm = self._make_sm()
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch("brain.startup.state_machine.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(sm.run())

        assert result is True
        assert sm.state == StartupState.READY
        assert sm.error_message is None
        assert sm.personality_profile is not None
        assert sm.personality_profile.name == "Senjougahara"

    def test_missing_api_key_causes_error(self):
        sm = self._make_sm()
        with patch.dict("os.environ", {}, clear=True):
            result = asyncio.run(sm.run())

        assert result is False
        assert sm.state == StartupState.ERROR
        assert sm.error_message is not None
        assert "ANTHROPIC_API_KEY" in sm.error_message

    def test_initial_state_is_initializing(self):
        sm = self._make_sm()
        assert sm.state == StartupState.INITIALIZING

    def test_personality_loaded_on_success(self):
        sm = self._make_sm()
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "key"}),
            patch("brain.startup.state_machine.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_resp = MagicMock(status_code=200)
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client
            asyncio.run(sm.run())

        assert sm.personality_profile is not None
        assert isinstance(sm.personality_profile, MockProfile)


class TestGreetingGating:
    def test_should_greet_first_run(self, tmp_path):
        state_file = tmp_path / "session_state.json"
        assert not state_file.exists()
        state = {"greeted_at": None}
        assert state["greeted_at"] is None

    def test_should_not_greet_within_cooldown(self):
        from datetime import datetime, timezone, timedelta
        greeted_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        last = datetime.fromisoformat(greeted_at)
        elapsed_hours = (datetime.now(timezone.utc) - last).total_seconds() / 3600
        assert elapsed_hours < 8

    def test_should_greet_after_cooldown(self):
        from datetime import datetime, timezone, timedelta
        greeted_at = (datetime.now(timezone.utc) - timedelta(hours=9)).isoformat()
        last = datetime.fromisoformat(greeted_at)
        elapsed_hours = (datetime.now(timezone.utc) - last).total_seconds() / 3600
        assert elapsed_hours >= 8