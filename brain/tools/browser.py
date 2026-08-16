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
_headless_browser_instance: Any = None
_playwright_instance: Any = None
_page_instance: Any = None


async def _get_playwright():
    global _playwright_instance
    if _playwright_instance is None:
        from playwright.async_api import async_playwright
        _playwright_instance = await async_playwright().start()
    return _playwright_instance


async def _get_page():
    global _browser_instance, _page_instance
    if _page_instance is not None and not _page_instance.is_closed():
        return _page_instance

    pw = await _get_playwright()
    if _browser_instance is None:
        _browser_instance = await pw.chromium.launch(headless=False)
    _page_instance = await _browser_instance.new_page()
    return _page_instance


async def _get_headless_browser():
    global _headless_browser_instance
    if _headless_browser_instance is None:
        pw = await _get_playwright()
        _headless_browser_instance = await pw.chromium.launch(headless=True)
    return _headless_browser_instance


@tool(
    name="quick_search",
    description=(
        "Perform a fast, invisible web search to retrieve concise factual information. "
        "Use this to answer factual questions (dates, definitions, events, concepts) without opening a visible browser window."
    ),
    risk=RISK_LOW,
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query (keywords or question).",
            },
        },
        "required": ["query"],
    },
)
async def quick_search(query: str) -> str:
    """Perform headless search via DuckDuckGo HTML and return a concise summary."""
    import urllib.parse

    logger.info("Performing quick search for: %s", query)
    page = None

    try:
        browser = await _get_headless_browser()
        page = await browser.new_page()

        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(query)}"
        # Aggressive 8s timeout to keep voice/chat pipeline snappy
        await asyncio.wait_for(
            page.goto(url, wait_until="domcontentloaded"),
            timeout=8.0,
        )

        results: list[str] = []
        bodies = await page.locator(".result__body").all()
        if bodies:
            for item in bodies[:3]:
                title_loc = item.locator(".result__title")
                snippet_loc = item.locator(".result__snippet")
                title = (await title_loc.inner_text()).strip() if await title_loc.count() > 0 else ""
                snippet = (await snippet_loc.inner_text()).strip() if await snippet_loc.count() > 0 else ""
                if title or snippet:
                    entry = f"{title}: {snippet}" if title and snippet else (title or snippet)
                    results.append(entry)

        if not results:
            # Fallback: inspect any .result elements
            raw_results = await page.locator(".result").all_inner_texts()
            for r in raw_results[:3]:
                cleaned = " ".join(r.split())
                if cleaned:
                    results.append(cleaned)

        if not results:
            body_text = await page.inner_text("body")
            summary = " ".join(body_text.split())[:400]
            return summary or "Nenhum resultado encontrado."

        combined = "\n".join(results)
        # Limit total response size to 450 characters
        if len(combined) > 450:
            combined = combined[:447] + "..."
        return combined

    except asyncio.TimeoutError:
        logger.warning("quick_search timed out for query: %s", query)
        return "A busca excedeu o tempo limite."
    except Exception as exc:
        logger.error("quick_search failed: %s", exc)
        return f"Não foi possível obter resultados para a busca: {exc}"
    finally:
        if page is not None:
            try:
                await page.close()
            except Exception:
                pass




@tool(
    name="browser_navigate",
    description="Open a website or navigate to a given URL in the user's web browser (e.g. 'https://youtube.com', 'https://google.com').",
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
    """Open the requested URL instantly in the user's default browser."""
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    import webbrowser
    await asyncio.to_thread(webbrowser.open, url)
    logger.info("Opened URL in default web browser: %s", url)
    return {"status": "success", "url": url, "message": f"Opened {url} in system web browser."}



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