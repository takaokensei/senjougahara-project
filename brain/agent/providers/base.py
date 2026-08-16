"""
brain/agent/providers/base.py

Base protocol / abstract class for LLM providers.
All providers must implement this interface so the agent loop
can swap them transparently via config.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ToolDefinition:
    """A tool the LLM may call."""
    def __init__(self, name: str, description: str, parameters: dict[str, Any]) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters  # JSON Schema object


class ToolCall:
    """A tool call emitted by the LLM."""
    def __init__(self, call_id: str, tool_name: str, arguments: dict[str, Any]) -> None:
        self.call_id = call_id
        self.tool_name = tool_name
        self.arguments = arguments


class LLMResponse:
    """
    Unified response shape returned by every provider.
    Either contains text (final response) or tool_calls (action requests).
    """
    def __init__(
        self,
        text: str | None = None,
        tool_calls: list[ToolCall] | None = None,
        raw: Any = None,
    ) -> None:
        self.text = text
        self.tool_calls: list[ToolCall] = tool_calls or []
        self.raw = raw  # original SDK response, useful for debugging

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class BaseLLMProvider(ABC):
    """Abstract base class for LLM provider adapters."""

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """
        Send a conversation to the LLM and return its response.

        Args:
            messages: List of {role, content} dicts in OpenAI message format.
                      Tool results must be pre-formatted per the provider's expectations.
            tools: Optional tool definitions available to the model.
            system_prompt: Optional system prompt (overrides any system message in messages).

        Returns:
            LLMResponse with either .text (final) or .tool_calls (action request).
        """
        ...

    @abstractmethod
    def format_tool_result(
        self,
        call_id: str,
        tool_name: str,
        result: Any,
        is_error: bool = False,
    ) -> dict[str, Any]:
        """
        Format a tool execution result as a message dict for the next completion call.
        Each provider uses slightly different shapes for tool result messages.
        """
        ...

    @abstractmethod
    def format_assistant_turn(self, response: "LLMResponse") -> dict[str, Any] | None:
        """
        Format the assistant's tool-use turn (text + tool_calls) as a message dict
        to append to conversation history, in this provider's expected shape.

        This must be appended to the messages list BEFORE the tool_result messages
        for the conversation history to be coherent. Return None if there are no
        tool calls to record (i.e., it was a plain text response with no tool use).

        Each provider implements this using its own native message format rather than
        inspecting response.raw (which has different shapes per SDK).
        """
        ...
