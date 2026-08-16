"""
brain/agent/providers/openai.py

OpenAI provider adapter (GPT-4o / GPT-4o-mini).
Uses the OpenAI Python SDK's native function/tool-calling API.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from openai import AsyncOpenAI

from .base import BaseLLMProvider, LLMResponse, ToolCall, ToolDefinition

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseLLMProvider):
    """Wraps OpenAI AsyncClient for use in the agent loop."""

    def __init__(self, model: str = "gpt-4o", api_key: str | None = None) -> None:
        self._model = model
        self._client = AsyncOpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY")
        )

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        openai_messages = []
        if system_prompt:
            openai_messages.append({"role": "system", "content": system_prompt})
        openai_messages.extend(messages)

        openai_tools = None
        if tools:
            openai_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": openai_messages,
        }
        if openai_tools:
            kwargs["tools"] = openai_tools

        logger.debug("Calling OpenAI API: model=%s, messages=%d", self._model, len(openai_messages))

        response = await self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message

        tool_calls: list[ToolCall] = []
        if message.tool_calls:
            for tc in message.tool_calls:
                args = {}
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except Exception:
                    pass
                tool_calls.append(ToolCall(
                    call_id=tc.id,
                    tool_name=tc.function.name,
                    arguments=args,
                ))

        return LLMResponse(text=message.content, tool_calls=tool_calls, raw=response)

    def format_tool_result(
        self,
        call_id: str,
        tool_name: str,
        result: Any,
        is_error: bool = False,
    ) -> dict[str, Any]:
        content = result if isinstance(result, str) else json.dumps(result)
        return {
            "role": "tool",
            "tool_call_id": call_id,
            "content": content,
        }

    def format_assistant_turn(self, response: LLMResponse) -> dict[str, Any] | None:
        """
        Build the OpenAI-format assistant message with tool_calls.
        OpenAI requires the assistant turn to include the tool_call descriptors
        before the corresponding 'tool' role messages with results.
        """
        if not response.tool_calls:
            return None
        tool_calls_payload = [
            {
                "id": tc.call_id,
                "type": "function",
                "function": {
                    "name": tc.tool_name,
                    "arguments": json.dumps(tc.arguments),
                },
            }
            for tc in response.tool_calls
        ]
        return {
            "role": "assistant",
            "content": response.text or None,
            "tool_calls": tool_calls_payload,
        }