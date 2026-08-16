"""
brain/agent/providers/factory.py

Factory function to instantiate the configured LLM provider adapter.
Uses lazy imports so unused provider SDKs do not cause ModuleNotFoundError.
"""

from __future__ import annotations

import logging
from typing import Any

from .base import BaseLLMProvider

logger = logging.getLogger(__name__)


def create_llm_provider(llm_config: Any) -> BaseLLMProvider:
    provider = getattr(llm_config, "provider", "anthropic").lower()
    model = getattr(llm_config, "model", "")

    if provider == "anthropic":
        from .anthropic import AnthropicProvider
        return AnthropicProvider(model=model or "claude-sonnet-4-5")
    elif provider == "openai":
        from .openai import OpenAIProvider
        return OpenAIProvider(model=model or "gpt-4o")
    elif provider == "gemini":
        from .gemini import GeminiProvider
        return GeminiProvider(model=model or "gemini-2.0-flash")
    elif provider == "ollama":
        from .ollama import OllamaProvider
        base_url = getattr(llm_config, "ollama_base_url", "http://localhost:11434")
        return OllamaProvider(model=model or "llama3.2", host=base_url)
    else:
        logger.warning("Unknown provider '%s', falling back to Anthropic", provider)
        from .anthropic import AnthropicProvider
        return AnthropicProvider(model=model or "claude-sonnet-4-5")