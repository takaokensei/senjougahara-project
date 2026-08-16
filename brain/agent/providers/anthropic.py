"""
brain/agent/providers/anthropic.py

Anthropic Claude provider adapter.
Uses the Anthropic Python SDK's native tool-use API.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import anthropic

from .base import BaseLLMProvider, LLMResponse, ToolCall, ToolDefinition

logger = logging.getLogger(__name__)


class AnthropicProvider(BaseLLMProvider):
    """
    Wraps the Anthropic Python SDK for use in the agent loop.

    Converts the agent loop's generic message/tool formats into
    Anthropic's specific API shape and back.
    """

    def __init__(self, model: str = "claude-sonnet-4-5", api_key: str | None = None) -> None:
        self._model = model
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
        )

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """Call Claude with optional tool definitions and return a unified response."""

        # Convert generic tool definitions to Anthropic's tool schema format
        anthropic_tools: list[dict[str, Any]] = []
        if tools:
            anthropic_tools = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters,
                }
                for t in tools
            ]

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 4096,
            "messages": messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        logger.debug("Calling Anthropic API: model=%s, messages=%d", self._model, len(messages))

        response = await self._client.messages.create(**kwargs)

        # Parse response into unified LLMResponse
        tool_calls: list[ToolCall] = []
        text_parts: list[str] = []

        for block in response.content:
            if block.type == "tool_use":
                tool_calls.append(ToolCall(
                    call_id=block.id,
                    tool_name=block.name,
                    arguments=block.input if isinstance(block.input, dict) else {},
                ))
            elif block.type == "text":
                text_parts.append(block.text)

        text = "\n".join(text_parts) if text_parts else None
        return LLMResponse(text=text, tool_calls=tool_calls, raw=response)

    def format_tool_result(
        self,
        call_id: str,
        tool_name: str,
        result: Any,
        is_error: bool = False,
    ) -> dict[str, Any]:
        """
        Format a tool result as an Anthropic-style 'user' message containing
        a tool_result content block.
        """
        content = result if isinstance(result, str) else json.dumps(result)
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": call_id,
                    "content": content,
                    "is_error": is_error,
                }
            ],
        }
