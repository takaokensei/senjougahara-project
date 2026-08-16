"""
brain/cli.py

Interactive Terminal CLI for Senjougahara.
Allows direct text interactions, testing tools, and verifying avatar reaction in real time.

Usage:
  python -m brain.cli
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

from brain.agent.loop import AgentLoop
from brain.agent.providers.factory import create_llm_provider
from brain.bridge.client import BridgeClient
from brain.config import config
from brain.permissions.policy import PermissionEngine, load_policy_overrides
from brain.personality.loader import load_profile
from brain.speech.tts import TTSAdapter
from brain.tools.registry import import_all_tools

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("cli")


async def run_cli() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 65)
    print("  ⛩️  SENJOUGAHARA — Interactive Desktop Companion CLI  ⛩️")
    print("=" * 65)
    print("Type your message and press Enter.")
    print("Commands: 'exit' or 'quit' to leave | 'state <STATE>' to test avatar pose.")
    print("-" * 65)

    import_all_tools()
    profile = load_profile(config.personality.active_profile)
    provider = create_llm_provider(config.llm)

    bridge = BridgeClient(host=config.bridge.host, port=config.bridge.port)
    await bridge.connect()

    policy_yaml = Path(__file__).parent / "permissions" / "policy.yaml"
    policy_overrides = load_policy_overrides(policy_yaml)

    async def confirm_cli(request_id: str, tool_name: str, description: str) -> bool:
        print(f"\n⚠️  [HIGH-RISK CONFIRMATION NEEDED]")
        print(f"Tool: {tool_name}")
        print(f"Description: {description}")
        ans = input("Allow execution? (y/N): ").strip().lower()
        return ans in ("y", "yes")

    permission_engine = PermissionEngine(
        audit_log_path=config.appdata_dir / "logs" / "audit.jsonl",
        policy_overrides=policy_overrides,
        confirmation_callback=confirm_cli,
    )

    system_prompt = profile.build_system_prompt()
    agent = AgentLoop(
        provider=provider,
        permission_engine=permission_engine,
        system_prompt=system_prompt,
    )

    tts = TTSAdapter(
        engine_base_url=config.tts.engine_base_url,
        speaker_id=config.tts.speaker_id,
        speed=config.tts.speed,
        pitch=config.tts.pitch,
        audio_cache_dir=config.appdata_dir / "audio_cache",
    )

    conversation_history: list[dict] = []
    print(f"[Ready] Personality: {profile.name} | LLM: {config.llm.provider} ({config.llm.model})\n")

    while True:
        try:
            user_input = (await asyncio.to_thread(input, "You > ")).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            break

        if user_input.startswith("state "):
            st = user_input.split(" ", 1)[1].strip().upper()
            await bridge.set_state(st, reason="manual CLI command")
            print(f"[Avatar state set to: {st}]")
            continue

        await bridge.set_state("THINKING", reason="processing input")

        try:
            response = await agent.process(user_input, conversation_history)
            conversation_history.append({"role": "user", "content": user_input})
            conversation_history.append({"role": "assistant", "content": response.text})

            print(f"\n{profile.name} > {response.text}")
            print(f"  [Emotion: {response.emotion.value} | Gesture: {response.animation} | Priority: {response.priority.value}]")

            audio_res = await tts.speak(
                text=response.text,
                emotion=response.emotion.value,
                animation=response.animation,
            )

            await bridge.speak(
                text=response.text,
                emotion=response.emotion.value,
                animation=response.animation,
                audio_url=audio_res.get("audio_url"),
                priority=response.priority.value,
            )

            # Play local audio file (WAV or MP3) via Windows audio output for direct CLI feedback
            wav_path = audio_res.get("wav_path")
            if wav_path and Path(wav_path).exists():
                try:
                    p = Path(wav_path)
                    if p.suffix.lower() == ".mp3":
                        import subprocess
                        abs_p = str(p.resolve())
                        cmd = f"Add-Type -AssemblyName PresentationCore; $p = New-Object System.Windows.Media.MediaPlayer; $p.Open('{abs_p}'); $p.Play(); Start-Sleep -Seconds 5"
                        subprocess.Popen(["powershell", "-c", cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else:
                        import winsound
                        winsound.PlaySound(str(p), winsound.SND_FILENAME | winsound.SND_ASYNC)
                except Exception as play_exc:
                    logger.debug("CLI audio playback error: %s", play_exc)

            print()

        except Exception as exc:
            print(f"\n❌ Error: {exc}\n")
            await bridge.set_state("ERROR")

    await bridge.disconnect()


if __name__ == "__main__":
    asyncio.run(run_cli())