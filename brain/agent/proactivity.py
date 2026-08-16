"""
brain/agent/proactivity.py

Proactive observation and spontaneous commentary engine.
Monitors foreground window stability, user context and memory, and triggers
infrequent, high-relevance observations without user prompt.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from brain.agent.loop import AgentLoop
from brain.agent.providers.base import BaseLLMProvider
from brain.bridge.client import BridgeClient
from brain.config import ProactivityConfig
from brain.memory.facts import FactMemory
from brain.tools.window_awareness import (
    WindowInfo,
    get_foreground_window_info,
    is_likely_fullscreen_content,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure heuristic filter functions (isolated and testable)
# ---------------------------------------------------------------------------

def is_window_stable(
    current_key: str,
    last_key: str | None,
    stable_since: float,
    now: float,
    min_stable_sec: float,
) -> bool:
    """True if the same foreground window has stayed focused for at least min_stable_sec."""
    if last_key is None or current_key != last_key:
        return False
    return (now - stable_since) >= min_stable_sec


def is_cooldown_active(
    last_comment_ts: float,
    now: float,
    min_cooldown_sec: float,
) -> bool:
    """True if not enough time has passed since the last spontaneous comment."""
    if last_comment_ts <= 0:
        return False
    return (now - last_comment_ts) < min_cooldown_sec


def is_process_blocked(
    process_name: str,
    title: str,
    blocked_list: list[str],
    is_fullscreen: bool,
) -> bool:
    """
    True if the foreground process is in the blocklist, is running in fullscreen,
    or belongs to Windows desktop/shell components.
    """
    if is_fullscreen:
        return True

    clean_proc = (process_name or "").strip().lower()
    blocked_lower = {b.strip().lower() for b in blocked_list if b.strip()}
    if clean_proc in blocked_lower:
        return True

    # Windows shell noise
    shell_titles = {"", "progman", "task switching", "windows input experience", "start"}
    if (title or "").strip().lower() in shell_titles:
        return True

    return False


def is_repeated_comment(
    window_key: str,
    history: dict[str, float],
    now: float,
    repeat_window_sec: float,
) -> bool:
    """True if a comment was already made on the same window within repeat_window_sec."""
    if window_key not in history:
        return False
    return (now - history[window_key]) < repeat_window_sec


# ---------------------------------------------------------------------------
# Lightweight Triaging
# ---------------------------------------------------------------------------

async def should_comment(
    window_info: WindowInfo,
    known_facts_summary: str,
    provider: BaseLLMProvider,
) -> str | None:
    """
    Lightweight triage call to decide if a spontaneous observation is warranted.
    Returns the suggested comment text or None if silence is preferred.
    """
    prompt = (
        f"O usuário está com a janela '{window_info.title}' ({window_info.process_name}) em foco há algum tempo. "
        f"Baseado no que se sabe sobre ele: {known_facts_summary or 'Nenhum fato específico registrado.'}\n"
        "Vale a pena fazer um comentário breve e não intrusivo sobre isso agora? "
        "Se não, responda apenas NO. Se sim, responda apenas o comentário em uma frase curta, em português, sem formatação."
    )

    try:
        response = await provider.complete(
            messages=[{"role": "user", "content": prompt}],
            tools=None,
            system_prompt=None,
        )
        text = (response.text or "").strip()
        if not text:
            return None

        # Check if the model explicitly declined
        upper = text.upper()
        if upper == "NO" or upper.startswith("NO.") or upper.startswith("NO,") or upper == "NÃO":
            return None

        return text
    except Exception as exc:
        logger.debug("Proactivity triage check failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Observer Class
# ---------------------------------------------------------------------------

class ProactivityObserver:
    """
    Background observer that monitors window activity and triggers proactive comments.
    """

    def __init__(
        self,
        config: ProactivityConfig,
        agent: AgentLoop,
        bridge: BridgeClient,
        provider: BaseLLMProvider,
        fact_memory: FactMemory | None = None,
        time_provider: Callable[[], float] = time.time,
    ) -> None:
        self._config = config
        self._agent = agent
        self._bridge = bridge
        self._provider = provider
        self._fact_memory = fact_memory
        self._time_provider = time_provider

        self._last_window_key: str | None = None
        self._window_stable_since: float = 0.0
        self._last_comment_time: float = 0.0
        self._comment_history: dict[str, float] = {}
        self._last_purge_time: float = 0.0

        self._task: asyncio.Task | None = None
        self._running: bool = False

    async def tick(self) -> None:
        """Run a single evaluation cycle."""
        now = self._time_provider()

        # 0. Periodic purge of expired facts in background (every 10 minutes)
        if self._fact_memory is not None and (now - self._last_purge_time > 600.0):
            try:
                await self._fact_memory.purge_expired()
            except Exception as exc:
                logger.debug("Failed purging expired facts in proactivity loop: %s", exc)
            self._last_purge_time = now

        # 1. Inspect foreground window
        win_info = get_foreground_window_info()
        if win_info is None or not win_info.title.strip():
            self._last_window_key = None
            return

        window_key = f"{win_info.process_name}::{win_info.title}"

        # 2. Check stability
        if window_key != self._last_window_key:
            self._last_window_key = window_key
            self._window_stable_since = now
            return

        if not is_window_stable(window_key, self._last_window_key, self._window_stable_since, now, self._config.min_window_stable_seconds):
            return

        # 3. Check cooldown
        min_cooldown_sec = self._config.min_cooldown_minutes * 60.0
        if is_cooldown_active(self._last_comment_time, now, min_cooldown_sec):
            return

        # 4. Check blocked processes and fullscreen
        is_fullscreen = is_likely_fullscreen_content(win_info)
        if is_process_blocked(win_info.process_name, win_info.title, self._config.blocked_processes, is_fullscreen):
            return

        # 5. Check repeat window
        repeat_window_sec = self._config.repeat_window_minutes * 60.0
        if is_repeated_comment(window_key, self._comment_history, now, repeat_window_sec):
            return

        # 6. Retrieve known facts summary
        known_facts = ""
        if self._fact_memory is not None:
            try:
                known_facts = await self._fact_memory.format_for_prompt(max_facts=10)
            except Exception as exc:
                logger.debug("Could not format facts for proactivity: %s", exc)

        # 7. Triaging / lightweight decision
        suggested_comment = await should_comment(win_info, known_facts, self._provider)
        if not suggested_comment:
            return

        # 8. Synthesize through full AgentLoop (ensuring Senjougahara tone + TTS payload)
        synthetic_input = (
            f"[Observação espontânea, não é uma pergunta do usuário — comente brevemente "
            f"e no seu estilo, sem parecer forçado: {suggested_comment}]"
        )

        try:
            response = await self._agent.process(synthetic_input)
            if response and response.text:
                emotion_val = response.emotion.value if hasattr(response.emotion, "value") else str(response.emotion)
                priority_val = response.priority.value if hasattr(response.priority, "value") else str(response.priority)
                await self._bridge.speak(
                    text=response.text,
                    emotion=emotion_val,
                    animation=response.animation,
                    priority=priority_val,
                )
                self._last_comment_time = now
                self._comment_history[window_key] = now
                logger.info("Emitted proactive comment on '%s': %s", win_info.title, response.text)
        except Exception as exc:
            logger.error("Failed emitting proactive comment: %s", exc)

    def start(self) -> asyncio.Task:
        if self._task is not None and not self._task.done():
            return self._task
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        return self._task

    async def _run_loop(self) -> None:
        logger.info("ProactivityObserver loop started (interval=%.1fs)", self._config.poll_interval_seconds)
        while self._running:
            try:
                await self.tick()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("Error in proactivity tick: %s", exc)

            try:
                await asyncio.sleep(self._config.poll_interval_seconds)
            except asyncio.CancelledError:
                break

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
