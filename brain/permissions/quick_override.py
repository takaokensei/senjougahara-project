"""
brain/permissions/quick_override.py

Quick override utilities for entire action categories or individual tools.

Inspired by the quick-override pattern in vierisid/jarvis
(studied as architectural reference only, not code-copied; RSALv2 license).
Reimplemented independently in Python.
"""

from __future__ import annotations

import logging
from typing import Any

from brain.permissions.policy import NEVER_AUTO_APPROVE_TOOLS

logger = logging.getLogger(__name__)

CATEGORY_MAP: dict[str, list[str]] = {
    "desktop": [
        "launch_app",
        "focus_window",
        "list_windows",
        "type_text",
        "get_clipboard",
        "set_clipboard",
        "press_hotkey",
        "get_system_info",
    ],
    "filesystem": [
        "read_file",
        "write_file",
        "list_directory",
        "search_files",
    ],
    "terminal": [
        "run_command",
    ],
    "browser": [
        "open_url",
        "search_web",
        "click_element",
        "get_page_text",
    ],
    "screenshot": [
        "capture_screen",
    ],
}


def apply_quick_override(
    overrides: dict[str, str],
    action_or_category: str,
    allow: bool,
) -> dict[str, str]:
    """
    Idempotently apply an override for an entire action category or individual tool.

    - allow=True promotes overrideable tools to 'LOW' (auto-approve).
    - allow=False elevates tools to 'HIGH' (always confirm).
    - Tools in NEVER_AUTO_APPROVE_TOOLS are never downgraded below HIGH.
    """
    target_tier = "LOW" if allow else "HIGH"
    updated = dict(overrides)

    normalized = action_or_category.strip().lower()
    if normalized.endswith(".*"):
        normalized = normalized[:-2]

    # 1. If it matches a known category
    if normalized in CATEGORY_MAP:
        tools_in_cat = CATEGORY_MAP[normalized]
        for tool_name in tools_in_cat:
            if tool_name not in NEVER_AUTO_APPROVE_TOOLS:
                updated[tool_name] = target_tier
        # Record category-level key as well
        updated[normalized] = target_tier
        updated[f"{normalized}.*"] = target_tier
    else:
        # 2. Direct tool override
        tool_name = normalized
        if tool_name in NEVER_AUTO_APPROVE_TOOLS and allow:
            logger.warning("Tool '%s' is in NEVER_AUTO_APPROVE_TOOLS and cannot be auto-approved.", tool_name)
        else:
            updated[tool_name] = target_tier

    return updated
