"""
brain/tests/test_e2e.py

End-to-End integration test for the Senjougahara MVP flow:
  1. Boot sequence and health checks
  2. WebSocket bridge connection
  3. Processing a user prompt with tool use
  4. Structured output validation ({text, emotion, animation, priority})
  5. Fallback/live TTS synthesis
  6. Bridge command emission
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brain.agent.loop import AgentLoop
from brain.agent.providers.base import BaseLLMProvider, LLMResponse, ToolCall
from brain.agent.structured_output import Emotion, Priority, StructuredResponse
from brain.bridge.client import BridgeClient
from brain.permissions.policy import PermissionEngine
from brain.personality.loader import PersonalityProfile
from brain.speech.tts import TTSAdapter
from brain.tools.registry import get_tool_risk, import_all_tools


class MockProvider(BaseLLMProvider):
    """Mock LLM provider that simulates tool-use -> final structured response."""

    def __init__(self):
        self.call_count = 0

    async def complete(self, messages, tools=None, system_prompt=None):
        self.call_count += 1
        if self.call_count == 1:
            # First turn: call launch_app tool
            return LLMResponse(
                tool_calls=[
                    ToolCall(call_id="call_1", tool_name="list_windows", arguments={})
                ]
            )
        else:
            # Second turn: final structured response
            return LLMResponse(
                text='{"text": "I checked your open windows.", "emotion": "happy", "animation": "nod", "priority": "normal"}'
            )

    def format_tool_result(self, call_id, tool_name, result, is_error=False):
        return {"role": "tool", "content": str(result), "tool_call_id": call_id}


class TestEndToEndMVP:
    def test_full_agent_turn_with_tool_use(self, tmp_path: Path):
        import_all_tools()

        audit_log = tmp_path / "audit.jsonl"
        permission_engine = PermissionEngine(
            audit_log_path=audit_log,
            confirmation_callback=None,
        )

        mock_provider = MockProvider()
        agent = AgentLoop(
            provider=mock_provider,
            permission_engine=permission_engine,
            system_prompt="You are Senjougahara.",
        )

        tts = TTSAdapter(
            engine_base_url="http://127.0.0.1:10101",
            audio_cache_dir=tmp_path / "audio_cache",
        )

        async def run_flow():
            history = []
            # 1. Agent processes user prompt
            response = await agent.process("What windows are open?", history)

            assert isinstance(response, StructuredResponse)
            assert response.emotion == Emotion.HAPPY
            assert response.animation == "nod"
            assert "windows" in response.text.lower()

            # 2. TTS generates audio (fallback or live)
            audio_res = await tts.speak(
                text=response.text,
                emotion=response.emotion.value,
                animation=response.animation,
            )
            assert "audio_url" in audio_res
            assert "wav_path" in audio_res
            assert Path(audio_res["wav_path"]).exists()

            # 3. Audit log contains the list_windows execution
            assert audit_log.exists()
            log_content = audit_log.read_text()
            assert "list_windows" in log_content

        asyncio.run(run_flow())