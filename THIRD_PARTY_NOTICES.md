# Third-Party Notices

This file documents all third-party components used in the Senjougahara project,
their licenses, and their upstream sources.

---

## avatar/ - Forked from desktop-mascot-mcp

**Source:** https://github.com/rennosuke-haresu/desktop-mascot-mcp  
**License:** MIT  
**Author:** rennosuke-haresu  

The `avatar/` directory is a fork of `desktop-mascot-mcp`. Its original LICENSE.md
is preserved at `avatar/LICENSE.md`. Project-specific additions (bridge-server.ts,
state-machine.ts extensions) are also MIT-licensed and attributed to this project.

---

## @pixiv/three-vrm

**Source:** https://github.com/pixiv/three-vrm  
**License:** MIT  
**Author:** Pixiv Inc.  

Used transitively via the desktop-mascot-mcp fork. Provides VRM 3D model loading
and rendering on top of Three.js.

---

## Python Dependencies (brain/)

| Package | License | Purpose |
|---|---|---|
| anthropic | MIT | Claude LLM provider SDK |
| openai | MIT | OpenAI provider SDK |
| google-generativeai | Apache-2.0 | Google Gemini provider SDK |
| ollama | MIT | Ollama local LLM client |
| pywinauto | BSD-3-Clause | Windows GUI automation |
| playwright | Apache-2.0 | Browser automation |
| faster-whisper | MIT | Local speech-to-text (Whisper) |
| openwakeword | Apache-2.0 | Wake-word detection |
| mss | MIT | Fast screen capture |
| mcp | MIT | Model Context Protocol SDK |
| pyyaml | MIT | YAML parsing |
| python-dotenv | BSD-3-Clause | .env file loading |
| keyboard | MIT | Global hotkey hook |
| aiosqlite | MIT | Async SQLite |
| websockets | BSD-3-Clause | WebSocket server/client |
| fastapi | MIT | HTTP server (bridge/health) |
| uvicorn | BSD-3-Clause | ASGI server |
| pydantic | MIT | Data validation / structured output |

---

## Architectural Inspiration (no code copied)

The following projects were studied for architectural patterns. No code was copied
from them into this repository.

- **vierisid/jarvis** (Jarvis Source Available License 2.0 / RSALv2): studied for
  the authority/permission engine risk-tiering pattern, the {text, emotion,
  animation, priority} structured-output convention, and the SQLite vault memory
  schema. Code reimplemented independently in brain/permissions/,
  brain/agent/structured_output.py, and brain/memory/.

- **not-elm/desktop-homunculus** (MIT/Apache-2.0): studied for dynamic FPS
  throttling in the idle state and the MOD system concept for future extensibility.

---

## AivisSpeech / VOICEVOX (external service - not bundled)

AivisSpeech and VOICEVOX are external applications installed separately by the user.
They are not bundled in this repository. Their licenses apply to their own
distributions. Consult their respective projects for per-model/per-voice license
details, especially before any commercial distribution.

- AivisSpeech: https://aivis-project.com/
- VOICEVOX: https://voicevox.hiroshiba.jp/
