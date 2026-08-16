"""
brain/main.py

Senjougahara Brain entrypoint.

Phase 1: Text-only mode.
  - POST /chat with {"message": "..."} -> agent processes -> structured response
  - GET /health -> {"status": "ready"} once startup completes
  - Audio files served at http://127.0.0.1:8766/audio/
"""

from __future__ import annotations

import asyncio
import logging
import logging.handlers
import os
import signal
import sys
from pathlib import Path


_AUDIO_SERVE_PORT = 8766


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

    from brain.personality.loader import load_profile
    from brain.startup.state_machine import StartupStateMachine, make_health_app
    import uvicorn

    startup = StartupStateMachine(config=config, personality_loader=load_profile)

    # Health server on bridge_port + 1 (e.g., 8766)
    health_port = config.bridge.port + 1
    health_app = make_health_app(startup)
    health_server = uvicorn.Server(uvicorn.Config(
        health_app, host="127.0.0.1", port=health_port, log_level="warning"
    ))
    health_task = asyncio.create_task(health_server.serve())

    success = await startup.run()
    if not success:
        logger.error("Startup failed: %s", startup.error_message)
        health_task.cancel()
        sys.exit(1)

    profile = startup.personality_profile
    logger.info("Personality: %s", profile.name if profile else "(none)")

    # Bridge client
    from brain.bridge.client import BridgeClient
    bridge = BridgeClient(host=config.bridge.host, port=config.bridge.port)
    await bridge.connect()

    # Permission engine
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

    # Agent loop
    from brain.agent.loop import AgentLoop
    from brain.agent.providers.anthropic import AnthropicProvider
    from brain.tools.registry import import_all_tools
    import_all_tools()

    provider = AnthropicProvider(model=config.llm.model)
    system_prompt = (
        profile.build_system_prompt() if profile
        else 'Respond in JSON: {"text": "...", "emotion": "neutral", "animation": "idle", "priority": "normal"}'
    )
    agent = AgentLoop(
        provider=provider,
        permission_engine=permission_engine,
        system_prompt=system_prompt,
    )

    # TTS
    from brain.speech.tts import TTSAdapter
    tts = TTSAdapter(
        engine_base_url=config.tts.engine_base_url,
        speaker_id=config.tts.speaker_id,
        speed=config.tts.speed,
        pitch=config.tts.pitch,
        audio_cache_dir=config.appdata_dir / "audio_cache",
    )

    conversation_history: list[dict] = []

    # Bridge activation handler
    async def handle_activate(event: dict) -> None:
        logger.info("Activation: %s", event.get("source"))
        await bridge.set_state("LISTENING", reason="activation")

    bridge.on("activate", handle_activate)

    # Chat REST endpoint
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from fastapi.staticfiles import StaticFiles

    chat_app = FastAPI(title="Senjougahara Chat", docs_url=None, redoc_url=None)

    @chat_app.post("/chat")
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
            # Keep history bounded
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
                logger.warning("TTS failed: %s", tts_exc)

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

    # Audio file server
    audio_cache_dir = config.appdata_dir / "audio_cache"
    audio_cache_dir.mkdir(parents=True, exist_ok=True)
    audio_app = FastAPI(docs_url=None, redoc_url=None)
    audio_app.mount("/audio", StaticFiles(directory=str(audio_cache_dir)), name="audio")

    chat_port = config.bridge.port + 2   # 8767
    chat_server = uvicorn.Server(uvicorn.Config(
        chat_app, host="127.0.0.1", port=chat_port, log_level="warning"
    ))
    audio_server = uvicorn.Server(uvicorn.Config(
        audio_app, host="127.0.0.1", port=_AUDIO_SERVE_PORT, log_level="warning"
    ))

    await bridge.set_state("IDLE", reason="brain ready")
    logger.info("READY. Chat: http://127.0.0.1:%d/chat | Health: http://127.0.0.1:%d/health", chat_port, health_port)

    stop_event = asyncio.Event()

    def _shutdown(signum, frame):
        logger.info("Signal %d received. Shutting down.", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    await asyncio.gather(
        chat_server.serve(),
        audio_server.serve(),
        stop_event.wait(),
    )
    await bridge.disconnect()
    logger.info("Brain shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())