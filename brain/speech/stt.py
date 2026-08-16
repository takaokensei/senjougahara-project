"""
brain/speech/stt.py

Speech-to-Text (STT) module using faster-whisper (CTranslate2).
Supports GPU (CUDA int8/fp16) with automatic CPU fallback.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class STTEngine:
    """
    Wraps faster-whisper for local speech recognition.
    """

    def __init__(
        self,
        model_size: str = "small",
        device: str = "auto",
        compute_type: str = "auto",
        language: str | None = None,
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self._model: Any = None

    def _get_device_and_compute(self) -> tuple[str, str]:
        if self.device != "auto" and self.compute_type != "auto":
            return self.device, self.compute_type

        # Auto-detect CUDA availability
        device = "cpu"
        compute_type = "int8"

        try:
            import torch
            if torch.cuda.is_available():
                device = "cuda"
                compute_type = "float16"
        except Exception:
            pass

        final_device = self.device if self.device != "auto" else device
        final_compute = self.compute_type if self.compute_type != "auto" else compute_type
        return final_device, final_compute

    def load_model(self) -> None:
        """Eagerly load the model into memory."""
        if self._model is not None:
            return

        from faster_whisper import WhisperModel

        device, compute_type = self._get_device_and_compute()
        logger.info("Loading faster-whisper model: %s on %s (%s)", self.model_size, device, compute_type)

        try:
            self._model = WhisperModel(self.model_size, device=device, compute_type=compute_type)
        except Exception as exc:
            if device == "cuda":
                logger.warning("Failed to load on CUDA (%s), falling back to CPU int8", exc)
                self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
            else:
                raise

    def transcribe_file(self, audio_path: str | Path) -> str:
        """Transcribe an audio file from disk."""
        self.load_model()
        segments, info = self._model.transcribe(
            str(audio_path),
            language=self.language,
            beam_size=5,
        )
        text_parts = [segment.text.strip() for segment in segments]
        result = " ".join(text_parts).strip()
        logger.info("STT Transcribed (%s, lang=%s): %s", audio_path, info.language, result[:80])
        return result

    def transcribe_bytes(self, audio_bytes: bytes) -> str:
        """Transcribe raw WAV/MP3 bytes."""
        self.load_model()
        stream = io.BytesIO(audio_bytes)
        segments, info = self._model.transcribe(
            stream,
            language=self.language,
            beam_size=5,
        )
        text_parts = [segment.text.strip() for segment in segments]
        result = " ".join(text_parts).strip()
        logger.info("STT Transcribed (%d bytes): %s", len(audio_bytes), result[:80])
        return result