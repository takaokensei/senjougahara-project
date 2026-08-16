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

## Quick Start (Phase 1 — Text Mode)

### Prerequisites

- Windows 10/11
- Python 3.11+
- Node.js 20+
- [AivisSpeech](https://aivis-project.com/) (or VOICEVOX) installed and running on port 10101
- An Anthropic API key (or other LLM provider)

### 1. Clone the avatar fork

```powershell
# From the project root:
git clone https://github.com/rennosuke-haresu/desktop-mascot-mcp avatar
```

### 2. Install avatar dependencies

```powershell
npm --prefix avatar install
```

### 3. Set up brain Python environment

```powershell
python -m venv brain\.venv
brain\.venv\Scripts\pip install -r brain\requirements.txt
brain\.venv\Scripts\playwright install chromium
```

### 4. Configure

```powershell
copy config\.env.example .env
# Edit .env: add your ANTHROPIC_API_KEY
copy config\config.example.yaml config\config.yaml
# Edit config.yaml as needed (defaults work for most setups)
```

### 5. Run in dev mode

```powershell
.\scripts\dev.ps1
```

Or run individually:

```powershell
# Terminal 1: Brain
brain\.venv\Scripts\python -m brain.main

# Terminal 2: Avatar
npm --prefix avatar run start:electron
```

### 6. Test

```powershell
# Send a text message to the agent (Phase 1 mode)
curl -X POST http://127.0.0.1:8767/chat -H "Content-Type: application/json" -d '{"message": "Open Notepad"}'
```

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