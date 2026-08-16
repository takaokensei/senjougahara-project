"""
brain/tests/test_agent_loop_providers.py

Contract tests for format_assistant_turn — verifies that every provider
correctly serializes the assistant tool-use turn into the conversation history.

The bug (pre-fix): loop.py inspected `response.raw.content` using Anthropic
SDK attribute access — which silently produced nothing for Ollama (raw is a
dict), OpenAI (raw is an SDK Completion object without `.content`), and Gemini.
This caused multi-tool-call conversations to have a corrupted history because
the assistant turn was never inserted before the tool_result messages.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brain.agent.providers.base import LLMResponse, ToolCall
from brain.agent.providers.anthropic import AnthropicProvider
from brain.agent.providers.ollama import OllamaProvider
from brain.agent.providers.openai import OpenAIProvider
from brain.agent.providers.gemini import GeminiProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response_with_two_tool_calls() -> LLMResponse:
    """A normalised LLMResponse with 2 tool calls and no raw SDK object."""
    return LLMResponse(
        text="Let me check two things.",
        tool_calls=[
            ToolCall(call_id="call_1", tool_name="list_windows", arguments={}),
            ToolCall(call_id="call_2", tool_name="get_system_info", arguments={}),
        ],
        raw=None,  # explicitly None to test the non-Anthropic path
    )


def _make_response_no_tool_calls() -> LLMResponse:
    return LLMResponse(text="Just a plain text reply.", tool_calls=[], raw=None)


# ---------------------------------------------------------------------------
# Parametrised provider contract test
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("provider_cls,provider_kwargs", [
    (OllamaProvider,   {"model": "test-model", "host": "http://localhost:11434"}),
    (OpenAIProvider,   {"model": "gpt-4o"}),
    (AnthropicProvider, {"model": "claude-sonnet-4-5"}),
    (GeminiProvider,   {"model": "gemini-2.0-flash"}),
])
class TestFormatAssistantTurnContract:
    """Every provider must satisfy these three contracts."""

    def _make_provider(self, provider_cls, provider_kwargs):
        """Instantiate provider without real API keys / network calls."""
        if provider_cls is AnthropicProvider:
            with patch("anthropic.AsyncAnthropic"):
                return provider_cls(**provider_kwargs, api_key="test-key")
        if provider_cls is OpenAIProvider:
            with patch("openai.AsyncOpenAI"):
                return provider_cls(**provider_kwargs, api_key="test-key")
        return provider_cls(**provider_kwargs)

    def test_returns_none_when_no_tool_calls(self, provider_cls, provider_kwargs):
        """format_assistant_turn must return None for plain-text responses."""
        provider = self._make_provider(provider_cls, provider_kwargs)
        result = provider.format_assistant_turn(_make_response_no_tool_calls())
        assert result is None, (
            f"{provider_cls.__name__}: expected None for no-tool-call response, got {result!r}"
        )

    def test_returns_dict_with_role_assistant_when_has_tool_calls(self, provider_cls, provider_kwargs):
        """format_assistant_turn must return a dict with role='assistant' when tool calls exist."""
        if provider_cls is GeminiProvider:
            pytest.skip("GeminiProvider intentionally returns None (tool call history not supported in this adapter)")
        provider = self._make_provider(provider_cls, provider_kwargs)
        result = provider.format_assistant_turn(_make_response_with_two_tool_calls())
        assert result is not None, (
            f"{provider_cls.__name__}: expected a message dict, got None"
        )
        assert isinstance(result, dict)
        assert result.get("role") == "assistant", (
            f"{provider_cls.__name__}: expected role='assistant', got {result.get('role')!r}"
        )

    def test_both_tool_calls_are_represented(self, provider_cls, provider_kwargs):
        """Both tool calls in the response must appear somewhere in the assistant turn."""
        if provider_cls is GeminiProvider:
            pytest.skip("GeminiProvider intentionally returns None (tool call history not supported in this adapter)")
        provider = self._make_provider(provider_cls, provider_kwargs)
        result = provider.format_assistant_turn(_make_response_with_two_tool_calls())
        assert result is not None
        result_str = str(result)
        assert "list_windows" in result_str, (
            f"{provider_cls.__name__}: 'list_windows' not found in assistant turn: {result!r}"
        )
        assert "get_system_info" in result_str, (
            f"{provider_cls.__name__}: 'get_system_info' not found in assistant turn: {result!r}"
        )


# ---------------------------------------------------------------------------
# Integration: verify loop inserts assistant turn before tool_result messages
# ---------------------------------------------------------------------------

class TestLoopInsertsAssistantTurnBeforeToolResults:
    """
    Simulate two iterations of the agent loop using OllamaProvider (previously
    broken) and verify that after the tool calls in iteration 1, the messages
    list contains [... user_msg, assistant_turn, tool_result_1, tool_result_2].
    """

    @pytest.mark.asyncio
    async def test_ollama_assistant_turn_inserted_in_history(self):
        from brain.agent.loop import AgentLoop
        from brain.agent.providers.base import ToolDefinition
        from brain.permissions.policy import PermissionEngine
        from unittest.mock import AsyncMock, MagicMock

        # Fake tool registry with two tools
        fake_registry_tools = [
            ToolDefinition("list_windows", "List windows", {"type": "object", "properties": {}, "required": []}),
        ]

        # Build a fake OllamaProvider
        provider = OllamaProvider(model="test")

        # Round 1: provider returns tool call
        tool_call_response = LLMResponse(
            text="",
            tool_calls=[ToolCall(call_id="call_0", tool_name="list_windows", arguments={})],
            raw={"message": {"tool_calls": []}},  # raw is a dict — the original bug
        )
        # Round 2: provider returns plain text (loop ends)
        final_response = LLMResponse(text='{"text":"Done","emotion":"neutral","animation":"wave","priority":"normal"}')

        call_count = 0

        captured_messages_history = []

        async def fake_complete(messages, tools=None, system_prompt=None):
            nonlocal call_count
            call_count += 1
            captured_messages_history.append(list(messages))
            if call_count == 1:
                return tool_call_response
            return final_response

        provider.complete = fake_complete  # type: ignore[assignment]

        # Fake permission engine (auto-approve everything)
        perms = MagicMock(spec=PermissionEngine)
        perms.check_and_gate = AsyncMock(return_value=True)

        # Fake tool registry
        from brain.tools import registry as tool_registry_module
        with patch.object(tool_registry_module, "get_tool_definitions", return_value=fake_registry_tools), \
             patch.object(tool_registry_module, "get_tool_risk", return_value="low"), \
             patch.object(tool_registry_module, "dispatch", new_callable=AsyncMock,
                         return_value=["Window A", "Window B"]):

            loop = AgentLoop(provider=provider, permission_engine=perms, system_prompt="You are a test assistant.")
            result = await loop.process(user_input="list open windows")

        assert result is not None
        assert result.text

        # Verify that in round 2, the message history sent to complete() contains:
        # [0]: user message
        # [1]: assistant turn with tool_calls (formatted by OllamaProvider)
        # [2]: tool result
        round_2_messages = captured_messages_history[1]
        assert len(round_2_messages) >= 3
        assistant_turn = round_2_messages[1]
        assert assistant_turn["role"] == "assistant"
        assert "tool_calls" in assistant_turn
        assert len(assistant_turn["tool_calls"]) == 1
        assert assistant_turn["tool_calls"][0]["function"]["name"] == "list_windows"
        tool_result = round_2_messages[2]
        assert tool_result["role"] == "tool"
