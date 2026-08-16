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
import re
import time
from pathlib import Path
from typing import Any

from brain.agent.loop import AgentLoop
from brain.bridge.client import BridgeClient
from brain.speech.audio_capture import AudioRecorder
from brain.speech.hotkey import GlobalHotkeyListener
from brain.speech.stt import STTEngine
from brain.speech.tts import TTSAdapter
from brain.speech.wake_phrase import contains_wake_phrase, estimate_audio_duration_seconds
from brain.speech.wakeword import WakeWordDetector

logger = logging.getLogger(__name__)


class VoicePipeline:
    """Coordinates end-to-end voice interactions with acoustic echo suppression."""

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
        self._suppress_wakeword_until: float = 0.0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._wakeword_task: asyncio.Task | None = None
        self._stopped = False

    def start(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Start listening for activation triggers."""
        try:
            self._loop = loop or asyncio.get_running_loop()
        except RuntimeError:
            self._loop = asyncio.get_event_loop()

        self._stopped = False

        if self.hotkey:
            def _on_hotkey():
                if self._loop and self._loop.is_running():
                    asyncio.run_coroutine_threadsafe(self.handle_activation("hotkey"), self._loop)
                else:
                    asyncio.create_task(self.handle_activation("hotkey"))

            self.hotkey.callback = _on_hotkey
            self.hotkey.start()

        # Listen for bridge activation events (e.g. click on avatar)
        def _on_bridge_activate(evt: dict[str, Any]) -> None:
            source = evt.get("source", "bridge")
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(self.handle_activation(source), self._loop)
            else:
                asyncio.create_task(self.handle_activation(source))

        self.bridge.on("activate", _on_bridge_activate)

        # Continuous wake-word background task if enabled
        if self.wakeword:
            self._wakeword_task = asyncio.create_task(self._listen_wakeword())

        logger.info("Voice pipeline started and listening for activation.")

    def stop(self) -> None:
        """Stop listening for triggers."""
        self._stopped = True
        if self.hotkey:
            self.hotkey.stop()
        if self._wakeword_task and not self._wakeword_task.done():
            self._wakeword_task.cancel()
        logger.info("Voice pipeline stopped.")

    async def _listen_wakeword(self) -> None:
        """Continuous background wake-word listening loop."""
        try:
            import sounddevice as sd
            import numpy as np
            logger.info("Continuous wake-word detection started for: %s", self.wakeword.phrase)

            chunk_size = 1280  # 80ms at 16kHz
            loop = asyncio.get_running_loop()
            queue: asyncio.Queue[np.ndarray] = asyncio.Queue()

            def _audio_callback(indata, frames, time_info, status):
                now = time.monotonic()
                if not self._is_processing and not self._stopped and now >= self._suppress_wakeword_until:
                    loop.call_soon_threadsafe(queue.put_nowait, indata.copy())

            stream = sd.InputStream(
                samplerate=16000,
                channels=1,
                dtype="int16",
                blocksize=chunk_size,
                callback=_audio_callback,
            )
            with stream:
                while not self._stopped:
                    chunk = await queue.get()
                    now = time.monotonic()
                    if self._is_processing or now < self._suppress_wakeword_until:
                        continue
                    detected, name, score = await asyncio.to_thread(self.wakeword.process_frame, chunk)
                    if detected and not self._is_processing and time.monotonic() >= self._suppress_wakeword_until:
                        logger.info("Wake word '%s' detected (confidence: %.2f)!", name, score)
                        await self.handle_activation("wake_word")
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("Wake-word listener unavailable (%s). Continuing with hotkey only.", exc)

    async def handle_activation(self, source: str = "hotkey") -> None:
        """Execute a full voice interaction turn."""
        if self._is_processing:
            logger.info("Voice pipeline already busy processing turn. Ignoring trigger.")
            return

        self._is_processing = True
        logger.info("Voice pipeline activated via: %s", source)

        # Pre-emptively suppress any self-trigger during the full turn duration.
        # This is extended again with the actual audio duration once TTS is ready.
        self._suppress_wakeword_until = time.monotonic() + 6.0

        try:

            # 1. Notify avatar: LISTENING
            await self.bridge.set_state("LISTENING", reason=f"Activated by {source}")

            # 2. Record audio with VAD silence detection
            audio_bytes = await self.recorder.record_async()
            if not audio_bytes:
                logger.warning("No audio recorded from microphone.")
                await self.bridge.set_state("CONFUSED", reason="Microphone error / no audio")
                await asyncio.sleep(1.0)
                await self.bridge.set_state("IDLE")
                return

            # 3. Transcribe audio with STT
            user_text = await asyncio.to_thread(self.stt.transcribe_bytes, audio_bytes)
            if not user_text.strip():
                logger.info("STT returned empty transcript (silence). Returning to IDLE.")
                await self.bridge.set_state("CONFUSED", reason="Silence detected")
                await asyncio.sleep(1.0)
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
                logger.warning(
                    "TTS synthesis failed: %s. Echo suppression will use a short fixed 2s window "
                    "(no audio plays, so full heuristic estimate is unnecessary and would over-suppress).",
                    tts_exc,
                )
                # No audio will play — use a short fixed window so the voice pipeline stays
                # responsive while still preventing an immediate self-trigger on the caption.
                self._suppress_wakeword_until = time.monotonic() + 2.0

            # 7. Command Avatar to speak with lip-sync and subtitle caption
            wav_path = audio_result.get("wav_path") if audio_result else None
            if audio_result:
                audio_duration = estimate_audio_duration_seconds(structured.text, wav_path)
                # Suppress acoustic self-triggering during audio playback window (+ margin)
                self._suppress_wakeword_until = time.monotonic() + audio_duration + 0.6
                logger.debug(
                    "Acoustic echo suppression active for %.2fs (until +%.2fs)",
                    audio_duration,
                    audio_duration + 0.6,
                )
            else:
                logger.debug("Acoustic echo suppression active for fixed 2.0s (TTS unavailable)")


            caption_text = structured.portuguese_translation
            if not caption_text:
                m_cap = re.search(r"\(([^)]+)\)", structured.text)
                caption_text = m_cap.group(1).strip() if m_cap else structured.text

            await self.bridge.speak(
                text=structured.text,
                emotion=structured.emotion.value,
                animation=structured.animation,
                audio_url=audio_result["audio_url"] if audio_result else None,
                priority=structured.priority.value,
                caption=caption_text,
            )

            # 8. Local speaker playback fallback
            if wav_path and Path(wav_path).exists():
                try:
                    import winsound
                    winsound.PlaySound(str(wav_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
                except Exception as play_exc:
                    logger.debug("Voice pipeline audio playback error: %s", play_exc)

        except Exception as exc:
            logger.error("Voice pipeline error: %s", exc, exc_info=True)
            await self.bridge.send_error(str(exc))
            await self.bridge.set_state("ERROR")
        finally:
            self._is_processing = False