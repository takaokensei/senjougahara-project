"""
brain/agent/structured_output.py

Defines the canonical structured output schema that the LLM must produce:
  { text, emotion, animation, priority }

This convention is adopted from the pattern described in vierisid/jarvis (studied
as architecture reference only — not code-copied; RSALv2 license). Reimplemented
independently using Pydantic.

The LLM is instructed to always respond with a JSON object matching this schema.
The agent loop uses this module to parse and validate the response before acting.
"""

from __future__ import annotations

import json
import logging
import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class Emotion(str, Enum):
    """Maps to VRM blendshape presets. Must stay in sync with shared/schemas/bridge-messages.json."""
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    SURPRISED = "surprised"
    CONFUSED = "confused"
    ANNOYED = "annoyed"
    RELAXED = "relaxed"


class Priority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


logger = logging.getLogger(__name__)

# Heuristic CJK character ranges: Chinese/Japanese Kanji and Hanzi (\u4e00-\u9fff, \u3400-\u4dbf, etc.)
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uF900-\uFAFF]")
_PAREN_GROUPS_RE = re.compile(r"\(([^)]*)\)")


def _translate_to_pt(text: str) -> str:
    """Fast auto-translation of Japanese text to Brazilian Portuguese."""
    import httpx
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {"client": "gtx", "sl": "ja", "tl": "pt", "dt": "t", "q": text}
        r = httpx.get(url, params=params, timeout=2.5)
        if r.status_code == 200:
            return "".join([p[0] for p in r.json()[0] if p[0]]).strip()
    except Exception:
        pass
    return ""


def sanitize_bilingual_text(raw_text: str) -> str:
    """
    Sanitize text to guarantee at most ONE (Portuguese) translation parenthesis,
    and prevent Chinese/CJK translation leakage.
    
    1. If multiple parentheses groups exist (e.g. `Frase (trad) ("..." 译为 "...")`):
       Keep only the base text and the first parenthetical group, discarding trailing meta-notes.
    2. Check for CJK characters in the translation parenthesis:
       If CJK is found, log a clear warning and auto-correct using _translate_to_pt.
    """
    text = raw_text.strip()
    matches = list(_PAREN_GROUPS_RE.finditer(text))
    if not matches:
        return text

    first_match = matches[0]
    base_japanese = text[:first_match.start()].strip()
    first_paren_content = first_match.group(1).strip()

    if len(matches) > 1:
        extra_groups = [m.group(0) for m in matches[1:]]
        logger.warning(
            "Multiple parenthetical groups detected in response (%d groups). Discarding extra meta-notes %s from text: '%s'",
            len(matches), extra_groups, text
        )

    if _CJK_RE.search(first_paren_content) or "译" in first_paren_content or "中文" in first_paren_content:
        logger.warning(
            "Detected non-Portuguese (CJK) text inside translation parentheses: '%s' in text: '%s'. Auto-correcting to Portuguese.",
            first_paren_content, text
        )
        if base_japanese:
            auto_pt = _translate_to_pt(base_japanese)
            if auto_pt:
                first_paren_content = auto_pt

    if base_japanese and first_paren_content:
        return f"{base_japanese} ({first_paren_content})"
    elif base_japanese:
        return base_japanese
    else:
        return first_paren_content


