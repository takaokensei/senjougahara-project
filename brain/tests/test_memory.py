"""
brain/tests/test_memory.py

Unit tests for SQLite-backed memory modules (facts, preferences, conversation log).
"""

import asyncio
from pathlib import Path
import pytest

from brain.memory.db import initialize_db
from brain.memory.facts import FactMemory
from brain.memory.preferences import PreferenceMemory
from brain.memory.conversation_log import ConversationLog


@pytest.fixture
def mem_db(tmp_path: Path) -> Path:
    db_file = tmp_path / "test_memory.db"
    asyncio.run(initialize_db(db_file))
    return db_file


class TestMemoryModules:
    def test_facts_crud(self, mem_db: Path):
        facts = FactMemory(mem_db)

        async def run():
            await facts.set_fact("user_name", "Cauã")
            val = await facts.get_fact("user_name")
            assert val == "Cauã"

            prompt_text = await facts.format_for_prompt()
            assert "user_name: Cauã" in prompt_text

        asyncio.run(run())

    def test_preferences_crud(self, mem_db: Path):
        prefs = PreferenceMemory(mem_db)

        async def run():
            await prefs.set_preference("theme", "dark")
            val = await prefs.get_preference("theme")
            assert val == "dark"

            prompt_text = await prefs.format_for_prompt()
            assert "theme: dark" in prompt_text

        asyncio.run(run())

    def test_conversation_log(self, mem_db: Path):
        log = ConversationLog(mem_db)

        async def run():
            await log.log_turn("user", "Hello Senjougahara")
            await log.log_turn("assistant", "Hello Cauã")

            turns = await log.get_recent_turns(limit=5)
            assert len(turns) == 2
            assert turns[0]["content"] == "Hello Senjougahara"
            assert turns[1]["content"] == "Hello Cauã"

        asyncio.run(run())