"""
brain/speech/wake_phrase.py

Wake phrase detection and acoustic echo suppression utilities.

Inspired by the wake phrase suppression pattern in vierisid/jarvis
(studied as architectural reference only, not code-copied; RSALv2 license).
Reimplemented independently in Python.
"""

from __future__ import annotations

import logging
import re
import wave
from pathlib import Path

logger = logging.getLogger(__name__)


def normalize_phrase_pattern(phrase: str) -> re.Pattern[str]:
    """
    Build a case-insensitive regex pattern with word boundaries for a wake phrase.
    Handles underscores as spaces or optional separators (e.g. 'hey_jarvis' -> 'hey[ _]jarvis').
    """
    phrase = phrase.strip().lower()
    parts = [re.escape(part) for part in re.split(r"[_\s]+", phrase) if part]
    if not parts:
        return re.compile(r"$^")
    
    joined = r"[\s_]+".join(parts)
    pattern_str = rf"(?:\b|^){joined}(?:\b|$)"
    return re.compile(pattern_str, re.IGNORECASE)


def contains_wake_phrase(text: str, phrase: str) -> bool:
    """
    Check whether a text string contains the wake phrase.

    Uses word-boundary regex matching and punctuation-stripping so that
    e.g. 'Hey, Jarvis!' matches phrase 'hey_jarvis' or 'hey jarvis'.
    """
    if not text or not phrase:
        return False

    pattern = normalize_phrase_pattern(phrase)
    cleaned_text = re.sub(r"[,\.!\?\"'()\[\]{}:;~]", " ", text)
    return bool(pattern.search(text) or pattern.search(cleaned_text))


def estimate_audio_duration_seconds(
    text: str = "",
    wav_path: Path | str | None = None,
) -> float:
    """
    Determine or estimate the duration of synthesized speech in seconds.

    If a valid WAV file is provided, computes exact duration from headers.
    Otherwise, estimates duration based on language heuristics (words / characters).
    """
    if wav_path:
        p = Path(wav_path)
        if p.is_file():
            try:
                with wave.open(str(p), "rb") as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    if rate > 0:
                        return float(frames) / float(rate)
            except Exception as exc:
                logger.debug("Failed reading WAV header from %s: %s", p, exc)

    if not text:
        return 1.0

    cjk_count = len(re.findall(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]", text))
    other_text = re.sub(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]", "", text).strip()
    word_count = len(other_text.split()) if other_text else 0

    duration = (cjk_count / 5.0) + (word_count / 3.0)
    return max(1.0, min(60.0, duration))
