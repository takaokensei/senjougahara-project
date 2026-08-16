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
            await facts.set_fact("user_name", "Cauã", category="general")
            val = await facts.get_fact("user_name")
            assert val == "Cauã"

            prompt_text = await facts.format_for_prompt()
            assert "[general] user_name: Cauã" in prompt_text

        asyncio.run(run())

    def test_facts_category_and_expiration(self, mem_db: Path):
        facts = FactMemory(mem_db)

        async def run():
            # Permanent fact
            await facts.set_fact("course", "Electrical Engineering", category="interest")
            # Future event
            await facts.set_fact("exam_dsp", "2099-01-01", category="event", expires_at="2099-01-01 23:59:59")
            # Expired event (in the past)
            await facts.set_fact("old_meeting", "2020-01-01", category="event", expires_at="2020-01-01 00:00:00")

            all_facts = await facts.list_all_facts()
            assert "course" in all_facts
            assert "exam_dsp" in all_facts
            assert "old_meeting" not in all_facts  # Expired fact must be filtered out

            # Test purge_expired
            deleted = await facts.purge_expired()
            assert deleted == 1

            # Run again, 0 deleted
            deleted_again = await facts.purge_expired()
            assert deleted_again == 0

        asyncio.run(run())

    def test_idempotent_migration(self, tmp_path: Path):
        from brain.memory.db import _init_sync
        db_file = tmp_path / "idempotent_test.db"
        # Run init sync twice on the same DB file — must not raise any error
        _init_sync(db_file)
        _init_sync(db_file)

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