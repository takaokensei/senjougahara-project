"""
brain/tests/test_audio_capture.py

Unit tests for VAD-based microphone recording and silence detection.
"""

from __future__ import annotations

import math
import struct
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from brain.speech.audio_capture import AudioRecorder, CHANNELS, SAMPLE_RATE


def generate_speech_frame(duration_ms: int = 30, sample_rate: int = 16000, freq: float = 300.0) -> np.ndarray:
    """Generate synthetic 16-bit PCM speech frame (sine wave)."""
    n_samples = int(sample_rate * duration_ms / 1000)
    samples = []
    for i in range(n_samples):
        val = int(12000 * math.sin(2 * math.pi * freq * i / sample_rate))
        samples.append(val)
    return np.array(samples, dtype=np.int16)


def generate_silence_frame(duration_ms: int = 30, sample_rate: int = 16000) -> np.ndarray:
    """Generate synthetic 16-bit PCM silence frame (all zeros)."""
    n_samples = int(sample_rate * duration_ms / 1000)
    return np.zeros(n_samples, dtype=np.int16)


class MockInputStream:
    def __init__(self, frame_queue: list[np.ndarray]):
        self.frame_queue = list(frame_queue)
        self.read_count = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def read(self, size):
        self.read_count += 1
        if self.frame_queue:
            return self.frame_queue.pop(0), False
        return np.zeros(size, dtype=np.int16), False


class TestAudioCaptureVAD:
    def test_record_until_silence_stops_on_silence(self):
        recorder = AudioRecorder(sample_rate=16000)

        # 10 speech frames (300ms) + 30 silence frames (900ms) + 100 extra silence frames
        frames = [generate_speech_frame() for _ in range(10)] + [generate_silence_frame() for _ in range(50)]

        mock_stream = MockInputStream(frames)

        with patch("sounddevice.InputStream", return_value=mock_stream):
            wav_bytes = recorder.record_until_silence(
                frame_duration_ms=30,
                silence_timeout_ms=900,
                max_duration_s=10.0,
                min_duration_s=0.3,
            )

        # Should have stopped right after 10 speech frames + 30 silence frames (~40 reads)
        assert len(wav_bytes) > 0
        assert mock_stream.read_count <= 45

    def test_record_until_silence_respects_max_duration(self):
        recorder = AudioRecorder(sample_rate=16000)

        # 100 continuous speech frames without silence
        frames = [generate_speech_frame() for _ in range(100)]
        mock_stream = MockInputStream(frames)

        with patch("sounddevice.InputStream", return_value=mock_stream):
            wav_bytes = recorder.record_until_silence(
                frame_duration_ms=30,
                silence_timeout_ms=900,
                max_duration_s=1.0,  # Max ~33 frames
                min_duration_s=0.3,
            )

        assert len(wav_bytes) > 0
        # 1.0s max @ 30ms per frame = 33 frames
        assert mock_stream.read_count == 33

    def test_min_duration_prevents_premature_cut(self):
        recorder = AudioRecorder(sample_rate=16000)

        # 2 speech frames + 10 silence frames (300ms total) + 20 speech frames
        frames = (
            [generate_speech_frame() for _ in range(2)]
            + [generate_silence_frame() for _ in range(10)]
            + [generate_speech_frame() for _ in range(20)]
        )
        mock_stream = MockInputStream(frames)

        with patch("sounddevice.InputStream", return_value=mock_stream):
            wav_bytes = recorder.record_until_silence(
                frame_duration_ms=30,
                silence_timeout_ms=300,
                max_duration_s=5.0,
                min_duration_s=1.0,  # Must record at least 1.0s before checking silence timeout
            )

        assert len(wav_bytes) > 0
        assert mock_stream.read_count >= 30
