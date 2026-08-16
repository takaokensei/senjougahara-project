"""
brain/agent/providers/factory.py

Factory function to instantiate the configured LLM provider adapter.
"""

from __future__ import annotations

import logging
from typing import Any

from .anthropic import AnthropicProvider
from .base import BaseLLMProvider
from .gemini import GeminiProvider
from .ollama import OllamaProvider
from .openai import OpenAIProvider

logger = logging.getLogger(__name__)


def create_llm_provider(llm_config: Any) -> BaseLLMProvider:
    provider = getattr(llm_config, "provider", "anthropic").lower()
    model = getattr(llm_config, "model", "")

    if provider == "anthropic":
        return AnthropicProvider(model=model or "claude-sonnet-4-5")
    elif provider == "openai":
        return OpenAIProvider(model=model or "gpt-4o")
    elif provider == "gemini":
        return GeminiProvider(model=model or "gemini-2.0-flash")
    elif provider == "ollama":
        base_url = getattr(llm_config, "ollama_base_url", "http://localhost:11434")
        return OllamaProvider(model=model or "llama3.2", host=base_url)
    else:
        logger.warning("Unknown provider '%s', falling back to Anthropic", provider)
        return AnthropicProvider(model=model or "claude-sonnet-4-5")