class StructuredResponse(BaseModel):
    """
    The structured output every LLM response must conform to.
    
    - text: The response text displayed on screen.
    - japanese_text: Spoken Japanese text for AivisSpeech.
    - portuguese_translation: Translation in Brazilian Portuguese.
    - emotion: The facial expression to display during speech.
    - animation: VRMA animation clip name (must exist in avatar/assets/animations/).
    - priority: Controls interrupt/queue behavior in the avatar state machine.
    """
    text: str = Field(default="", description="The spoken/displayed response.")
    japanese_text: str | None = Field(default=None, description="Spoken Japanese text for AivisSpeech.")
    portuguese_translation: str | None = Field(default=None, description="Portuguese translation for display.")
    emotion: Emotion = Field(default=Emotion.NEUTRAL, description="Facial expression preset.")
    animation: str = Field(default="idle", description="VRMA animation clip name.")
    priority: Priority = Field(default=Priority.NORMAL, description="Response priority.")

    @model_validator(mode="after")
    def populate_or_validate_text(self) -> StructuredResponse:
        # If japanese_text is set, sanitize or auto-translate the Portuguese translation
        if self.japanese_text:
            has_cjk = bool(self.portuguese_translation and _CJK_RE.search(self.portuguese_translation))
            if not self.portuguese_translation or has_cjk or (self.portuguese_translation and "译" in self.portuguese_translation):
                if has_cjk:
                    logger.warning(
                        "Detected non-Portuguese (CJK) text in portuguese_translation field: '%s'. Auto-correcting.",
                        self.portuguese_translation
                    )
                auto_pt = _translate_to_pt(self.japanese_text)
                if auto_pt:
                    self.portuguese_translation = auto_pt

            if self.portuguese_translation:
                self.text = f"{self.japanese_text} ({self.portuguese_translation})"
            else:
                self.text = self.japanese_text

        elif not self.text or not self.text.strip():
            if self.portuguese_translation:
                self.text = self.portuguese_translation
            else:
                raise ValueError("text must not be blank")
        else:
            # Defensively sanitize any multiple parentheses or CJK in text
            self.text = sanitize_bilingual_text(self.text)

        return self

    @field_validator("emotion", mode="before")
    @classmethod
    def normalize_emotion(cls, v: Any) -> Emotion:
        if isinstance(v, Emotion):
            return v
        if isinstance(v, str):
            v_clean = v.strip().lower()
            aliases: dict[str, Emotion] = {
                "friendly": Emotion.HAPPY,
                "cheerful": Emotion.HAPPY,
                "joyful": Emotion.HAPPY,
                "excited": Emotion.HAPPY,
                "smirk": Emotion.HAPPY,
                "amused": Emotion.HAPPY,
                "content": Emotion.HAPPY,
                "thoughtful": Emotion.RELAXED,
                "calm": Emotion.RELAXED,
                "curious": Emotion.CONFUSED,
                "puzzled": Emotion.CONFUSED,
                "shocked": Emotion.SURPRISED,
                "scared": Emotion.SURPRISED,
                "mad": Emotion.ANGRY,
                "furious": Emotion.ANGRY,
                "disgusted": Emotion.ANNOYED,
            }
            if v_clean in aliases:
                return aliases[v_clean]
            try:
                return Emotion(v_clean)
            except ValueError:
                return Emotion.NEUTRAL
        return Emotion.NEUTRAL

    @field_validator("priority", mode="before")
    @classmethod
    def normalize_priority(cls, v: Any) -> Priority:
        if isinstance(v, Priority):
            return v
        if isinstance(v, str):
            v_clean = v.strip().lower()
            try:
                return Priority(v_clean)
            except ValueError:
                return Priority.NORMAL
        return Priority.NORMAL


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
_FIRST_OBJECT_RE = re.compile(r"\{[\s\S]*\}", re.DOTALL)


def parse_structured_response(raw: str) -> StructuredResponse:
    """
    Parse a StructuredResponse from LLM output.

    Strategy:
    1. If the raw string is valid JSON, parse directly.
    2. If it contains a ```json ... ``` block, extract and parse.
    3. If it contains any JSON object, extract the first one.
    4. If all else fails, treat the entire string as plain text with neutral defaults.

    This fallback chain ensures that even a misbehaving LLM produces *some* output
    rather than crashing the agent loop.
    """
    raw = raw.strip()

    # Attempt 1: direct parse
    try:
        return StructuredResponse.model_validate(json.loads(raw))
    except Exception:
        pass

    # Attempt 2: ```json ... ``` block
    m = _JSON_BLOCK_RE.search(raw)
    if m:
        try:
            return StructuredResponse.model_validate(json.loads(m.group(1)))
        except Exception:
            pass

    # Attempt 3: search all { ... } blocks for a valid StructuredResponse (has "text" or "japanese_text" key)
    for match in re.finditer(r"\{[\s\S]*?\}", raw):
        try:
            obj = json.loads(match.group(0))
            if isinstance(obj, dict) and ("text" in obj or "japanese_text" in obj or "portuguese_translation" in obj):
                return StructuredResponse.model_validate(obj)
        except Exception:
            pass

    # Fallback: plain text response (clean up any stray JSON tool call artifacts)
    clean_text = re.sub(r"\{[\s\S]*?\}", "", raw).strip()
    return StructuredResponse(text=clean_text if clean_text else (raw if raw else "..."), emotion=Emotion.NEUTRAL, animation="idle")


def structured_response_to_dict(response: StructuredResponse) -> dict[str, Any]:
    """Serialize for sending over the bridge protocol."""
    return response.model_dump()
