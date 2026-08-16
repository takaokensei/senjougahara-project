"""
brain/tests/test_browser_quick_search.py

Unit tests for quick_search tool (headless fast search).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brain.tools.browser import quick_search


class TestQuickSearch:
    @pytest.mark.asyncio
    async def test_quick_search_success(self):
        """quick_search navigates to DuckDuckGo HTML and parses result bodies."""
        mock_page = MagicMock()
        mock_page.goto = AsyncMock()
        mock_page.close = AsyncMock()

        # Mock result elements
        mock_item1 = MagicMock()
        mock_title1 = MagicMock()
        mock_title1.inner_text = AsyncMock(return_value="Guerra do Vietnã")
        mock_title1.count = AsyncMock(return_value=1)
        mock_snippet1 = MagicMock()
        mock_snippet1.inner_text = AsyncMock(return_value="Conflito ocorrido entre 1955 e 1975 no sudeste asiático.")
        mock_snippet1.count = AsyncMock(return_value=1)
        mock_item1.locator.side_effect = lambda sel: mock_title1 if "title" in sel else mock_snippet1

        mock_locator = MagicMock()
        mock_locator.all = AsyncMock(return_value=[mock_item1])
        mock_page.locator.return_value = mock_locator

        mock_browser = MagicMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)

        with patch("brain.tools.browser._get_headless_browser", new_callable=AsyncMock, return_value=mock_browser):
            result = await quick_search("guerra do vietna")

        assert "Guerra do Vietnã" in result
        assert "1955 e 1975" in result
        assert len(result) <= 450
        mock_page.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_quick_search_timeout_handled_gracefully(self):
        """Timeout in goto does not raise unhandled exception to agent loop."""
        mock_page = MagicMock()

        async def slow_goto(*args, **kwargs):
            await asyncio.sleep(10.0)

        mock_page.goto = slow_goto
        mock_page.close = AsyncMock()

        mock_browser = MagicMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)

        with patch("brain.tools.browser._get_headless_browser", new_callable=AsyncMock, return_value=mock_browser):
            result = await quick_search("query timeout test")

        assert "tempo limite" in result.lower()
        mock_page.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_quick_search_exception_handled_gracefully(self):
        """General errors return friendly message without crashing."""
        mock_browser = MagicMock()
        mock_browser.new_page = AsyncMock(side_effect=RuntimeError("Playwright crashed"))

        with patch("brain.tools.browser._get_headless_browser", new_callable=AsyncMock, return_value=mock_browser):
            result = await quick_search("crash test")

        assert "Não foi possível obter resultados" in result
