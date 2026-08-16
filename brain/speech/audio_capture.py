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
    Supports VAD-based silence detection and fixed-duration fallback.
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

    def record_until_silence(
        self,
        frame_duration_ms: int = 30,
        silence_timeout_ms: int = 900,
        max_duration_s: float = 15.0,
        min_duration_s: float = 0.3,
        vad_aggressiveness: int = 2,
    ) -> bytes:
        """
        Record audio from the microphone until sustained silence is detected after speech,
        or until max_duration_s is reached.
        """
        try:
            import sounddevice as sd
            import numpy as np
            import webrtcvad
        except ImportError as exc:
            logger.warning("sounddevice / numpy / webrtcvad not available (%s), falling back to fixed duration", exc)
            return self.record_seconds(min(max_duration_s, 4.5))

        try:
            vad = webrtcvad.Vad(vad_aggressiveness)
            samples_per_frame = int(self.sample_rate * frame_duration_ms / 1000)
            silence_frames_needed = silence_timeout_ms // frame_duration_ms
            max_frames = int(max_duration_s * 1000 / frame_duration_ms)
            min_frames = int(min_duration_s * 1000 / frame_duration_ms)

            frames: list[np.ndarray] = []
            silence_run = 0
            started_speaking = False

            logger.info("Recording with VAD (max: %.1fs, silence_timeout: %dms)...", max_duration_s, silence_timeout_ms)

            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=CHANNELS,
                dtype="int16",
                blocksize=samples_per_frame,
            ) as stream:
                for i in range(max_frames):
                    frame_data, overflowed = stream.read(samples_per_frame)
                    frames.append(frame_data.copy())

                    raw_bytes = frame_data.tobytes()
                    is_speech = vad.is_speech(raw_bytes, self.sample_rate)

                    if is_speech:
                        started_speaking = True
                        silence_run = 0
                    elif started_speaking and i >= min_frames:
                        silence_run += 1
                        if silence_run >= silence_frames_needed:
                            logger.info("VAD detected end of speech (silence for %dms)", silence_timeout_ms)
                            break

            if not frames:
                return b""

            audio_data = np.concatenate(frames)
            logger.info("VAD Recording complete (%d samples, %.2fs)", len(audio_data), len(audio_data) / self.sample_rate)

            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(audio_data.tobytes())

            return wav_buffer.getvalue()

        except Exception as exc:
            logger.error("VAD Audio recording error: %s", exc)
            return b""

    async def record_async(
        self,
        duration: float | None = None,
        silence_timeout_ms: int = 900,
        max_duration_s: float = 15.0,
        min_duration_s: float = 0.3,
        vad_aggressiveness: int = 2,
    ) -> bytes:
        """Async wrapper for microphone recording (VAD or fixed duration)."""
        if duration is not None and duration > 0:
            return await asyncio.to_thread(self.record_seconds, duration)
        return await asyncio.to_thread(
            self.record_until_silence,
            30,
            silence_timeout_ms,
            max_duration_s,
            min_duration_s,
            vad_aggressiveness,
        )