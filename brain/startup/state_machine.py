"""
brain/startup/state_machine.py

Brain startup state machine.

States (in order):
  INITIALIZING -> CHECKING_LLM_PROVIDER -> CHECKING_TTS -> CHECKING_DESKTOP_BRIDGE
  -> LOADING_PERSONALITY -> READY | ERROR

Each state performs a health check or loading step.
On success, advances to the next state.
On failure, transitions to ERROR with a descriptive message.

Once READY, exposes a simple /health REST endpoint via FastAPI
so the launcher knows when to start the avatar.
"""

from __future__ import annotations

import asyncio
import logging
import os
from enum import Enum, auto
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class StartupState(str, Enum):
    INITIALIZING = "INITIALIZING"
    CHECKING_LLM_PROVIDER = "CHECKING_LLM_PROVIDER"
    CHECKING_TTS = "CHECKING_TTS"
    CHECKING_DESKTOP_BRIDGE = "CHECKING_DESKTOP_BRIDGE"
    LOADING_PERSONALITY = "LOADING_PERSONALITY"
    READY = "READY"
    ERROR = "ERROR"


class StartupStateMachine:
    """
    Runs the brain startup sequence and tracks the current state.
    """

    def __init__(self, config: Any, personality_loader: Any) -> None:
        self._config = config
        self._personality_loader = personality_loader
        self.state = StartupState.INITIALIZING
        self.error_message: str | None = None
        self.personality_profile: Any | None = None

    async def run(self) -> bool:
        """
        Run the full startup sequence.
        Returns True on success (READY), False on failure (ERROR).
        """
        steps = [
            (StartupState.CHECKING_LLM_PROVIDER, self._check_llm_provider),
            (StartupState.CHECKING_TTS, self._check_tts),
            (StartupState.CHECKING_DESKTOP_BRIDGE, self._check_desktop_bridge),
            (StartupState.LOADING_PERSONALITY, self._load_personality),
        ]

        for state, step_fn in steps:
            self.state = state
            logger.info("Startup: %s...", state.value)
            try:
                await step_fn()
            except Exception as exc:
                self.state = StartupState.ERROR
                self.error_message = f"{state.value} failed: {exc}"
                logger.error("Startup failed at %s: %s", state.value, exc)
                return False

        self.state = StartupState.READY
        logger.info("Startup: READY")
        return True

    # ------------------------------------------------------------------
    # Individual startup steps
    # ------------------------------------------------------------------

    async def _check_llm_provider(self) -> None:
        """Verify the configured LLM provider is reachable / has a valid key."""
        provider = self._config.llm.provider

        if provider == "anthropic":
            import os
            key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not key:
                raise EnvironmentError(
                    "ANTHROPIC_API_KEY is not set. Add it to your .env file."
                )
            # Light check: just verify the key is non-empty (actual API call happens in loop)
            logger.info("LLM provider: Anthropic (key present)")

        elif provider == "ollama":
            base_url = self._config.llm.ollama_base_url
            model_name = self._config.llm.model
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{base_url}/api/version")
                resp.raise_for_status()

                # Check if the configured model is installed
                try:
                    tags_resp = await client.get(f"{base_url}/api/tags")
                    if tags_resp.status_code == 200:
                        data = tags_resp.json()
                        installed = [m.get("name", "") for m in data.get("models", [])]
                        # Match exact name or name without tag (e.g. 'qwen2.5:7b' or 'qwen2.5')
                        model_base = model_name.split(":")[0]
                        matched = any(
                            m == model_name or m.startswith(f"{model_name}:") or m.split(":")[0] == model_base
                            for m in installed
                        )
                        if not matched:
                            avail_str = ", ".join(installed) if installed else "(none)"
                            raise ValueError(
                                f"Ollama model '{model_name}' not found locally. "
                                f"Available models: {avail_str}. "
                                f"Run 'ollama pull {model_name}' or set model in config/config.yaml."
                            )
                except ValueError:
                    raise
                except Exception as exc:
                    logger.debug("Could not verify Ollama models list: %s", exc)

            logger.info("LLM provider: Ollama at %s (model: %s)", base_url, model_name)


        elif provider == "openai":
            key = os.environ.get("OPENAI_API_KEY", "")
            if not key:
                raise EnvironmentError("OPENAI_API_KEY is not set.")
            logger.info("LLM provider: OpenAI (key present)")

        elif provider == "gemini":
            key = os.environ.get("GOOGLE_API_KEY", "")
            if not key:
                raise EnvironmentError("GOOGLE_API_KEY is not set.")
            logger.info("LLM provider: Google Gemini (key present)")

        else:
            raise ValueError(f"Unknown LLM provider: {provider!r}")

    async def _check_tts(self) -> None:
        """Verify the TTS engine HTTP API is reachable."""
        base_url = self._config.tts.engine_base_url
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{base_url}/version")
                # AivisSpeech/VOICEVOX return 200 on /version
                if resp.status_code == 200:
                    logger.info("TTS engine reachable at %s", base_url)
                    return
        except Exception as exc:
            logger.warning(
                "TTS engine not reachable at %s: %s. Continuing in TTS-degraded mode.",
                base_url, exc
            )
            # TTS unavailability is a WARNING, not a FATAL error in Phase 1
            # The brain can still process text requests

    async def _check_desktop_bridge(self) -> None:
        """
        Check if the avatar bridge server is reachable.
        This is a soft check — the avatar may not be running yet (launcher starts it after brain is READY).
        """
        logger.info(
            "Desktop bridge check: bridge client will connect once avatar starts on port %d",
            self._config.bridge.port,
        )
        # The actual WS connection is established by the BridgeClient after READY

    async def _load_personality(self) -> None:
        """Load the active personality profile."""
        profile_name = self._config.personality.active_profile
        self.personality_profile = self._personality_loader(profile_name)
        logger.info("Personality loaded: %s", profile_name)


def make_health_app(state_machine: StartupStateMachine) -> FastAPI:
    """
    Create a minimal FastAPI app that exposes GET /health.
    The launcher polls this endpoint until it returns {"status": "ready"}.
    """
    app = FastAPI(title="Senjougahara Brain Health", docs_url=None, redoc_url=None)

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({
            "status": state_machine.state.value.lower(),
            "error": state_machine.error_message,
        })

    return app