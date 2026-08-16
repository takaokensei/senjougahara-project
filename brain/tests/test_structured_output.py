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

    def test_parse_emotion_alias_normalizes(self):
        raw = '{"text": "hi", "emotion": "friendly"}'
        r = parse_structured_response(raw)
        assert r.text == "hi"
        assert r.emotion == Emotion.HAPPY

    def test_parse_unknown_emotion_falls_back_to_neutral(self):
        raw = '{"text": "hi", "emotion": "NOTANEMMOTION123"}'
        r = parse_structured_response(raw)
        assert r.text == "hi"
        assert r.emotion == Emotion.NEUTRAL

    def test_serialize(self):
        r = StructuredResponse(text="Hello", emotion=Emotion.HAPPY, animation="nod")
        d = r.model_dump()
        assert d["text"] == "Hello"
        assert d["emotion"] == "happy"

    def test_multiple_parentheses_sanitized_to_first(self, caplog):
        # Reproduces the real bug with duplicate meta-explanatory translation note
        raw = '別に…関心の対象じゃないからな。(Não me importo com isso.) ("別に…関心の対象じゃないからな。" 译为 "其实…这不关我的事。")'
        r = StructuredResponse(text=raw)
        assert r.text.count("(") == 1
        assert "Não me importo com isso." in r.text
        assert "译为" not in r.text
        assert "Multiple parenthetical groups detected" in caplog.text

    def test_cjk_in_parentheses_triggers_warning(self, caplog):
        # Reproduces Chinese translation leakage inside parentheses
        raw = '別に…関心の対象じゃないからな。(其实我没在意……这不关我的事。)'
        r = StructuredResponse(text=raw)
        assert "Detected non-Portuguese (CJK) text inside translation parentheses" in caplog.text
        assert r.text.count("(") <= 1

    def test_bilingual_fields_combined(self):
        r = StructuredResponse(
            japanese_text="了解したわ。",
            portuguese_translation="Entendido.",
            emotion=Emotion.NEUTRAL,
        )
        assert r.text == "了解したわ。 (Entendido.)"

    def test_parse_json_with_separate_bilingual_fields(self):
        raw = '{"japanese_text": "こんにちは。", "portuguese_translation": "Olá.", "emotion": "happy", "animation": "greeting"}'
        r = parse_structured_response(raw)
        assert r.text == "こんにちは。 (Olá.)"
        assert r.emotion == Emotion.HAPPY

    def test_sync_parse_does_not_block_on_cjk(self):
        """parse_structured_response must execute synchronously without any network I/O."""
        raw = '{"japanese_text": "了解したわ。", "portuguese_translation": "明白", "emotion": "neutral"}'
        # Should parse instantly and clear the CJK translation without making HTTP requests
        r = parse_structured_response(raw)
        assert r.japanese_text == "了解したわ。"
        assert r.portuguese_translation is None
        assert r.text == "了解したわ。"


class TestAsyncTranslation:
    @pytest.mark.asyncio
    async def test_ensure_portuguese_translation_success(self, monkeypatch):
        from brain.agent.structured_output import ensure_portuguese_translation

        async def mock_translate(text: str, timeout: float = 2.0) -> str:
            return "Entendido."

        monkeypatch.setattr("brain.agent.structured_output.async_translate_to_pt", mock_translate)

        resp = StructuredResponse(japanese_text="了解したわ。", emotion=Emotion.NEUTRAL)
        assert resp.portuguese_translation is None

        updated = await ensure_portuguese_translation(resp)
        assert updated.portuguese_translation == "Entendido."
        assert updated.text == "了解したわ。 (Entendido.)"

    @pytest.mark.asyncio
    async def test_ensure_portuguese_translation_failure_preserves_text_without_crash(self, monkeypatch):
        from brain.agent.structured_output import ensure_portuguese_translation

        async def mock_translate_fail(text: str, timeout: float = 2.0) -> str:
            return ""  # Simulates network timeout or outage

        monkeypatch.setattr("brain.agent.structured_output.async_translate_to_pt", mock_translate_fail)

        resp = StructuredResponse(japanese_text="了解したわ。", emotion=Emotion.NEUTRAL)
        updated = await ensure_portuguese_translation(resp)
        assert updated.portuguese_translation is None
        assert updated.text == "了解したわ。"  # Original Japanese text preserved safely