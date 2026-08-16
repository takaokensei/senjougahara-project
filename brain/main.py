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
import os
import signal
import sys
from pathlib import Path

# Silence Hugging Face Windows symlink warnings
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"


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

    # ── Permission & Emergency Engine ────────────────────────────────────────────
    from brain.comms.telegram_approval import TelegramApprovalChannel
    from brain.permissions.emergency import EmergencyController
    from brain.permissions.learning import AuthorityLearner
    from brain.permissions.policy import PermissionEngine, load_policy_overrides
    policy_yaml = Path(__file__).parent / "permissions" / "policy.yaml"
    policy_overrides = load_policy_overrides(policy_yaml)

    telegram_channel = TelegramApprovalChannel(
        bot_token=config.telegram.bot_token,
        chat_id=config.telegram.chat_id,
        enabled=config.telegram.enabled,
    )

    async def confirmation_callback(request_id: str, tool_name: str, description: str) -> bool:
        local_task = asyncio.create_task(
            bridge.request_confirmation(
                tool_name=tool_name, action_description=description, risk_tier="HIGH"
            )
        )
        telegram_task = None
        if telegram_channel.is_active:
            await telegram_channel.send_approval_request(
                request_id=request_id, tool_name=tool_name, risk_tier="HIGH", action_description=description
            )
            telegram_task = asyncio.create_task(
                telegram_channel.poll_for_decision(request_id=request_id, timeout_s=30.0)
            )

        if telegram_task is None:
            return await local_task

        done, pending = await asyncio.wait(
            [local_task, telegram_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

        for task in done:
            res = task.result()
            if res is not None:
                return res
        return False

    emergency_controller = EmergencyController()
    authority_learner = AuthorityLearner(db_path=config.appdata_dir / "memory.db")

    permission_engine = PermissionEngine(
        audit_log_path=config.appdata_dir / "logs" / "audit.jsonl",
        policy_overrides=policy_overrides,
        confirmation_callback=confirmation_callback,
        authority_learner=authority_learner,
    )

    # ── Agent loop ───────────────────────────────────────────────────────────────
    from brain.agent.loop import AgentLoop
    from brain.agent.providers.factory import create_llm_provider
    from brain.personality.learner import PersonalityModel
    from brain.tools.registry import import_all_tools
    import_all_tools()

    personality_model = PersonalityModel(db_path=config.appdata_dir / "memory.db")
    provider = create_llm_provider(config.llm)
    system_prompt = (
        profile.build_system_prompt() if profile
        else 'Respond in JSON: {"text": "...", "emotion": "neutral", "animation": "idle", "priority": "normal"}'
    )
    agent = AgentLoop(
        provider=provider,
        permission_engine=permission_engine,
        system_prompt=system_prompt,
        emergency_controller=emergency_controller,
        personality_model=personality_model,
    )

    # ── Memory (Optional fact extractor) ─────────────────────────────────────────
    fact_memory = None
    fact_extractor = None
    if config.memory.enabled:
        from brain.memory.extractor import FactExtractor
        from brain.memory.facts import FactMemory
        fact_memory = FactMemory(db_path=config.appdata_dir / "memory.db")
        fact_extractor = FactExtractor(provider=provider)

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

    # ── Voice Pipeline (Primary Hands-Free Voice Interface) ──────────────────────
    from brain.speech.audio_capture import AudioRecorder
    from brain.speech.hotkey import GlobalHotkeyListener
    from brain.speech.stt import STTEngine
    from brain.speech.voice_pipeline import VoicePipeline
    from brain.speech.wakeword import WakeWordDetector

    stt_engine = None
    if config.stt.enabled:
        stt_engine = STTEngine(
            model_size=config.stt.model_size,
            device=config.stt.device,
            compute_type=config.stt.compute_type,
            language=config.stt.language,
        )
        # Preload weights into RAM in background so first voice interaction has zero latency
        asyncio.create_task(asyncio.to_thread(stt_engine.load_model))

    hotkey_listener = None
    if config.hotkey.enabled:
        hotkey_listener = GlobalHotkeyListener(key=config.hotkey.key)

    wakeword_detector = None
    if config.wake_word.enabled:
        wakeword_detector = WakeWordDetector(
            phrase=config.wake_word.phrase,
            custom_model_path=config.wake_word.custom_model_path,
        )

    recorder = AudioRecorder()

    voice_pipeline = VoicePipeline(
        agent=agent,
        bridge=bridge,
        stt=stt_engine,
        tts=tts,
        recorder=recorder,
        hotkey=hotkey_listener,
        wakeword=wakeword_detector,
    )
    voice_pipeline.start()

    conversation_history = voice_pipeline.conversation_history

    # ── FastAPI app (single server, single port) ─────────────────────────────────
    app = FastAPI(title="Senjougahara Brain", docs_url=None, redoc_url=None)

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({
            "status": "ready",
            "voice_enabled": config.stt.enabled,
            "hotkey": config.hotkey.key if config.hotkey.enabled else None,
            "wake_word": config.wake_word.phrase if config.wake_word.enabled else None,
            "emergency": emergency_controller.status,
            "error": None,
        })

    @app.post("/emergency/pause")
    async def emergency_pause(request: Request) -> JSONResponse:
        body = await request.json() if request.headers.get("content-type") == "application/json" else {}
        reason = body.get("reason", "Manual emergency pause")
        emergency_controller.pause(reason)
        return JSONResponse({"status": "ok", "emergency": emergency_controller.status})

    @app.post("/emergency/resume")
    async def emergency_resume() -> JSONResponse:
        ok = emergency_controller.resume()
        return JSONResponse({
            "status": "ok" if ok else "failed",
            "emergency": emergency_controller.status,
        }, status_code=200 if ok else 400)

    @app.post("/emergency/kill")
    async def emergency_kill(request: Request) -> JSONResponse:
        body = await request.json() if request.headers.get("content-type") == "application/json" else {}
        reason = body.get("reason", "Kill switch engaged")
        emergency_controller.kill(reason)
        return JSONResponse({"status": "ok", "emergency": emergency_controller.status})

    @app.post("/emergency/reset")
    async def emergency_reset() -> JSONResponse:
        emergency_controller.reset()
        return JSONResponse({"status": "ok", "emergency": emergency_controller.status})

    @app.get("/permissions/suggestions")
    async def get_permission_suggestions() -> JSONResponse:
        suggestions = await authority_learner.get_pending_suggestions()
        return JSONResponse({"suggestions": suggestions})

    @app.post("/permissions/suggestions/{pattern_id}/accept")
    async def accept_permission_suggestion(pattern_id: int) -> JSONResponse:
        pattern = await authority_learner.get_pattern(pattern_id)
        if not pattern:
            return JSONResponse({"error": "Pattern not found"}, status_code=404)
        tool_name = pattern["tool_name"]
        permission_engine._policy_overrides[tool_name] = "LOW"
        await authority_learner.mark_suggestion_sent(pattern_id)
        return JSONResponse({"status": "promoted", "tool_name": tool_name, "new_tier": "LOW"})

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
        "READY. Voice Pipeline active (Hotkey: '%s' | Wake word: %s). health=http://127.0.0.1:%d/health",
        config.hotkey.key if config.hotkey.enabled else "disabled",
        config.wake_word.phrase if config.wake_word.enabled else "disabled",
        api_port,
    )

    # Graceful shutdown on Ctrl+C (Windows: only SIGINT is reliable)
    def _shutdown(signum, frame):
        logger.info("Shutdown (signal %d).", signum)
        server.should_exit = True

    signal.signal(signal.SIGINT, _shutdown)

    await server.serve()
    voice_pipeline.stop()
    await bridge.disconnect()
    logger.info("Brain shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())