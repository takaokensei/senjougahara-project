"""
brain/config.py

Loads config/config.yaml + .env and exposes a typed AppConfig object.
This is the single source of truth for all runtime configuration.
No other module hard-codes paths, ports, or settings.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, field_validator

# ---------------------------------------------------------------------------
# Locate the project root and load .env
# ---------------------------------------------------------------------------
# Project root is two levels up from brain/config.py: project_root/brain/config.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
CONFIG_FILE = PROJECT_ROOT / "config" / "config.yaml"

# Load .env first so os.environ is populated before we resolve ${VAR} tokens
load_dotenv(ENV_FILE)


# ---------------------------------------------------------------------------
# Pydantic sub-models
# ---------------------------------------------------------------------------

class PersonalityConfig(BaseModel):
    active_profile: str = "senjougahara"


class LLMConfig(BaseModel):
    provider: str = "anthropic"  # anthropic | openai | gemini | ollama
    model: str = "claude-sonnet-4-5"
    ollama_base_url: str = "http://localhost:11434"


class STTConfig(BaseModel):
    enabled: bool = True
    engine: str = "faster-whisper"
    model_size: str = "small"
    device: str = "auto"  # auto | cuda | cpu
    compute_type: str = "auto"  # auto | int8 | float16
    language: str | None = None


class WakeWordConfig(BaseModel):
    enabled: bool = False
    phrase: str = "hey_jarvis"
    custom_model_path: str | None = None


class HotkeyConfig(BaseModel):
    enabled: bool = True
    key: str = "right ctrl"


class TTSConfig(BaseModel):
    engine_base_url: str = "http://127.0.0.1:10101"
    speaker_id: str = ""
    speed: float = 1.0
    pitch: float = 0.0


class BridgeConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765


class MemoryConfig(BaseModel):
    enabled: bool = False
    summary_threshold_turns: int = 20


class PermissionsConfig(BaseModel):
    overrides: dict[str, str] = {}


class LoggingConfig(BaseModel):
    level: str = "INFO"


class SessionConfig(BaseModel):
    greeting_cooldown_hours: float = 8.0


class TelegramConfig(BaseModel):
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""


class AppConfig(BaseModel):
    personality: PersonalityConfig = PersonalityConfig()
    llm: LLMConfig = LLMConfig()
    stt: STTConfig = STTConfig()
    wake_word: WakeWordConfig = WakeWordConfig()
    hotkey: HotkeyConfig = HotkeyConfig()
    tts: TTSConfig = TTSConfig()
    bridge: BridgeConfig = BridgeConfig()
    memory: MemoryConfig = MemoryConfig()
    permissions: PermissionsConfig = PermissionsConfig()
    logging: LoggingConfig = LoggingConfig()
    session: SessionConfig = SessionConfig()
    telegram: TelegramConfig = TelegramConfig()

    # Derived paths (always fixed, not configurable — to avoid path traversal)
    @property
    def appdata_dir(self) -> Path:
        """Persistent data directory: %LOCALAPPDATA%\\Senjougahara\\"""
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        d = base / "Senjougahara"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def logs_dir(self) -> Path:
        """Log files: %APPDATA%\\Senjougahara\\logs\\"""
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        d = base / "Senjougahara" / "logs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def session_state_file(self) -> Path:
        return self.appdata_dir / "session_state.json"


# ---------------------------------------------------------------------------
# YAML loader with ${ENV_VAR} interpolation
# ---------------------------------------------------------------------------

def _interpolate(value: Any) -> Any:
    """Replace ${VAR} tokens in string values with os.environ equivalents."""
    if isinstance(value, str):
        if value.startswith("${") and value.endswith("}"):
            var_name = value[2:-1]
            return os.environ.get(var_name, "")
        return value
    if isinstance(value, dict):
        return {k: _interpolate(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate(item) for item in value]
    return value


def load_config() -> AppConfig:
    """Load and validate application configuration."""
    raw: dict[str, Any] = {}

    if CONFIG_FILE.exists():
        with CONFIG_FILE.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        raw = _interpolate(raw)
    else:
        # Fallback to environment variables only (useful in CI/testing)
        raw = {
            "tts": {
                "engine_base_url": os.environ.get("TTS_ENGINE_BASE_URL", "http://127.0.0.1:10101"),
                "speaker_id": os.environ.get("TTS_SPEAKER_ID", ""),
            },
            "bridge": {
                "host": os.environ.get("BRIDGE_HOST", "127.0.0.1"),
                "port": int(os.environ.get("BRIDGE_PORT", "8765")),
            },
            "llm": {
                "ollama_base_url": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
            },
        }

    return AppConfig.model_validate(raw)


# Module-level singleton — import this everywhere
config: AppConfig = load_config()
