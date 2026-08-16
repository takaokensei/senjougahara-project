"""
launcher/launcher.py

Startup orchestrator for Senjougahara.

Sequence:
  1. Check TTS engine
  2. Start Brain subprocess
  3. Poll Brain /health until READY (30s)
  4. Start Avatar subprocess
  5. Check session_state.json -> fire greeting only if new session
  6. Supervise both processes
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCAL_APP_DATA = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
SESSION_STATE_FILE = LOCAL_APP_DATA / "Senjougahara" / "session_state.json"
BRAIN_HEALTH_URL = "http://127.0.0.1:8766/health"
TTS_URL = os.environ.get("TTS_ENGINE_BASE_URL", "http://127.0.0.1:10101")
GREETING_COOLDOWN_HOURS = float(os.environ.get("GREETING_COOLDOWN_HOURS", "8"))

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("launcher")


def load_session_state() -> dict:
    if SESSION_STATE_FILE.exists():
        try:
            return json.loads(SESSION_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"greeted_at": None}


def save_session_state(state: dict) -> None:
    SESSION_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_STATE_FILE.write_text(json.dumps(state), encoding="utf-8")


def should_greet() -> bool:
    """
    Fire greeting if first run or cooldown expired.
    A brain crash+restart within cooldown does NOT re-trigger.
    """
    state = load_session_state()
    greeted_at = state.get("greeted_at")
    if greeted_at is None:
        return True
    try:
        last = datetime.fromisoformat(greeted_at)
        elapsed = (datetime.now(timezone.utc) - last).total_seconds() / 3600
        return elapsed >= GREETING_COOLDOWN_HOURS
    except Exception:
        return True


def mark_greeted() -> None:
    state = load_session_state()
    state["greeted_at"] = datetime.now(timezone.utc).isoformat()
    save_session_state(state)


async def wait_for_health(url: str, timeout_seconds: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    backoff = 0.5
    async with httpx.AsyncClient(timeout=3.0) as client:
        while time.monotonic() < deadline:
            try:
                resp = await client.get(url)
                if resp.status_code == 200 and resp.json().get("status") == "ready":
                    return True
                logger.info("Brain status: %s", resp.json().get("status"))
            except Exception:
                pass
            await asyncio.sleep(backoff)
            backoff = min(backoff * 1.5, 5.0)
    return False


def start_brain() -> subprocess.Popen:
    cmd = [sys.executable, "-m", "brain.main"]
    logger.info("Starting brain: %s", " ".join(cmd))
    return subprocess.Popen(cmd, cwd=str(PROJECT_ROOT))


def start_avatar() -> subprocess.Popen:
    cmd = ["npm", "--prefix", str(PROJECT_ROOT / "avatar"), "run", "start:electron"]
    logger.info("Starting avatar: %s", " ".join(cmd))
    return subprocess.Popen(cmd, cwd=str(PROJECT_ROOT))


async def run() -> None:
    logger.info("=" * 60)
    logger.info("Senjougahara Launcher")
    logger.info("Project root: %s", PROJECT_ROOT)
    logger.info("=" * 60)

    # Step 1: TTS check
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            resp = await client.get(f"{TTS_URL}/version")
            if resp.status_code == 200:
                logger.info("TTS engine running at %s", TTS_URL)
        except Exception as exc:
            logger.warning("TTS not reachable: %s. Continuing degraded.", exc)

    # Step 2: Start brain
    brain_proc = start_brain()
    logger.info("Brain PID: %d", brain_proc.pid)

    # Step 3: Wait for brain ready
    logger.info("Waiting for brain READY...")
    if not await wait_for_health(BRAIN_HEALTH_URL, 30.0):
        logger.error("Brain not ready within 30s.")
        brain_proc.terminate()
        sys.exit(1)
    logger.info("Brain READY.")

    # Step 4: Start avatar
    avatar_proc = start_avatar()
    logger.info("Avatar PID: %d", avatar_proc.pid)

    # Step 5: Greeting
    if should_greet():
        logger.info("New session: greeting will fire.")
        state = load_session_state()
        state["pending_greeting"] = True
        save_session_state(state)
        mark_greeted()
    else:
        logger.info("Within cooldown: no greeting.")

    # Step 6: Supervise
    logger.info("Supervising processes...")
    try:
        while True:
            await asyncio.sleep(5)
            if brain_proc.poll() is not None:
                logger.error("Brain exited (code %d)!", brain_proc.returncode)
                avatar_proc.terminate()
                break
            if avatar_proc.poll() is not None:
                logger.warning("Avatar exited (code %d).", avatar_proc.returncode)
                break
    except KeyboardInterrupt:
        logger.info("Interrupted. Terminating.")
        brain_proc.terminate()
        avatar_proc.terminate()


if __name__ == "__main__":
    asyncio.run(run())