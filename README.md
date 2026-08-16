# Senjougahara

**An AI-powered anime desktop companion for Windows 10/11.**

A persistent 3D VRM anime character lives on your desktop as a transparent, always-on-top window. Activate her via a global hotkey or wake word, speak a request, and she performs real actions on your computer while responding with natural speech, lip-synced animation, and contextual expressions.

> **Status:** Phase 1 (text-only) — see [Development Roadmap](#development-roadmap)

---

## Architecture

Two native Windows processes communicating over a local WebSocket/REST bridge:

| Process | Technology | Role |
|---|---|---|
| `avatar/` | Electron + Three.js + @pixiv/three-vrm | Renders the 3D VRM character, plays TTS audio with lip-sync, owns the system tray and global hotkey |
| `brain/` | Python 3.11+ | LLM agent loop, speech I/O, Windows automation, memory, permission engine |

Bridge: `ws://127.0.0.1:8765` (WebSocket events) + `http://127.0.0.1:8767/chat` (text input in Phase 1)

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design rationale.

---

## Quick Start (Voice & Hands-Free Interaction)

### Prerequisites

- Windows 10/11
- Python 3.11+
- Node.js 20+
- [AivisSpeech](https://aivis-project.com/) (or VOICEVOX) running on port `10101`
- Ollama running locally (or API key for Anthropic/OpenAI/Gemini)

### 1. Setup Python Environment & Dependencies

```powershell
pip install -r brain\requirements.txt
playwright install chromium
```

### 2. Configure

```powershell
copy config\.env.example .env
copy config\config.example.yaml config\config.yaml
# Edit config/config.yaml (defaults work out of the box with Ollama & AivisSpeech)
```

### 3. Launch Senjougahara

```powershell
# Run the complete system (Brain + Voice Pipeline + Avatar)
.\scripts\dev.ps1
```

Or run the Brain backend directly:

```powershell
python -m brain.main
```

### 4. Talk to Senjougahara (Voice Mode — Primary)

1. Press the global hotkey: **`Right Ctrl`** (works anywhere in Windows).
2. The avatar transitions to **`LISTENING`** state.
3. Speak your request (e.g. *"Abra o YouTube e procure músicas relaxantes"* or *"Como você está se sentindo hoje?"*).
4. Senjougahara transcribes your voice (via `faster-whisper`), processes the prompt, speaks back with her Japanese anime voice (via `AivisSpeech`), and triggers lip-sync and expressions on your desktop!

#### Hands-Free Wake Word (Optional)
To activate hands-free without pressing any keys, enable wake word in `config/config.yaml`:
```yaml
wake_word:
  enabled: true
  phrase: hey_jarvis  # or custom model path
```

---

## Debug & Text Interfaces (Secondary)

- **Interactive CLI**: `python -m brain.cli` for terminal-based testing.
- **REST Debug Endpoint**: `POST http://127.0.0.1:8766/chat` with `{"message": "Open Notepad"}`.
- **Health Check**: `GET http://127.0.0.1:8766/health`.

---

## Development Roadmap

| Phase | Status | Feature |
|---|---|---|
| **1** | 🔧 In Progress | Text-only: agent loop + personality + 3 tools + avatar + TTS |
| **2** | ⏳ Planned | Voice input: hotkey + faster-whisper STT + openWakeWord |
| **3** | ⏳ Planned | Desktop control: pywinauto + Playwright + filesystem + terminal + screenshots |
| **4** | ⏳ Planned | Advanced avatar: full emotion/gesture set, idle micro-behaviors, better lip-sync |
| **5** | ⏳ Planned | Memory: SQLite facts/preferences/conversation log |
| **6** | ⏳ Planned | Advanced autonomy: proactive suggestions (opt-in), scheduled tasks |

---

## Project Structure

```
senjougahara-project/
├── avatar/          # Electron + three-vrm avatar shell (fork of desktop-mascot-mcp)
├── brain/           # Python agent backend
├── launcher/        # Startup orchestrator + Windows Startup registration
├── config/          # config.example.yaml, .env.example
├── shared/schemas/  # Bridge protocol JSON schemas
├── docs/            # Architecture, setup, permissions documentation
└── scripts/         # dev.ps1, build.ps1
```

---

## Security

All desktop automation tools are risk-tiered (LOW/MEDIUM/HIGH). HIGH-risk actions always require explicit user confirmation and cannot be silently auto-approved. See [docs/PERMISSIONS.md](docs/PERMISSIONS.md).

---

## License

MIT — see [LICENSE](LICENSE). Third-party attributions in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

The `avatar/` directory is a fork of [desktop-mascot-mcp](https://github.com/rennosuke-haresu/desktop-mascot-mcp) (MIT).