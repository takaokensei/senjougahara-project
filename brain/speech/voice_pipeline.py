"""
brain/speech/voice_pipeline.py

Unified voice pipeline coordinating:
  1. Trigger (Hotkey / Wake Word / Bridge activate)
  2. State transition -> LISTENING
  3. Audio capture via AudioRecorder
  4. Transcription via STTEngine (faster-whisper)
  5. State transition -> THINKING
  6. Agent loop ReAct execution (LLM + Tools + Permissions + Memory)
  7. TTS synthesis via TTSAdapter (AivisSpeech / VOICEVOX)
  8. State transition -> SPEAKING
  9. Bridge speak command -> Avatar lip-sync and VRMA animation
  10. State transition -> IDLE
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from brain.agent.loop import AgentLoop
from brain.bridge.client import BridgeClient
from brain.speech.audio_capture import AudioRecorder
from brain.speech.hotkey import GlobalHotkeyListener
from brain.speech.stt import STTEngine
from brain.speech.tts import TTSAdapter
from brain.speech.wakeword import WakeWordDetector

logger = logging.getLogger(__name__)


class VoicePipeline:
    """Coordinates end-to-end voice interactions."""

    def __init__(
        self,
        agent: AgentLoop,
        bridge: BridgeClient,
        stt: STTEngine,
        tts: TTSAdapter,
        recorder: AudioRecorder | None = None,
        hotkey: GlobalHotkeyListener | None = None,
        wakeword: WakeWordDetector | None = None,
    ) -> None:
        self.agent = agent
        self.bridge = bridge
        self.stt = stt
        self.tts = tts
        self.recorder = recorder or AudioRecorder()
        self.hotkey = hotkey
        self.wakeword = wakeword
        self.conversation_history: list[dict[str, Any]] = []
        self._is_processing = False

    def start(self) -> None:
        """Start listening for activation triggers."""
        if self.hotkey:
            self.hotkey.callback = lambda: asyncio.create_task(self.handle_activation("hotkey"))
            self.hotkey.start()

        # Listen for bridge activation events (e.g. click from avatar)
        self.bridge.on("activate", lambda evt: asyncio.create_task(
            self.handle_activation(evt.get("source", "bridge"))
        ))
        logger.info("Voice pipeline started and listening for activation.")

    def stop(self) -> None:
        """Stop listening for triggers."""
        if self.hotkey:
            self.hotkey.stop()
        logger.info("Voice pipeline stopped.")

    async def handle_activation(self, source: str = "hotkey") -> None:
        """Execute a full voice interaction turn."""
        if self._is_processing:
            logger.info("Voice pipeline already busy processing turn. Ignoring trigger.")
            return

        self._is_processing = True
        logger.info("Voice pipeline activated via: %s", source)

        try:
            # 1. Notify avatar: LISTENING
            await self.bridge.set_state("LISTENING", reason=f"Activated by {source}")

            # 2. Record audio
            audio_bytes = await self.recorder.record_async(duration=4.5)
            if not audio_bytes:
                logger.warning("No audio recorded.")
                await self.bridge.set_state("IDLE")
                return

            # 3. Transcribe audio with STT
            user_text = await asyncio.to_thread(self.stt.transcribe_bytes, audio_bytes)
            if not user_text.strip():
                logger.info("STT returned empty transcript (silence). Returning to IDLE.")
                await self.bridge.set_state("IDLE")
                return

            logger.info("[VOICE INPUT] %s", user_text)

            # 4. Notify avatar: THINKING
            await self.bridge.set_state("THINKING", reason="Processing user utterance")

            # 5. Run agent loop
            structured = await self.agent.process(user_text, self.conversation_history)
            self.conversation_history.append({"role": "user", "content": user_text})
            self.conversation_history.append({"role": "assistant", "content": structured.text})
            if len(self.conversation_history) > 40:
                self.conversation_history[:] = self.conversation_history[-40:]

            logger.info("[AGENT RESPONSE] %s (emotion=%s, anim=%s)", structured.text[:80], structured.emotion.value, structured.animation)

            # 6. Synthesize TTS
            audio_result = None
            try:
                audio_result = await self.tts.speak(
                    text=structured.text,
                    emotion=structured.emotion.value,
                    animation=structured.animation,
                )
            except Exception as tts_exc:
                logger.warning("TTS synthesis failed: %s", tts_exc)

            # 7. Command Avatar to speak with lip-sync
            await self.bridge.speak(
                text=structured.text,
                emotion=structured.emotion.value,
                animation=structured.animation,
                audio_url=audio_result["audio_url"] if audio_result else None,
                priority=structured.priority.value,
            )

        except Exception as exc:
            logger.error("Voice pipeline error: %s", exc, exc_info=True)
            await self.bridge.send_error(str(exc))
            await self.bridge.set_state("ERROR")
        finally:
            self._is_processing = False