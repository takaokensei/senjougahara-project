"""
brain/main.py

Senjougahara Brain entrypoint.

Phase 1: Text-only mode.
  - GET  /health        -> {\"status\": \"ready\"} once startup completes
  - POST /chat          -> {\"message\": \"...\"} -> agent processes -> structured response
  - GET  /audio/<file>  -> serves generated TTS audio files

All endpoints are served by a single uvicorn instance on 127.0.0.1:8766
(bridge_port + 1) to avoid port conflicts.
"""

from __future__ import annotations

import asyncio
import logging
import logging.handlers
import signal
import sys
from pathlib import Path


def _configure_logging(log_dir: Path, level: str) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "brain.log"
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    fmt_short = logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
    fmt_full = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt_short)
    root.addHandler(console)
    fh = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    fh.setFormatter(fmt_full)
    root.addHandler(fh)


async def main() -> None:
    from brain.config import config

    _configure_logging(config.logs_dir, config.logging.level)
    logger = logging.getLogger("brain.main")
    logger.info("Starting Senjougahara brain (Phase 1)")

    # ── Imports ─────────────────────────────────────────────────────────────────
    import uvicorn
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from fastapi.staticfiles import StaticFiles

    from brain.personality.loader import load_profile
    from brain.startup.state_machine import StartupStateMachine

    # ── Startup sequence ─────────────────────────────────────────────────────────
    startup = StartupStateMachine(config=config, personality_loader=load_profile)
    success = await startup.run()
    if not success:
        logger.error("Startup failed: %s", startup.error_message)
        sys.exit(1)

    profile = startup.personality_profile
    logger.info("Personality: %s", profile.name if profile else "(none)")

    # ── Bridge client ────────────────────────────────────────────────────────────
    from brain.bridge.client import BridgeClient
    bridge = BridgeClient(host=config.bridge.host, port=config.bridge.port)
    await bridge.connect()

    # ── Permission engine ────────────────────────────────────────────────────────
    from brain.permissions.policy import PermissionEngine, load_policy_overrides
    policy_yaml = Path(__file__).parent / "permissions" / "policy.yaml"
    policy_overrides = load_policy_overrides(policy_yaml)

    async def confirmation_callback(request_id: str, tool_name: str, description: str) -> bool:
        return await bridge.request_confirmation(
            tool_name=tool_name, action_description=description, risk_tier="HIGH"
        )

    permission_engine = PermissionEngine(
        audit_log_path=config.appdata_dir / "logs" / "audit.jsonl",
        policy_overrides=policy_overrides,
        confirmation_callback=confirmation_callback,
    )

    # ── Agent loop ───────────────────────────────────────────────────────────────
    from brain.agent.loop import AgentLoop
    from brain.agent.providers.factory import create_llm_provider
    from brain.tools.registry import import_all_tools
    import_all_tools()

    provider = create_llm_provider(config.llm)
    system_prompt = (
        profile.build_system_prompt() if profile
        else 'Respond in JSON: {"text": "...", "emotion": "neutral", "animation": "idle", "priority": "normal"}'
    )
    agent = AgentLoop(
        provider=provider,
        permission_engine=permission_engine,
        system_prompt=system_prompt,
    )

    # ── TTS ──────────────────────────────────────────────────────────────────────
    from brain.speech.tts import TTSAdapter
    audio_cache_dir = config.appdata_dir / "audio_cache"
    audio_cache_dir.mkdir(parents=True, exist_ok=True)
    tts = TTSAdapter(
        engine_base_url=config.tts.engine_base_url,
        speaker_id=config.tts.speaker_id,
        speed=config.tts.speed,
        pitch=config.tts.pitch,
        audio_cache_dir=audio_cache_dir,
    )

    conversation_history: list[dict] = []

    # ── Bridge event handlers ────────────────────────────────────────────────────
    async def handle_activate(event: dict) -> None:
        logger.info("Activation: %s", event.get("source"))
        await bridge.set_state("LISTENING", reason="activation")

    bridge.on("activate", handle_activate)

    # ── FastAPI app (single server, single port) ─────────────────────────────────
    app = FastAPI(title="Senjougahara Brain", docs_url=None, redoc_url=None)

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ready", "error": None})

    @app.post("/chat")
    async def chat(request: Request) -> JSONResponse:
        body = await request.json()
        user_message = body.get("message", "").strip()
        if not user_message:
            return JSONResponse({"error": "message required"}, status_code=400)

        logger.info("[CHAT] > %s", user_message)
        await bridge.set_state("THINKING", reason="processing")

        try:
            structured = await agent.process(user_message, conversation_history)
            conversation_history.append({"role": "user", "content": user_message})
            conversation_history.append({"role": "assistant", "content": structured.text})
            # Keep history bounded to last 40 messages
            if len(conversation_history) > 40:
                conversation_history[:] = conversation_history[-40:]

            audio_result = None
            try:
                audio_result = await tts.speak(
                    text=structured.text,
                    emotion=structured.emotion.value,
                    animation=structured.animation,
                )
            except Exception as tts_exc:
                logger.warning("TTS failed (degraded mode): %s", tts_exc)

            await bridge.speak(
                text=structured.text,
                emotion=structured.emotion.value,
                animation=structured.animation,
                audio_url=audio_result["audio_url"] if audio_result else None,
                priority=structured.priority.value,
            )

            return JSONResponse({
                "text": structured.text,
                "emotion": structured.emotion.value,
                "animation": structured.animation,
                "priority": structured.priority.value,
                "audio_url": audio_result["audio_url"] if audio_result else None,
            })
        except Exception as exc:
            logger.error("Agent error: %s", exc, exc_info=True)
            await bridge.send_error(str(exc))
            await bridge.set_state("ERROR")
            return JSONResponse({"error": str(exc)}, status_code=500)

    # Serve generated audio files at /audio/*
    app.mount("/audio", StaticFiles(directory=str(audio_cache_dir)), name="audio")

    # ── Start server ─────────────────────────────────────────────────────────────
    api_port = config.bridge.port + 1  # default: 8766
    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=api_port, log_level="warning"
    ))

    await bridge.set_state("IDLE", reason="brain ready")
    logger.info(
        "READY. health=http://127.0.0.1:%d/health  chat=http://127.0.0.1:%d/chat",
        api_port, api_port,
    )

    # Graceful shutdown on Ctrl+C (Windows: only SIGINT is reliable)
    def _shutdown(signum, frame):
        logger.info("Shutdown (signal %d).", signum)
        server.should_exit = True

    signal.signal(signal.SIGINT, _shutdown)

    await server.serve()
    await bridge.disconnect()
    logger.info("Brain shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())