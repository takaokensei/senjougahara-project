"""
brain/tests/test_personality_learner.py

Unit tests for PersonalityModel and style signals extraction.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from brain.agent.loop import AgentLoop
from brain.agent.providers.base import BaseLLMProvider, LLMResponse
from brain.memory.db import initialize_db
from brain.permissions.policy import PermissionEngine
from brain.personality.learner import PersonalityModel, extract_style_signals


class MockCapturePromptLLMProvider(BaseLLMProvider):
    def __init__(self):
        self.last_system_prompt: str | None = None

    async def complete(self, messages, tools=None, system_prompt=None):
        self.last_system_prompt = system_prompt
        return LLMResponse(
            text='{"text": "Entendido.", "emotion": "neutral", "animation": "idle", "priority": "normal"}'
        )

    def format_tool_result(self, call_id, tool_name, result, is_error=False):
        return {"role": "tool", "content": str(result), "tool_call_id": call_id}


class TestPersonalityLearner:
    def test_extract_style_signals_pt_en(self):
        # Verbosity negative
        sig1 = extract_style_signals("Por favor, seja mais curto e direto ao ponto.")
        assert len(sig1) == 1
        assert sig1[0]["preference"] == "verbosity"
        assert sig1[0]["direction"] == -1.0

        sig2 = extract_style_signals("Keep it concise, tldr please.")
        assert len(sig2) == 1
        assert sig2[0]["preference"] == "verbosity"
        assert sig2[0]["direction"] == -1.0

        # Verbosity positive
        sig3 = extract_style_signals("Pode me dar mais detalhes sobre isso?")
        assert len(sig3) == 1
        assert sig3[0]["preference"] == "verbosity"
        assert sig3[0]["direction"] == 1.0

        sig4 = extract_style_signals("Please elaborate in depth.")
        assert len(sig4) == 1
        assert sig4[0]["preference"] == "verbosity"
        assert sig4[0]["direction"] == 1.0

        # Formality
        sig5 = extract_style_signals("Use um tom mais formal.")
        assert len(sig5) == 1
        assert sig5[0]["preference"] == "formality"
        assert sig5[0]["direction"] == 1.0

        sig6 = extract_style_signals("Pode ser mais informal e descontraído.")
        assert len(sig6) == 1
        assert sig6[0]["preference"] == "formality"
        assert sig6[0]["direction"] == -1.0

        # No signals
        assert extract_style_signals("Que horas são?") == []

    @pytest.mark.asyncio
    async def test_personality_model_lifecycle_and_persistence(self, tmp_path: Path):
        db_path = tmp_path / "memory.db"
        await initialize_db(db_path)

        model = PersonalityModel(db_path=db_path)
        assert model.get_preference("verbosity") == 0.0

        # Apply 2 negative verbosity signals (-0.25 * 2 = -0.5)
        await model.apply_signals([{"preference": "verbosity", "direction": -1.0}])
        await model.apply_signals([{"preference": "verbosity", "direction": -1.0}])
        assert model.get_preference("verbosity") == -0.5

        ctx = model.get_style_prompt_context()
        assert "diretas, concisas" in ctx

        # Test persistence in new instance
        model2 = PersonalityModel(db_path=db_path)
        assert model2.get_preference("verbosity") == -0.5

    @pytest.mark.asyncio
    async def test_agent_loop_style_injection(self, tmp_path: Path):
        db_path = tmp_path / "memory.db"
        await initialize_db(db_path)

        model = PersonalityModel(db_path=db_path)
        # Shift towards formality
        await model.apply_signals([{"preference": "formality", "direction": 1.0}], step=0.5)

        provider = MockCapturePromptLLMProvider()
        permission_engine = PermissionEngine(audit_log_path=tmp_path / "audit.jsonl")

        agent = AgentLoop(
            provider=provider,
            permission_engine=permission_engine,
            system_prompt="Base prompt.",
            personality_model=model,
        )

        resp = await agent.process("Olá, responda de forma mais curta.")
        assert resp.text == "Entendido."
        # Verify style directive was appended to system prompt
        assert provider.last_system_prompt is not None
        assert "Base prompt." in provider.last_system_prompt
        assert "polido e formal" in provider.last_system_prompt or "concisas" in provider.last_system_prompt
