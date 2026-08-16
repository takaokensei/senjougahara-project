"""
brain/tests/test_memory_extractor.py

Unit tests for FactExtractor and integration with SQLite FactMemory.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from brain.agent.providers.base import BaseLLMProvider, LLMResponse
from brain.memory.db import initialize_db
from brain.memory.extractor import (
    FactExtractor,
    extract_facts_heuristic,
    parse_extracted_facts,
)
from brain.memory.facts import FactMemory


class MockExtractionLLMProvider(BaseLLMProvider):
    def __init__(self, response_json: str):
        self.response_json = response_json

    async def complete(self, messages, tools=None, system_prompt=None):
        return LLMResponse(text=self.response_json)

    def format_tool_result(self, call_id, tool_name, result, is_error=False):
        return {"role": "tool", "content": str(result), "tool_call_id": call_id}

    def format_assistant_turn(self, response: LLMResponse):
        return None



class TestMemoryExtractor:
    def test_parse_extracted_facts_json(self):
        clean_json = '{"facts": [{"key": "user_name", "value": "Cauã", "confidence": 1.0, "category": "general"}]}'
        parsed = parse_extracted_facts(clean_json)
        assert len(parsed) == 1
        assert parsed[0].key == "user_name"
        assert parsed[0].value == "Cauã"
        assert parsed[0].confidence == 1.0
        assert parsed[0].category == "general"
        assert parsed[0].expires_at is None

        markdown_json = '```json\n{"facts": [{"key": "user_city", "value": "Natal", "confidence": 0.85, "category": "general"}]}\n```'
        parsed_md = parse_extracted_facts(markdown_json)
        assert len(parsed_md) == 1
        assert parsed_md[0].key == "user_city"
        assert parsed_md[0].value == "Natal"
        assert parsed_md[0].confidence == 0.85

        invalid = 'No facts found here.'
        assert parse_extracted_facts(invalid) == []

    def test_parse_extracted_facts_with_expiration_and_defaults(self):
        json_with_dates = (
            '{"facts": ['
            '{"key": "exam_dsp", "value": "Prova 1", "confidence": 0.9, "category": "event", "expires_at": "2026-08-20T23:59:59"},'
            '{"key": "hobby", "value": "Anime", "confidence": 0.8},'
            '{"key": "bad_date", "value": "Test", "expires_at": "not-a-valid-date"}'
            ']}'
        )
        parsed = parse_extracted_facts(json_with_dates)
        assert len(parsed) == 3
        # Valid date
        assert parsed[0].category == "event"
        assert parsed[0].expires_at == "2026-08-20T23:59:59"
        # Defaults
        assert parsed[1].category == "general"
        assert parsed[1].expires_at is None
        # Malformed date fallback to None
        assert parsed[2].expires_at is None

    def test_extract_facts_heuristic(self):
        facts = extract_facts_heuristic("Olá, meu nome é Cauã e eu moro em Natal!")
        keys = {f.key: f.value for f in facts}
        assert keys.get("user_name") == "Cauã"
        assert "Natal" in keys.get("user_location", "")

    @pytest.mark.asyncio
    async def test_extract_and_save_to_fact_memory(self, tmp_path: Path):
        db_path = tmp_path / "test_memory.db"
        await initialize_db(db_path)
        memory = FactMemory(db_path)

        mock_llm = MockExtractionLLMProvider(
            '{"facts": [{"key": "favorite_editor", "value": "VS Code", "confidence": 0.95, "category": "preference"}]}'
        )
        extractor = FactExtractor(provider=mock_llm)

        saved = await extractor.extract_and_save(
            user_message="Eu gosto muito do VS Code e meu nome é Cauã.",
            assistant_response="Entendido, anotado!",
            memory=memory,
        )

        assert "favorite_editor" in saved
        assert "user_name" in saved

        saved_editor = await memory.get_fact("favorite_editor")
        assert saved_editor == "VS Code"

        saved_name = await memory.get_fact("user_name")
        assert saved_name == "Cauã"

        prompt_str = await memory.format_for_prompt()
        assert "[preference] favorite_editor: VS Code" in prompt_str
        assert "[general] user_name: Cauã" in prompt_str

