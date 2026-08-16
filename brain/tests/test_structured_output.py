"""
brain/tests/test_structured_output.py

Unit tests for the structured output schema and parser.
"""

import pytest
from brain.agent.structured_output import (
    Emotion,
    Priority,
    StructuredResponse,
    parse_structured_response,
)


class TestStructuredResponse:
    def test_valid_full_response(self):
        r = StructuredResponse(
            text="Hello, how can I help you?",
            emotion=Emotion.HAPPY,
            animation="greeting",
            priority=Priority.NORMAL,
        )
        assert r.text == "Hello, how can I help you?"
        assert r.emotion == Emotion.HAPPY
        assert r.animation == "greeting"
        assert r.priority == Priority.NORMAL

    def test_defaults(self):
        r = StructuredResponse(text="hi")
        assert r.emotion == Emotion.NEUTRAL
        assert r.animation == "idle"
        assert r.priority == Priority.NORMAL

    def test_text_strip_whitespace(self):
        r = StructuredResponse(text="  hello  ")
        assert r.text == "hello"

    def test_blank_text_raises(self):
        with pytest.raises(Exception):
            StructuredResponse(text="   ")

    def test_empty_text_raises(self):
        with pytest.raises(Exception):
            StructuredResponse(text="")


class TestParseStructuredResponse:
    def test_parse_valid_json(self):
        raw = '{"text": "Hello!", "emotion": "happy", "animation": "nod", "priority": "normal"}'
        r = parse_structured_response(raw)
        assert r.text == "Hello!"
        assert r.emotion == Emotion.HAPPY
        assert r.animation == "nod"

    def test_parse_json_block(self):
        raw = '```json\n{"text": "Hi", "emotion": "neutral"}\n```'
        r = parse_structured_response(raw)
        assert r.text == "Hi"
        assert r.emotion == Emotion.NEUTRAL

    def test_parse_embedded_json(self):
        raw = 'Sure, here is my response: {"text": "Done!", "emotion": "happy"}'
        r = parse_structured_response(raw)
        assert r.text == "Done!"

    def test_fallback_plain_text(self):
        raw = "I could not format a JSON response."
        r = parse_structured_response(raw)
        assert r.text == raw
        assert r.emotion == Emotion.NEUTRAL
        assert r.animation == "idle"

    def test_parse_missing_optional_fields(self):
        raw = '{"text": "Just text"}'
        r = parse_structured_response(raw)
        assert r.text == "Just text"
        assert r.emotion == Emotion.NEUTRAL

    def test_parse_invalid_emotion_falls_back(self):
        # Invalid enum value should fail validation and fall back to plain text
        raw = '{"text": "hi", "emotion": "NOTANEMMOTION123"}'
        r = parse_structured_response(raw)
        # Should have fallen back to plain-text mode
        assert r.text  # Some non-empty text

    def test_serialize(self):
        r = StructuredResponse(text="Hello", emotion=Emotion.HAPPY, animation="nod")
        d = r.model_dump()
        assert d["text"] == "Hello"
        assert d["emotion"] == "happy"