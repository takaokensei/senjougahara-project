"""
brain/agent/loop.py

ReAct-style tool-use agent loop.

Flow:
  1. Build messages list with system prompt and conversation history
  2. Call LLM provider
  3. If response has tool_calls: check permissions -> execute -> loop back
  4. When LLM produces final text: parse as StructuredResponse
  5. Caller sends to TTS + avatar bridge

Design decisions:
  - Max 8 tool-use iterations per turn to prevent infinite loops
  - Tool execution is sequential for safety/predictability
  - Structured output parsed from the FINAL text response only
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from brain.agent.providers.base import BaseLLMProvider, LLMResponse, ToolCall
from brain.agent.structured_output import StructuredResponse, parse_structured_response
from brain.permissions.policy import PermissionEngine
from brain.tools import registry

logger = logging.getLogger(__name__)

_MAX_TOOL_ITERATIONS = 8


class AgentLoop:
    """Main agent loop: receives user utterance, produces StructuredResponse."""

    def __init__(
        self,
        provider: BaseLLMProvider,
        permission_engine: PermissionEngine,
        system_prompt: str,
    ) -> None:
        self._provider = provider
        self._permissions = permission_engine
        self._system_prompt = system_prompt

    async def process(
        self,
        user_input: str,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> StructuredResponse:
        """
        Process a user message and return a structured response.
        conversation_history is mutated in-place (appended to).
        """
        messages = list(conversation_history or [])
        messages.append({"role": "user", "content": user_input})

        tool_definitions = registry.get_tool_definitions()

        for iteration in range(_MAX_TOOL_ITERATIONS):
            logger.debug("Agent iteration %d/%d", iteration + 1, _MAX_TOOL_ITERATIONS)

            response: LLMResponse = await self._provider.complete(
                messages=messages,
                tools=tool_definitions if tool_definitions else None,
                system_prompt=self._system_prompt,
            )

            if not response.has_tool_calls:
                text = response.text or ""
                logger.debug("Agent final response: %d chars", len(text))
                if text:
                    messages.append({"role": "assistant", "content": text})
                return parse_structured_response(text)

            # Execute tool calls sequentially
            tool_result_messages: list[dict[str, Any]] = []

            for tool_call in response.tool_calls:
                result = await self._execute_tool_call(tool_call)
                tool_result_msg = self._provider.format_tool_result(
                    call_id=tool_call.call_id,
                    tool_name=tool_call.tool_name,
                    result=result["result"],
                    is_error=result["is_error"],
                )
                tool_result_messages.append(tool_result_msg)

            # Append assistant tool-use turn
            if response.raw is not None and hasattr(response.raw, 'content'):
                assistant_content = []
                for block in response.raw.content:
                    if hasattr(block, 'type'):
                        if block.type == 'text':
                            assistant_content.append({"type": "text", "text": block.text})
                        elif block.type == 'tool_use':
                            assistant_content.append({
                                "type": "tool_use",
                                "id": block.id,
                                "name": block.name,
                                "input": block.input,
                            })
                if assistant_content:
                    messages.append({"role": "assistant", "content": assistant_content})

            messages.extend(tool_result_messages)

        logger.warning("Agent exceeded max tool iterations (%d).", _MAX_TOOL_ITERATIONS)
        return StructuredResponse(
            text="I seem to be going in circles. Could you rephrase that?",
            emotion="confused",
            animation="shrug",
        )

    async def _execute_tool_call(self, tool_call: ToolCall) -> dict[str, Any]:
        """Execute a single tool call after permission engine approval."""
        tool_name = tool_call.tool_name
        arguments = tool_call.arguments

        try:
            base_risk = registry.get_tool_risk(tool_name)
        except KeyError:
            logger.warning("Unknown tool requested by LLM: %s", tool_name)
            return {"result": f"Unknown tool: {tool_name}", "is_error": True}

        # Dynamic risk for terminal commands
        if tool_name == "run_command" and "command" in arguments:
            from brain.tools.terminal import classify_command_risk
            base_risk = classify_command_risk(arguments["command"])

        allowed = await self._permissions.check_and_gate(
            tool_name=tool_name,
            base_risk=base_risk,
            arguments=arguments,
        )

        if not allowed:
            return {
                "result": f"Action '{tool_name}' was denied (requires confirmation).",
                "is_error": True,
            }

        try:
            result = await registry.dispatch(tool_name, arguments)
            return {"result": result, "is_error": False}
        except Exception as exc:
            logger.error("Tool %s raised: %s", tool_name, exc)
            return {"result": f"Tool error: {exc}", "is_error": True}