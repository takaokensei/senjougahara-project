"""
brain/tests/test_proactivity.py

Unit tests for ProactivityObserver and heuristic filters.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brain.agent.loop import AgentLoop
from brain.agent.proactivity import (
    ProactivityObserver,
    is_cooldown_active,
    is_process_blocked,
    is_repeated_comment,
    is_window_stable,
    should_comment,
)
from brain.agent.providers.base import BaseLLMProvider, LLMResponse
from brain.agent.structured_output import Emotion, Priority, StructuredResponse
from brain.bridge.client import BridgeClient
from brain.config import ProactivityConfig
from brain.tools.window_awareness import WindowInfo


class MockSimpleLLMProvider(BaseLLMProvider):
    def __init__(self, reply_text: str):
        self.reply_text = reply_text

    async def complete(self, messages, tools=None, system_prompt=None):
        return LLMResponse(text=self.reply_text)

    def format_tool_result(self, call_id, tool_name, result, is_error=False):
        return {"role": "tool", "content": str(result), "tool_call_id": call_id}

    def format_assistant_turn(self, response):
        return None


class TestProactivityHeuristicFilters:
    def test_is_window_stable(self):
        # Different window
        assert not is_window_stable("code.exe::main.py", "chrome.exe::YouTube", stable_since=100.0, now=130.0, min_stable_sec=20.0)
        # Same window, not enough time
        assert not is_window_stable("code.exe::main.py", "code.exe::main.py", stable_since=100.0, now=110.0, min_stable_sec=20.0)
        # Same window, elapsed >= min_stable
        assert is_window_stable("code.exe::main.py", "code.exe::main.py", stable_since=100.0, now=125.0, min_stable_sec=20.0)

    def test_is_cooldown_active(self):
        # First run (no last comment)
        assert not is_cooldown_active(last_comment_ts=0.0, now=1000.0, min_cooldown_sec=720.0)
        # In cooldown
        assert is_cooldown_active(last_comment_ts=1000.0, now=1200.0, min_cooldown_sec=720.0)
        # Cooldown expired
        assert not is_cooldown_active(last_comment_ts=1000.0, now=1800.0, min_cooldown_sec=720.0)

    def test_is_process_blocked(self):
        blocked = ["Teams.exe", "zoom.exe", "discord.exe"]
        # In blocklist
        assert is_process_blocked("teams.exe", "Meeting with Team", blocked, is_fullscreen=False)
        assert is_process_blocked("Zoom.exe", "Zoom Call", blocked, is_fullscreen=False)
        # Fullscreen
        assert is_process_blocked("vlc.exe", "Movie", blocked, is_fullscreen=True)
        # Shell component
        assert is_process_blocked("explorer.exe", "Progman", blocked, is_fullscreen=False)
        # Permitted window
        assert not is_process_blocked("Code.exe", "brain/main.py", blocked, is_fullscreen=False)

    def test_is_repeated_comment(self):
        history = {"code.exe::main.py": 1000.0}
        # In repeat window
        assert is_repeated_comment("code.exe::main.py", history, now=2000.0, repeat_window_sec=3600.0)
        # After repeat window
        assert not is_repeated_comment("code.exe::main.py", history, now=5000.0, repeat_window_sec=3600.0)
        # New window
        assert not is_repeated_comment("notepad.exe::notes.txt", history, now=2000.0, repeat_window_sec=3600.0)


class TestShouldCommentTriage:
    @pytest.mark.asyncio
    async def test_should_comment_returns_none_on_no(self):
        win = WindowInfo(
            title="main.py - Senjougahara",
            process_name="Code.exe",
            x=0, y=0, width=1920, height=1080,
            is_foreground=True, screen_coverage_pct=0.7,
        )
        provider = MockSimpleLLMProvider("NO")
        res = await should_comment(win, "User is an engineering student.", provider)
        assert res is None

        provider_with_punct = MockSimpleLLMProvider("No.")
        res2 = await should_comment(win, "User is an engineering student.", provider_with_punct)
        assert res2 is None

    @pytest.mark.asyncio
    async def test_should_comment_returns_text_when_worthy(self):
        win = WindowInfo(
            title="DSP Lab Report.docx",
            process_name="WINWORD.EXE",
            x=0, y=0, width=1920, height=1080,
            is_foreground=True, screen_coverage_pct=0.7,
        )
        provider = MockSimpleLLMProvider("Você está trabalhando no relatório de processamento de sinais há bastante tempo.")
        res = await should_comment(win, "User has DSP exam coming up.", provider)
        assert res is not None
        assert "processamento de sinais" in res

    @pytest.mark.asyncio
    async def test_should_comment_handles_provider_error_gracefully(self):
        win = WindowInfo(
            title="Test", process_name="Test.exe",
            x=0, y=0, width=800, height=600,
            is_foreground=True, screen_coverage_pct=0.5,
        )
        broken_provider = MagicMock(spec=BaseLLMProvider)
        broken_provider.complete = AsyncMock(side_effect=RuntimeError("Provider connection error"))
        res = await should_comment(win, "", broken_provider)
        assert res is None


class TestProactivityObserverEndToEnd:
    @pytest.mark.asyncio
    async def test_full_proactivity_tick_emits_comment(self):
        current_time = 1000.0

        def fake_time():
            return current_time

        config = ProactivityConfig(
            enabled=True,
            poll_interval_seconds=1.0,
            min_cooldown_minutes=10.0,
            min_window_stable_seconds=20.0,
            repeat_window_minutes=60.0,
            blocked_processes=["Teams.exe"],
        )

        mock_bridge = MagicMock(spec=BridgeClient)
        mock_bridge.speak = AsyncMock()

        mock_agent = MagicMock(spec=AgentLoop)
        mock_agent.process = AsyncMock(return_value=StructuredResponse(
            text="Trabalhando duro no código, não é? Não se esqueça de respirar.",
            emotion=Emotion.RELAXED,
            animation="pose",
            priority=Priority.NORMAL,
        ))

        triage_provider = MockSimpleLLMProvider("Ele está programando no VS Code.")

        observer = ProactivityObserver(
            config=config,
            agent=mock_agent,
            bridge=mock_bridge,
            provider=triage_provider,
            fact_memory=None,
            time_provider=fake_time,
        )

        fake_win = WindowInfo(
            title="main.py - Senjougahara",
            process_name="Code.exe",
            x=0, y=0, width=1920, height=1080,
            is_foreground=True, screen_coverage_pct=0.6,
        )

        with patch("brain.agent.proactivity.get_foreground_window_info", return_value=fake_win):
            # Tick 1: Window observed first time -> stabilizes
            await observer.tick()
            mock_bridge.speak.assert_not_called()

            # Advance time by 25s (exceeds min_window_stable_seconds=20s)
            current_time += 25.0

            # Tick 2: Window is stable, passes cooldown and filters -> emits
            await observer.tick()
            mock_bridge.speak.assert_called_once()
            call_kwargs = mock_bridge.speak.call_args.kwargs
            assert "Trabalhando duro" in call_kwargs["text"]
            assert call_kwargs["emotion"] == "relaxed"
            assert call_kwargs["animation"] == "pose"

            # Tick 3: Immediate next tick -> blocked by cooldown!
            current_time += 5.0
            mock_bridge.speak.reset_mock()
            await observer.tick()
            mock_bridge.speak.assert_not_called()


class TestCommentHistoryPurge:
    """_comment_history stale entries must be removed each tick, but recent ones kept."""

    @pytest.mark.asyncio
    async def test_stale_entries_removed_fresh_entries_kept(self):
        config = ProactivityConfig(
            enabled=True,
            poll_interval_seconds=1.0,
            min_cooldown_minutes=10.0,
            min_window_stable_seconds=20.0,
            repeat_window_minutes=60.0,  # 3600 seconds
            blocked_processes=[],
        )
        now = 10_000.0
        mock_bridge = MagicMock(spec=BridgeClient)
        mock_bridge.speak = AsyncMock()
        mock_agent = MagicMock(spec=AgentLoop)
        mock_agent.process = AsyncMock(return_value=None)

        observer = ProactivityObserver(
            config=config,
            agent=mock_agent,
            bridge=mock_bridge,
            provider=MockSimpleLLMProvider("NO"),
            fact_memory=None,
            time_provider=lambda: now,
        )

        repeat_window_sec = config.repeat_window_minutes * 60.0  # 3600s

        # Populate history: 2 stale entries (> 3600s ago) and 1 recent entry (< 3600s ago)
        observer._comment_history = {
            "old_proc::old_title_1": now - repeat_window_sec - 1.0,   # stale
            "old_proc::old_title_2": now - repeat_window_sec - 100.0, # stale
            "new_proc::recent_title": now - repeat_window_sec + 60.0, # still fresh (3540s ago)
        }

        fake_win = WindowInfo(
            title="SomethingNew", process_name="new.exe",
            x=0, y=0, width=1920, height=1080,
            is_foreground=True, screen_coverage_pct=0.5,
        )
        with patch("brain.agent.proactivity.get_foreground_window_info", return_value=fake_win):
            await observer.tick()

        # Stale keys must be gone
        assert "old_proc::old_title_1" not in observer._comment_history
        assert "old_proc::old_title_2" not in observer._comment_history
        # Recent key must survive
        assert "new_proc::recent_title" in observer._comment_history

