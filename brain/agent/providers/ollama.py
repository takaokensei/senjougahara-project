"""
brain/agent/providers/ollama.py

Ollama local LLM provider adapter.
Supports local models (Llama 3, Mistral, Qwen, etc.).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .base import BaseLLMProvider, LLMResponse, ToolCall, ToolDefinition

logger = logging.getLogger(__name__)


class OllamaProvider(BaseLLMProvider):
    """Wraps Ollama AsyncClient for use in the agent loop."""

    def __init__(self, model: str = "llama3.2", host: str = "http://localhost:11434") -> None:
        self._model = model
        self._host = host

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        import ollama

        client = ollama.AsyncClient(host=self._host)

        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        formatted_messages.extend(messages)

        ollama_tools = None
        if tools:
            ollama_tools = [
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
            "messages": formatted_messages,
        }
        if ollama_tools:
            kwargs["tools"] = ollama_tools

        logger.debug("Calling Ollama: model=%s", self._model)
        response = await client.chat(**kwargs)
        message = response.get("message", {})

        tool_calls: list[ToolCall] = []
        if "tool_calls" in message and message["tool_calls"]:
            for i, tc in enumerate(message["tool_calls"]):
                fn = tc.get("function", {})
                tool_calls.append(ToolCall(
                    call_id=f"call_{i}",
                    tool_name=fn.get("name", ""),
                    arguments=fn.get("arguments", {}),
                ))
        elif message.get("content"):
            import re
            content = message["content"]
            for m in re.finditer(r"\{[\s\S]*?\}", content):
                try:
                    obj = json.loads(m.group(0))
                    if isinstance(obj, dict):
                        name = obj.get("name") or obj.get("function")
                        args = obj.get("arguments") or obj.get("parameters") or {}
                        if name and isinstance(name, str) and isinstance(args, dict) and "text" not in obj:
                            tool_calls.append(ToolCall(
                                call_id=f"call_{len(tool_calls)}",
                                tool_name=name,
                                arguments=args,
                            ))
                except Exception:
                    pass

        return LLMResponse(text=message.get("content"), tool_calls=tool_calls, raw=response)

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
            "content": content,
        }

    def format_assistant_turn(self, response: LLMResponse) -> dict[str, Any] | None:
        """
        Build the Ollama-compatible assistant message.
        Ollama's Python SDK validates Message.tool_calls.function.arguments as a dict (Mapping),
        unlike OpenAI SDK which expects a serialized JSON string.
        """
        if not response.tool_calls:
            return None
        tool_calls_payload = [
            {
                "id": tc.call_id,
                "type": "function",
                "function": {
                    "name": tc.tool_name,
                    "arguments": tc.arguments if isinstance(tc.arguments, dict) else {},
                },
            }
            for tc in response.tool_calls
        ]
        return {
            "role": "assistant",
            "content": response.text or "",
            "tool_calls": tool_calls_payload,
        }