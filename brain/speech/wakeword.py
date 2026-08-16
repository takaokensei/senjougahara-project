"""
brain/speech/wakeword.py

Wake-word detection module using openWakeWord (ONNX).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


class WakeWordDetector:
    """
    Wraps openWakeWord for continuous stream inference.
    """

    def __init__(
        self,
        phrase: str = "hey_jarvis",
        custom_model_path: str | None = None,
        threshold: float = 0.5,
    ) -> None:
        self.phrase = phrase
        self.custom_model_path = custom_model_path
        self.threshold = threshold
        self._model: Any = None

    def load_model(self) -> None:
        if self._model is not None:
            return

        import openwakeword
        from openwakeword.model import Model

        model_paths = []
        if self.custom_model_path and Path(self.custom_model_path).exists():
            model_paths.append(self.custom_model_path)
            logger.info("Loading custom wake word model: %s", self.custom_model_path)
            self._model = Model(wakeword_models=model_paths)
        else:
            logger.info("Loading default openWakeWord model: %s", self.phrase)
            self._model = Model(wakeword_models=[self.phrase] if self.phrase else None)

    def process_frame(self, audio_chunk: Any) -> tuple[bool, str | None, float]:
        """
        Process a 16-bit PCM 16kHz audio frame (typically 1280 samples / 80ms).
        Returns (detected, model_name, confidence).
        """
        self.load_model()
        prediction = self._model.predict(audio_chunk)

        for model_name, score in prediction.items():
            if score >= self.threshold:
                logger.info("Wake word detected! Model: %s (score=%.3f)", model_name, score)
                return True, model_name, float(score)

        return False, None, 0.0