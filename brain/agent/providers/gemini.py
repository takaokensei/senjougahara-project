"""
brain/agent/providers/gemini.py

Google Gemini provider adapter.
Uses google-generativeai / google-genai SDK.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from .base import BaseLLMProvider, LLMResponse, ToolCall, ToolDefinition

logger = logging.getLogger(__name__)


class GeminiProvider(BaseLLMProvider):
    """Wraps Gemini client for use in the agent loop."""

    def __init__(self, model: str = "gemini-2.0-flash", api_key: str | None = None) -> None:
        self._model = model
        self._api_key = api_key or os.environ.get("GOOGLE_API_KEY")

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        import google.generativeai as genai

        genai.configure(api_key=self._api_key)
        model = genai.GenerativeModel(
            model_name=self._model,
            system_instruction=system_prompt,
        )

        contents = []
        for msg in messages:
            role = "user" if msg.get("role") in ("user", "tool") else "model"
            content = msg.get("content", "")
            if isinstance(content, str):
                contents.append({"role": role, "parts": [content]})

        response = await model.generate_content_async(contents)
        text = response.text if hasattr(response, "text") else ""

        return LLMResponse(text=text, tool_calls=[], raw=response)

    def format_tool_result(
        self,
        call_id: str,
        tool_name: str,
        result: Any,
        is_error: bool = False,
    ) -> dict[str, Any]:
        content = result if isinstance(result, str) else json.dumps(result)
        return {
            "role": "user",
            "content": f"[Tool Result for {tool_name}]: {content}",
        }