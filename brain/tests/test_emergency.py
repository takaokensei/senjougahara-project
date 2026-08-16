"""
brain/tests/test_emergency.py

Unit tests for EmergencyController and AgentLoop emergency gating.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from brain.agent.loop import AgentLoop
from brain.agent.providers.base import BaseLLMProvider, LLMResponse, ToolCall, ToolDefinition
from brain.permissions.emergency import EmergencyController, EmergencyState
from brain.permissions.policy import PermissionEngine
from brain.tools import registry


class MockToolLLMProvider(BaseLLMProvider):
    def __init__(self, should_call_tool: bool = True):
        self.should_call_tool = should_call_tool

    async def complete(self, messages, tools=None, system_prompt=None):
        if self.should_call_tool:
            self.should_call_tool = False
            return LLMResponse(
                tool_calls=[ToolCall(call_id="call_1", tool_name="dummy_tool", arguments={})]
            )
        return LLMResponse(
            text='{"text": "Done.", "emotion": "neutral", "animation": "idle", "priority": "normal"}'
        )

    def format_tool_result(self, call_id, tool_name, result, is_error=False):
        return {"role": "tool", "content": str(result), "tool_call_id": call_id}


class TestEmergencyController:
    def test_emergency_controller_lifecycle(self):
        ctrl = EmergencyController()
        assert ctrl.is_normal
        assert ctrl.can_execute()[0] is True

        # Pause
        ctrl.pause("Suspicious activity")
        assert ctrl.is_paused
        can_exec, reason = ctrl.can_execute()
        assert not can_exec
        assert "PAUSED" in reason

        # Resume
        resumed = ctrl.resume()
        assert resumed is True
        assert ctrl.is_normal
        assert ctrl.can_execute()[0] is True

        # Kill
        ctrl.kill("Critical stop")
        assert ctrl.is_killed
        can_exec, reason = ctrl.can_execute()
        assert not can_exec
        assert "KILL SWITCH" in reason

        # Resume fails when killed
        assert ctrl.resume() is False
        assert ctrl.is_killed

        # Reset recovers to normal
        ctrl.reset()
        assert ctrl.is_normal
        assert ctrl.can_execute()[0] is True

    @pytest.mark.asyncio
    async def test_emergency_controller_blocks_agent_tool_calls(self, tmp_path: Path):
        @registry.tool(name="dummy_tool", description="Dummy tool for testing", risk=registry.RISK_LOW)
        async def dummy_fn():
            return "executed"

        permission_engine = PermissionEngine(audit_log_path=tmp_path / "audit.jsonl")
        emergency = EmergencyController()
        emergency.pause("Testing pause")

        provider = MockToolLLMProvider(should_call_tool=True)
        agent = AgentLoop(
            provider=provider,
            permission_engine=permission_engine,
            system_prompt="You are an assistant.",
            emergency_controller=emergency,
        )

        resp = await agent.process("Run dummy tool")
        assert resp.text == "Done."
        # Verify tool was blocked by emergency controller in loop
        call_result = await agent._execute_tool_call(
            ToolCall(call_id="c1", tool_name="dummy_tool", arguments={})
        )
        assert call_result["is_error"] is True
        assert "PAUSED" in call_result["result"]

        # Resume allows execution
        emergency.resume()
        call_result_ok = await agent._execute_tool_call(
            ToolCall(call_id="c2", tool_name="dummy_tool", arguments={})
        )
        assert call_result_ok["is_error"] is False
        assert call_result_ok["result"] == "executed"
