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

    def format_assistant_turn(self, response: LLMResponse):
        return None



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


class TestEstimateDurationSafetyMultiplier:
    """The heuristic fallback must apply a 1.4x safety margin; WAV path must not."""

    def test_heuristic_applies_1_4x_multiplier(self):
        # Compute the raw value the old formula would give, then verify the new one is ~1.4x
        text = "了解したわ。YouTubeを開いたわよ。"
        import re
        cjk = len(re.findall(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]", text))
        other = re.sub(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]", "", text).strip()
        words = len(other.split()) if other else 0
        raw = (cjk / 5.0) + (words / 3.0)
        expected = max(1.0, min(60.0, raw * 1.4))
        got = estimate_audio_duration_seconds(text=text, wav_path=None)
        assert abs(got - expected) < 0.01, f"Expected {expected:.3f}, got {got:.3f}"

    def test_heuristic_minimum_clamped_to_1_second(self):
        # Very short text — even with 1.4x, the result must be >= 1.0
        assert estimate_audio_duration_seconds(text=".", wav_path=None) >= 1.0

    def test_wav_path_returns_exact_duration_no_multiplier(self, tmp_path):
        """WAV header path must NOT apply the 1.4x multiplier."""
        wav_file = tmp_path / "exact.wav"
        framerate = 16000
        duration_s = 3.0
        n_frames = int(framerate * duration_s)
        import wave as wave_mod
        with wave_mod.open(str(wav_file), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(framerate)
            wf.writeframes(b"\x00\x00" * n_frames)
        measured = estimate_audio_duration_seconds(text="ignored", wav_path=wav_file)
        assert abs(measured - duration_s) < 0.05


class TestVoicePipelineTTSFailureSuppression:
    """When TTS fails, the suppression window must be short and fixed (2s), not heuristic."""

    @pytest.mark.asyncio
    async def test_tts_failure_uses_short_fixed_suppression(self, tmp_path):
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
        mock_stt.transcribe_bytes = MagicMock(return_value="abre o youtube pra mim")

        mock_recorder = MagicMock(spec=AudioRecorder)
        mock_recorder.record_async = AsyncMock(return_value=b"DUMMY_WAV_BYTES_16KHZ")

        # TTS always fails
        mock_tts = MagicMock(spec=TTSAdapter)
        mock_tts.speak = AsyncMock(side_effect=RuntimeError("AivisSpeech not available"))

        pipeline = VoicePipeline(
            agent=agent,
            bridge=mock_bridge,
            stt=mock_stt,
            tts=mock_tts,
            recorder=mock_recorder,
        )

        before = time.monotonic()
        await pipeline.handle_activation(source="hotkey")
        after = time.monotonic()

        sup = pipeline._suppress_wakeword_until
        # Must be set (> 0 and in the future relative to call start)
        assert sup > before
        # The fixed 2s window: suppress_until should be around before+2s to before+6s
        # (6s is the pre-emptive guard set at pipeline start; 2s is reset on TTS failure).
        # After TTS fails, suppress_until is reset to monotonic()+2. We just check it's
        # a small window, not a large heuristic estimate (which would be ~4-8s for CJK text).
        assert sup < after + 4.0, (
            f"Suppression window too long for TTS-failure path: {sup - before:.2f}s from call start"
        )

