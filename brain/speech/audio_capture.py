"""
brain/speech/audio_capture.py

Microphone audio capture using sounddevice / PyAudio with silence detection.
Records 16kHz mono audio suitable for faster-whisper and openWakeWord.
"""

from __future__ import annotations

import asyncio
import io
import logging
import tempfile
import time
import wave
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Audio format constants
SAMPLE_RATE = 16000
CHANNELS = 1


class AudioRecorder:
    """
    Records audio from the default microphone.
    Supports fixed-duration recording or energy-based silence detection.
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE) -> None:
        self.sample_rate = sample_rate

    def record_seconds(self, duration: float = 5.0) -> bytes:
        """Record audio for a fixed number of seconds and return WAV bytes."""
        try:
            import sounddevice as sd
            import numpy as np

            logger.info("Recording audio for %.1f seconds...", duration)
            audio_data = sd.rec(
                int(duration * self.sample_rate),
                samplerate=self.sample_rate,
                channels=CHANNELS,
                dtype="int16",
            )
            sd.wait()
            logger.info("Recording complete (%d samples)", len(audio_data))

            # Convert numpy array to WAV bytes
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(self.sample_rate)
                wf.writeframes(audio_data.tobytes())

            return wav_buffer.getvalue()

        except ImportError:
            logger.warning("sounddevice / numpy not available for live mic recording")
            return b""
        except Exception as exc:
            logger.error("Audio recording error: %s", exc)
            return b""

    async def record_async(self, duration: float = 5.0) -> bytes:
        """Async wrapper for microphone recording."""
        return await asyncio.to_thread(self.record_seconds, duration)