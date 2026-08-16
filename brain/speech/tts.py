"""
brain/speech/tts.py

TTS (Text-to-Speech) adapter.

Single adapter class that talks to AivisSpeech or VOICEVOX via their shared
VOICEVOX-compatible HTTP API. The engine URL and speaker ID are driven by config
alone — no code changes are needed to switch between engines.

API used:
  POST /audio_query  ->  returns an AudioQuery JSON object
  POST /synthesis    ->  returns WAV audio bytes

The adapter also serves the resulting WAV file on a local HTTP endpoint so the
avatar can play it via URL (referenced in SpeakCommand.audio_url).

Phase 1: synthesize() returns a file path + serves it on http://127.0.0.1:8766/audio/
"""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Port for serving synthesized audio files
_AUDIO_SERVE_PORT = 8766


class TTSAdapter:
    """
    Engine-agnostic TTS adapter for VOICEVOX-compatible APIs.

    interface: speak(text, emotion, speed, pitch, animation)
    -> internally: audio_query -> synthesis -> WAV file
    -> returns: (audio_url, wav_path)
    """

    def __init__(
        self,
        engine_base_url: str = "http://127.0.0.1:10101",
        speaker_id: str = "888753760",
        speed: float = 1.0,
        pitch: float = 0.0,
        audio_cache_dir: Path | None = None,
    ) -> None:
        self._base_url = engine_base_url.rstrip("/")
        self._speaker_id = speaker_id
        self._speed = speed
        self._pitch = pitch
        self._cache_dir = audio_cache_dir or Path(tempfile.gettempdir()) / "senjougahara_audio"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def speak(
        self,
        text: str,
        emotion: str = "neutral",
        speed: float | None = None,
        pitch: float | None = None,
        animation: str = "idle",
    ) -> dict[str, str]:
        """
        Synthesize text to speech.

        Returns a dict with:
          audio_url: URL where the avatar can fetch the audio (served locally)
          wav_path:  Absolute path to the WAV file on disk
        """
        speed = speed if speed is not None else self._speed
        pitch = pitch if pitch is not None else self._pitch

        # Adjust speed/pitch based on emotion for expressiveness
        speed, pitch = self._emotion_to_params(emotion, speed, pitch)

        wav_path = await self._synthesize(text, speed, pitch)
        audio_url = f"http://127.0.0.1:{_AUDIO_SERVE_PORT}/audio/{wav_path.name}"

        return {"audio_url": audio_url, "wav_path": str(wav_path)}

    async def check_health(self) -> bool:
        """Returns True if the TTS engine is reachable."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self._base_url}/version")
                return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _emotion_to_params(self, emotion: str, speed: float, pitch: float) -> tuple[float, float]:
        """
        Translate emotion to speed/pitch adjustments.
        These are small nudges, not dramatic changes.
        The underlying AivisSpeech engine handles most expressiveness internally.
        """
        adjustments: dict[str, tuple[float, float]] = {
            "happy":     (speed * 1.05, pitch + 0.02),
            "excited":   (speed * 1.10, pitch + 0.05),
            "sad":       (speed * 0.90, pitch - 0.03),
            "angry":     (speed * 1.05, pitch + 0.03),
            "surprised": (speed * 1.10, pitch + 0.05),
            "relaxed":   (speed * 0.93, pitch - 0.01),
            "neutral":   (speed, pitch),
        }
        return adjustments.get(emotion, (speed, pitch))

    async def _synthesize(self, text: str, speed: float, pitch: float) -> Path:
        """
        Run the VOICEVOX audio_query -> synthesis pipeline.
        Returns the path to the resulting WAV file.
        Caches results by content hash to avoid re-synthesizing identical text.
        """
        # Cache key: hash of text + speaker + speed + pitch
        cache_key = hashlib.sha256(
            f"{text}|{self._speaker_id}|{speed:.3f}|{pitch:.3f}".encode()
        ).hexdigest()[:16]
        wav_path = self._cache_dir / f"{cache_key}.wav"

        if wav_path.exists():
            logger.debug("TTS cache hit: %s", cache_key)
            return wav_path

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: audio_query
            query_resp = await client.post(
                f"{self._base_url}/audio_query",
                params={"text": text, "speaker": self._speaker_id},
            )
            query_resp.raise_for_status()
            audio_query: dict[str, Any] = query_resp.json()

            # Apply speed/pitch overrides
            audio_query["speedScale"] = speed
            audio_query["pitchScale"] = pitch

            # Step 2: synthesis
            synth_resp = await client.post(
                f"{self._base_url}/synthesis",
                params={"speaker": self._speaker_id},
                json=audio_query,
            )
            synth_resp.raise_for_status()

            wav_path.write_bytes(synth_resp.content)

        logger.info("TTS synthesized: %d chars -> %s", len(text), wav_path.name)
        return wav_path