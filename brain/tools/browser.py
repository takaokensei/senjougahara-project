"""
brain/tools/browser.py

Playwright browser automation tool.

Provides navigation, page interaction, text extraction, and screenshots.
Risk tiers:
  LOW:    Navigating to URLs, reading page text, inspecting links
  MEDIUM: Clicking buttons, filling forms
  HIGH:   Form submissions with payment/credentials keywords
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from brain.tools.registry import RISK_HIGH, RISK_LOW, RISK_MEDIUM, tool

logger = logging.getLogger(__name__)

_browser_instance: Any = None
_playwright_instance: Any = None
_page_instance: Any = None


async def _get_page():
    global _browser_instance, _playwright_instance, _page_instance
    if _page_instance is not None and not _page_instance.is_closed():
        return _page_instance

    from playwright.async_api import async_playwright
    if _playwright_instance is None:
        _playwright_instance = await async_playwright().start()
    if _browser_instance is None:
        _browser_instance = await _playwright_instance.chromium.launch(headless=False)
    _page_instance = await _browser_instance.new_page()
    return _page_instance


@tool(
    name="browser_navigate",
    description="Navigate the browser to a given URL. Opens the website in the system browser and extracts preview text.",
    risk=RISK_LOW,
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The URL to navigate to."},
        },
        "required": ["url"],
    },
)
async def browser_navigate(url: str) -> dict[str, str]:
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    import webbrowser
    webbrowser.open(url)

    try:
        page = await _get_page()
        logger.info("Browser navigating to %s", url)
        await page.goto(url, timeout=30000, wait_until="domcontentloaded")
        title = await page.title()
        content = await page.inner_text("body")
        preview = content[:2000] if content else ""
        return {"title": title, "url": page.url, "preview": preview}
    except Exception as exc:
        logger.warning("Playwright navigation error: %s. Opened in default browser.", exc)
        return {"title": "Opened in default browser", "url": url, "preview": f"Opened {url} in system web browser."}


@tool(
    name="browser_click",
    description="Click an element on the active browser page by text or CSS selector.",
    risk=RISK_MEDIUM,
    parameters={
        "type": "object",
        "properties": {
            "selector": {"type": "string", "description": "CSS selector or text selector to click."},
        },
        "required": ["selector"],
    },
)
async def browser_click(selector: str) -> str:
    page = await _get_page()
    logger.info("Browser clicking %s", selector)
    await page.click(selector, timeout=10000)
    return f"Clicked element '{selector}'."


@tool(
    name="browser_type",
    description="Type text into an input field on the active browser page.",
    risk=RISK_MEDIUM,
    parameters={
        "type": "object",
        "properties": {
            "selector": {"type": "string", "description": "CSS selector of the input field."},
            "text": {"type": "string", "description": "Text to enter."},
        },
        "required": ["selector", "text"],
    },
)
async def browser_type(selector: str, text: str) -> str:
    page = await _get_page()
    logger.info("Browser typing into %s", selector)
    await page.fill(selector, text, timeout=10000)
    return f"Entered text into '{selector}'."