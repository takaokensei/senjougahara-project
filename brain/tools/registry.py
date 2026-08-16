"""
brain/tools/registry.py

Tool registration and dispatch system.

Tools are registered via the @tool() decorator. The registry exposes:
  - A list of ToolDefinition objects for the LLM (what it can call)
  - A dispatch function that executes a tool call by name
  - Risk tier metadata for the permission engine

The LLM proposes tool calls; the permission engine decides whether to execute them.
Risk tiers are defined at registration time by the tool author, not by the LLM.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
from typing import Any, Callable

from brain.agent.providers.base import ToolDefinition

logger = logging.getLogger(__name__)


# Risk tier constants — these are the only valid values
RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"


class RegisteredTool:
    """Metadata + callable for a registered tool."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        risk: str,
        fn: Callable,
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters
        self.risk = risk
        self.fn = fn

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
        )


# Global registry — populated by @tool() decorators at import time
_REGISTRY: dict[str, RegisteredTool] = {}


def tool(
    name: str | None = None,
    description: str = "",
    risk: str = RISK_LOW,
    parameters: dict[str, Any] | None = None,
) -> Callable:
    """
    Decorator that registers a function as a callable tool.

    Args:
        name: Tool name exposed to the LLM (defaults to function name).
        description: Description shown to the LLM (used for tool selection).
        risk: Risk tier — LOW | MEDIUM | HIGH. Determines permission-engine behavior.
        parameters: JSON Schema for the tool's arguments. If None, inferred as empty.

    Usage:
        @tool(name="launch_app", description="Launch an application by name.", risk=RISK_LOW,
              parameters={"type": "object", "properties": {"app_name": {"type": "string"}},
                          "required": ["app_name"]})
        async def launch_app(app_name: str) -> str:
            ...
    """
    def decorator(fn: Callable) -> Callable:
        tool_name = name or fn.__name__
        tool_params = parameters or {
            "type": "object",
            "properties": {},
            "required": [],
        }

        registered = RegisteredTool(
            name=tool_name,
            description=description or inspect.getdoc(fn) or "",
            parameters=tool_params,
            risk=risk,
            fn=fn,
        )
        _REGISTRY[tool_name] = registered
        logger.debug("Registered tool: %s (risk=%s)", tool_name, risk)

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if inspect.iscoroutinefunction(fn):
                return await fn(*args, **kwargs)
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def get_all_tools() -> list[RegisteredTool]:
    """Return all registered tools."""
    return list(_REGISTRY.values())


def get_tool_definitions() -> list[ToolDefinition]:
    """Return tool definitions suitable for passing to the LLM provider."""
    return [t.definition for t in _REGISTRY.values()]


def get_tool_risk(tool_name: str) -> str:
    """Return the risk tier of a named tool. Raises KeyError if not found."""
    return _REGISTRY[tool_name].risk


async def dispatch(tool_name: str, arguments: dict[str, Any]) -> Any:
    """
    Execute a registered tool by name.
    The permission engine must approve the call BEFORE this is invoked.

    Returns the tool's return value, or raises on error.
    """
    if tool_name not in _REGISTRY:
        raise ValueError(f"Unknown tool: {tool_name!r}")

    registered = _REGISTRY[tool_name]
    logger.info("Dispatching tool: %s args=%r", tool_name, arguments)

    try:
        if inspect.iscoroutinefunction(registered.fn):
            return await registered.fn(**arguments)
        return registered.fn(**arguments)
    except Exception as exc:
        logger.error("Tool %s raised an error: %s", tool_name, exc, exc_info=True)
        raise


def import_all_tools() -> None:
    """
    Eagerly import all tool modules so their @tool() decorators run
    and populate the registry before the agent loop starts.
    """
    import brain.tools.desktop_control  # noqa: F401
    import brain.tools.filesystem       # noqa: F401
    import brain.tools.terminal         # noqa: F401
    try:
        import brain.tools.browser      # noqa: F401
    except ImportError as e:
        logger.debug("Browser tools not loaded: %s", e)
    try:
        import brain.tools.screenshot   # noqa: F401
    except ImportError as e:
        logger.debug("Screenshot tools not loaded: %s", e)
    logger.debug("All tools imported. Registry size: %d", len(_REGISTRY))