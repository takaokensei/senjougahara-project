"""
brain/tests/test_wake_phrase.py

Unit tests for wake phrase detection, duration estimation, and echo suppression.
"""

from __future__ import annotations

import time
import wave
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from brain.agent.loop import AgentLoop
from brain.agent.providers.base import BaseLLMProvider, LLMResponse
from brain.bridge.client import BridgeClient
from brain.permissions.policy import PermissionEngine
from brain.speech.audio_capture import AudioRecorder
from brain.speech.stt import STTEngine
from brain.speech.tts import TTSAdapter
from brain.speech.voice_pipeline import VoicePipeline
from brain.speech.wake_phrase import (
    contains_wake_phrase,
    estimate_audio_duration_seconds,
    normalize_phrase_pattern,
)
from brain.speech.wakeword import WakeWordDetector


class TestWakePhraseDetection:
    def test_contains_wake_phrase_exact_and_variants(self):
        phrase = "hey_jarvis"
        assert contains_wake_phrase("hey jarvis", phrase)
        assert contains_wake_phrase("Hey Jarvis, what time is it?", phrase)
        assert contains_wake_phrase("hey_jarvis open notepad", phrase)
        assert contains_wake_phrase("HEY, JARVIS!", phrase)
        assert contains_wake_phrase("Olá hey jarvis tudo bem", phrase)

    def test_contains_wake_phrase_negative_matches(self):
        phrase = "hey_jarvis"
        assert not contains_wake_phrase("hey there", phrase)
        assert not contains_wake_phrase("jarvis is cool", phrase)
        assert not contains_wake_phrase("they jarvis", phrase)
        assert not contains_wake_phrase("", phrase)
        assert not contains_wake_phrase("hello world", "")

    def test_estimate_audio_duration_from_wav(self, tmp_path: Path):
        wav_file = tmp_path / "sample.wav"
        framerate = 16000
        duration_s = 2.5
        n_frames = int(framerate * duration_s)

        with wave.open(str(wav_file), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(framerate)
            wf.writeframes(b"\x00\x00" * n_frames)

        measured = estimate_audio_duration_seconds(wav_path=wav_file)
        assert abs(measured - 2.5) < 0.05

    def test_estimate_audio_duration_heuristics(self):
        dur_short = estimate_audio_duration_seconds(text="Sim.")
        dur_long = estimate_audio_duration_seconds(text="Este é um texto consideravelmente mais longo com várias palavras para medir.")
        assert dur_short >= 1.0
        assert dur_long > dur_short


class MockVoiceLLMProvider(BaseLLMProvider):
    async def complete(self, messages, tools=None, system_prompt=None):
        return LLMResponse(
            text='{"japanese_text": "はい、ヘイジャーヴィスと言いました。", "portuguese_translation": "Sim, você disse hey jarvis.", "emotion": "neutral", "animation": "idle", "priority": "normal"}'
        )

    def format_tool_result(self, call_id, tool_name, result, is_error=False):
        return {"role": "tool", "content": str(result), "tool_call_id": call_id}


class TestVoicePipelineEchoSuppression:
    @pytest.mark.asyncio
    async def test_echo_suppression_sets_timestamp(self, tmp_path: Path):
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

        mock_stt = MagicMock(spec=STTEngine)
        mock_stt.transcribe_bytes = MagicMock(return_value="hey jarvis")

        mock_recorder = MagicMock(spec=AudioRecorder)
        mock_recorder.record_async = AsyncMock(return_value=b"DUMMY_WAV_BYTES_16KHZ")

        mock_tts = MagicMock(spec=TTSAdapter)
        mock_tts.speak = AsyncMock(return_value={
            "audio_url": "http://127.0.0.1:8766/audio/test.wav",
            "wav_path": str(tmp_path / "nonexistent.wav"),
        })

        mock_wakeword = MagicMock(spec=WakeWordDetector)
        mock_wakeword.phrase = "hey_jarvis"

        pipeline = VoicePipeline(
            agent=agent,
            bridge=mock_bridge,
            stt=mock_stt,
            tts=mock_tts,
            recorder=mock_recorder,
            wakeword=mock_wakeword,
        )

        assert pipeline._suppress_wakeword_until == 0.0

        await pipeline.handle_activation(source="wake_word")

        # Echo suppression window must be scheduled into the future
        assert pipeline._suppress_wakeword_until > time.monotonic()
