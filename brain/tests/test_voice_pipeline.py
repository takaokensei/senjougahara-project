"""
brain/tests/test_voice_pipeline.py

Integration tests for the Voice Pipeline:
  - Activation -> Listening -> Audio Capture -> STT -> Agent -> TTS -> Bridge Speak
  - Silence / Empty transcript feedback (CONFUSED -> IDLE)
  - Microphone failure feedback (CONFUSED -> IDLE)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brain.agent.loop import AgentLoop
from brain.agent.providers.base import BaseLLMProvider, LLMResponse
from brain.agent.structured_output import Emotion, Priority, StructuredResponse
from brain.bridge.client import BridgeClient
from brain.permissions.policy import PermissionEngine
from brain.speech.audio_capture import AudioRecorder
from brain.speech.stt import STTEngine
from brain.speech.tts import TTSAdapter
from brain.speech.voice_pipeline import VoicePipeline


class MockVoiceLLMProvider(BaseLLMProvider):
    async def complete(self, messages, tools=None, system_prompt=None):
        return LLMResponse(
            text='{"japanese_text": "こんにちは。", "portuguese_translation": "Olá.", "emotion": "happy", "animation": "greeting", "priority": "normal"}'
        )

    def format_tool_result(self, call_id, tool_name, result, is_error=False):
        return {"role": "tool", "content": str(result), "tool_call_id": call_id}


class TestVoicePipelineIntegration:
    def test_full_voice_pipeline_turn(self, tmp_path: Path):
        async def _run():
            # 1. Setup mocks and real pipeline components
            permission_engine = PermissionEngine(audit_log_path=tmp_path / "audit.jsonl")
            agent = AgentLoop(
                provider=MockVoiceLLMProvider(),
                permission_engine=permission_engine,
                system_prompt="You are Senjougahara.",
            )

            mock_bridge = MagicMock(spec=BridgeClient)
            mock_bridge.set_state = AsyncMock()
            mock_bridge.speak = AsyncMock()
            mock_bridge.send_error = AsyncMock()
            mock_bridge.on = MagicMock()

            mock_stt = MagicMock(spec=STTEngine)
            mock_stt.transcribe_bytes = MagicMock(return_value="Olá Senjougahara")

            mock_recorder = MagicMock(spec=AudioRecorder)
            mock_recorder.record_async = AsyncMock(return_value=b"DUMMY_WAV_BYTES_16KHZ")

            mock_tts = MagicMock(spec=TTSAdapter)
            mock_tts.speak = AsyncMock(return_value={
                "audio_url": "http://127.0.0.1:8766/audio/test.wav",
                "wav_path": str(tmp_path / "test.wav"),
            })

            pipeline = VoicePipeline(
                agent=agent,
                bridge=mock_bridge,
                stt=mock_stt,
                tts=mock_tts,
                recorder=mock_recorder,
            )

            # 2. Trigger activation
            await pipeline.handle_activation(source="hotkey")

            # 3. Assertions on the full pipeline flow
            mock_bridge.set_state.assert_any_call("LISTENING", reason="Activated by hotkey")
            mock_recorder.record_async.assert_awaited_once()
            mock_stt.transcribe_bytes.assert_called_once_with(b"DUMMY_WAV_BYTES_16KHZ")
            mock_bridge.set_state.assert_any_call("THINKING", reason="Processing user utterance")
            mock_tts.speak.assert_awaited_once()
            mock_bridge.speak.assert_awaited_once_with(
                text="こんにちは。 (Olá.)",
                emotion="happy",
                animation="greeting",
                audio_url="http://127.0.0.1:8766/audio/test.wav",
                priority="normal",
            )
            assert len(pipeline.conversation_history) == 2
            assert pipeline.conversation_history[0]["content"] == "Olá Senjougahara"
            assert pipeline.conversation_history[1]["content"] == "こんにちは。 (Olá.)"

        asyncio.run(_run())

    def test_silence_fallback_ux_feedback(self, tmp_path: Path):
        async def _run():
            permission_engine = PermissionEngine(audit_log_path=tmp_path / "audit.jsonl")
            agent = AgentLoop(
                provider=MockVoiceLLMProvider(),
                permission_engine=permission_engine,
                system_prompt="You are Senjougahara.",
            )

            mock_bridge = MagicMock(spec=BridgeClient)
            mock_bridge.set_state = AsyncMock()
            mock_bridge.speak = AsyncMock()

            mock_stt = MagicMock(spec=STTEngine)
            mock_stt.transcribe_bytes = MagicMock(return_value="")  # Silence / Empty transcript

            mock_recorder = MagicMock(spec=AudioRecorder)
            mock_recorder.record_async = AsyncMock(return_value=b"DUMMY_SILENT_WAV")

            mock_tts = MagicMock(spec=TTSAdapter)
            mock_tts.speak = AsyncMock()

            pipeline = VoicePipeline(
                agent=agent,
                bridge=mock_bridge,
                stt=mock_stt,
                tts=mock_tts,
                recorder=mock_recorder,
            )

            await pipeline.handle_activation(source="hotkey")

            # Must give visual feedback (CONFUSED) before returning to IDLE
            mock_bridge.set_state.assert_any_call("CONFUSED", reason="Silence detected")
            mock_bridge.set_state.assert_any_call("IDLE")
            mock_tts.speak.assert_not_called()
            mock_bridge.speak.assert_not_called()

        asyncio.run(_run())

    def test_microphone_failure_ux_feedback(self, tmp_path: Path):
        async def _run():
            permission_engine = PermissionEngine(audit_log_path=tmp_path / "audit.jsonl")
            agent = AgentLoop(
                provider=MockVoiceLLMProvider(),
                permission_engine=permission_engine,
                system_prompt="You are Senjougahara.",
            )

            mock_bridge = MagicMock(spec=BridgeClient)
            mock_bridge.set_state = AsyncMock()

            mock_recorder = MagicMock(spec=AudioRecorder)
            mock_recorder.record_async = AsyncMock(return_value=b"")  # Mic error / 0 bytes

            mock_stt = MagicMock(spec=STTEngine)
            mock_tts = MagicMock(spec=TTSAdapter)

            pipeline = VoicePipeline(
                agent=agent,
                bridge=mock_bridge,
                stt=mock_stt,
                tts=mock_tts,
                recorder=mock_recorder,
            )

            await pipeline.handle_activation(source="hotkey")

            # Must give visual feedback (CONFUSED)
            mock_bridge.set_state.assert_any_call("CONFUSED", reason="Microphone error / no audio")
            mock_bridge.set_state.assert_any_call("IDLE")

        asyncio.run(_run())