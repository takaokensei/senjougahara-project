"""
brain/personality/loader.py

The ONLY module that reads personality YAML profiles and produces system prompts.
No other module may embed character-specific strings or reference profile fields directly.

Swapping the active profile = one-line change in config.yaml. Zero code changes.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

PROFILES_DIR = Path(__file__).parent / "profiles"


class PersonalityProfile:
    """Holds all personality data loaded from a YAML profile."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    @property
    def name(self) -> str:
        return self._data.get("name", "Assistant")

    @property
    def traits(self) -> list[str]:
        return self._data.get("traits", [])

    @property
    def speech_style(self) -> str:
        return self._data.get("speech_style", "")

    @property
    def default_voice_speaker_id(self) -> str | None:
        return self._data.get("voice", {}).get("speaker_id")

    @property
    def baseline_emotion(self) -> str:
        return self._data.get("baseline_emotion", "neutral")

    @property
    def system_prompt_template(self) -> str:
        """Raw template from the YAML, if overriding the auto-generated one."""
        return self._data.get("system_prompt_template", "")

    def build_system_prompt(self, extra_context: str = "") -> str:
        """
        Build the system prompt for the LLM from the profile data.

        If the YAML provides a `system_prompt_template`, use it verbatim
        (allowing maximum author control). Otherwise, auto-build from fields.
        """
        if self.system_prompt_template:
            prompt = self.system_prompt_template
        else:
            traits_text = ", ".join(self.traits) if self.traits else "helpful and friendly"
            prompt = (
                f"You are {self.name}, an AI assistant with the following traits: {traits_text}.\n"
                f"Speech style: {self.speech_style}\n"
                f"Always respond ONLY with a JSON object matching this exact schema:\n"
                f'{{"text": "your spoken reply", "emotion": "neutral|happy|sad|angry|surprised|confused|annoyed|relaxed", '
                f'"animation": "idle|greeting|nod|shrug|thinking|goodbye|surprised|angry_gesture", "priority": "low|normal|high|urgent"}}\n'
                f"\nCritical rules:\n"
                f"- text: what you will say aloud (natural, conversational, in character)\n"
                f"- emotion: the facial expression that fits the response\n"
                f"- animation: a gesture that accompanies the speech\n"
                f"- priority: normal for most responses; high for urgent information; low for casual remarks\n"
                f"- Never include any text outside the JSON object.\n"
                f"- Never break character.\n"
            )

        if extra_context:
            prompt += f"\n\nAdditional context:\n{extra_context}"

        return prompt


def load_profile(profile_name: str) -> PersonalityProfile:
    """
    Load a personality profile by name.
    Looks for: brain/personality/profiles/<profile_name>.yaml
    """
    profile_path = PROFILES_DIR / f"{profile_name}.yaml"

    if not profile_path.exists():
        logger.warning(
            "Personality profile '%s' not found at %s. Using empty default.",
            profile_name,
            profile_path,
        )
        return PersonalityProfile({})

    with profile_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    logger.info("Loaded personality profile: %s", profile_name)
    return PersonalityProfile(data)