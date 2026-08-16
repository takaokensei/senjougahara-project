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
        if not self.text or not self.text.strip():
            if self.japanese_text and self.portuguese_translation:
                self.text = f"{self.japanese_text} ({self.portuguese_translation})"
            elif self.japanese_text:
                self.text = self.japanese_text
            elif self.portuguese_translation:
                self.text = self.portuguese_translation
            else:
                raise ValueError("text must not be blank")
        else:
            self.text = self.text.strip()
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
