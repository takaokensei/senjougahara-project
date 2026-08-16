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

from pydantic import BaseModel, Field, field_validator


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
    
    - text: The spoken response text (will be sent to TTS).
    - emotion: The facial expression to display during speech.
    - animation: VRMA animation clip name (must exist in avatar/assets/animations/).
    - priority: Controls interrupt/queue behavior in the avatar state machine.
    """
    text: str = Field(..., min_length=1, description="The spoken response (sent to TTS).")
    emotion: Emotion = Field(default=Emotion.NEUTRAL, description="Facial expression preset.")
    animation: str = Field(default="idle", description="VRMA animation clip name.")
    priority: Priority = Field(default=Priority.NORMAL, description="Response priority.")

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be blank")
        return v.strip()


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

    # Attempt 3: first { ... } block
    m2 = _FIRST_OBJECT_RE.search(raw)
    if m2:
        try:
            return StructuredResponse.model_validate(json.loads(m2.group(0)))
        except Exception:
            pass

    # Fallback: plain text response
    return StructuredResponse(text=raw if raw else "...", emotion=Emotion.NEUTRAL, animation="idle")


def structured_response_to_dict(response: StructuredResponse) -> dict[str, Any]:
    """Serialize for sending over the bridge protocol."""
    return response.model_dump()
