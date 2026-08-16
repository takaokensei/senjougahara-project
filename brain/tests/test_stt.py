"""
brain/tests/test_stt.py

Unit tests for STTEngine language forcing and UTF-8 encoding preservation.
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from brain.speech.stt import STTEngine


class MockSegment:
    def __init__(self, text: str):
        self.text = text


class MockTranscriptionInfo:
    def __init__(self, language: str = "pt", language_probability: float = 0.98):
        self.language = language
        self.language_probability = language_probability


class TestSTTEngine:
    def test_stt_transcription_preserves_utf8_accents(self):
        """Ensure accented Portuguese characters (é, ã, ç, ó, í, ê) are preserved without mojibake."""
        engine = STTEngine(language="pt")
        expected_text = "Oi bébé, você não vai me dar atenção? Olá mundo com coração!"

        mock_segments = [MockSegment("Oi bébé,"), MockSegment("você não vai me dar atenção? Olá mundo com coração!")]
        mock_info = MockTranscriptionInfo(language="pt", language_probability=0.99)

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (mock_segments, mock_info)
        engine._model = mock_model

        result = engine.transcribe_bytes(b"DUMMY_AUDIO_BYTES")

        # Must match expected accented string exactly
        assert result == expected_text
        assert "é" in result
        assert "ã" in result
        assert "ç" in result
        assert "├" not in result
        assert "®" not in result
        assert "ú" not in result or "não" in result

    def test_stt_transcribe_passes_forced_language_pt(self):
        """Ensure transcribe passes language='pt' to WhisperModel."""
        engine = STTEngine(language="pt")

        mock_segments = [MockSegment("Teste")]
        mock_info = MockTranscriptionInfo(language="pt", language_probability=0.99)
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (mock_segments, mock_info)
        engine._model = mock_model

        result = engine.transcribe_bytes(b"DUMMY_AUDIO_BYTES")
        assert result == "Teste"

        # Verify arguments passed to model.transcribe
        mock_model.transcribe.assert_called_once()
        _, kwargs = mock_model.transcribe.call_args
        assert kwargs.get("language") == "pt"
        assert kwargs.get("vad_filter") is True

    def test_stt_low_confidence_fallback_to_pt(self):
        """When language='auto', low confidence detection (< 0.6) falls back to 'pt'."""
        engine = STTEngine(language="auto", min_language_confidence=0.6)

        mock_segments_fr = [MockSegment("Oi bebe")]
        mock_info_fr = MockTranscriptionInfo(language="fr", language_probability=0.34)

        mock_segments_pt = [MockSegment("Oi bebê")]
        mock_info_pt = MockTranscriptionInfo(language="pt", language_probability=0.95)

        mock_model = MagicMock()
        # First call returns low-prob FR, second call returns forced PT
        mock_model.transcribe.side_effect = [
            (mock_segments_fr, mock_info_fr),
            (mock_segments_pt, mock_info_pt),
        ]
        engine._model = mock_model

        result = engine.transcribe_bytes(b"DUMMY_AUDIO_BYTES")
        assert result == "Oi bebê"
        assert mock_model.transcribe.call_count == 2
        # Check second call forced pt
        second_call_kwargs = mock_model.transcribe.call_args_list[1][1]
        assert second_call_kwargs.get("language") == "pt"
