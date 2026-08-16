# Setup Guide

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Windows | 10 or 11 | No WSL or Docker needed |
| Python | 3.11+ | [python.org](https://python.org) |
| Node.js | 20+ | [nodejs.org](https://nodejs.org) |
| AivisSpeech | Latest | [aivis-project.com](https://aivis-project.com/) — OR VOICEVOX as fallback |
| Anthropic API Key | — | [console.anthropic.com](https://console.anthropic.com) |
| Git | Latest | For cloning the avatar fork |

---

## Step-by-Step Installation

### 1. Fork/clone the avatar base

From the project root (`C:\senjougahara-project\`):

```powershell
git clone https://github.com/rennosuke-haresu/desktop-mascot-mcp avatar
```

Inspect the clone before modifying anything:
```powershell
Get-Content avatar\README.md
npm --prefix avatar install
# Verify it runs unmodified first:
npm --prefix avatar run start:electron
```

Once verified, the new `bridge-server.ts` is already located at `avatar/src/main/bridge-server.ts`.

### 2. Set up the Python brain

```powershell
python -m venv brain\.venv
brain\.venv\Scripts\pip install -r brain\requirements.txt

# Install Playwright's Chromium browser (used for browser automation in Phase 3)
brain\.venv\Scripts\playwright install chromium
```

### 3. Install and run AivisSpeech

1. Download AivisSpeech from https://aivis-project.com/
2. Install and launch it
3. Verify it is running: `curl http://127.0.0.1:10101/version`

Alternatively, use VOICEVOX (default port: 50021 — update `TTS_ENGINE_BASE_URL` in `.env`).

### 4. Configure the project

```powershell
# Create your local .env (gitignored — never commit this)
copy config\.env.example .env

# Edit .env and fill in:
# ANTHROPIC_API_KEY=sk-ant-...
# TTS_ENGINE_BASE_URL=http://127.0.0.1:10101  (AivisSpeech)
# TTS_SPEAKER_ID=888753760                     (check AivisSpeech speaker list)

# Create your local config.yaml
copy config\config.example.yaml config\config.yaml
# Edit as needed (personality profile, hotkey, etc.)
```

### 5. Add a VRM model

Place a `.vrm` model file in `avatar\assets\models\`. Free/CC models:
- [VRoid Hub](https://hub.vroid.com/) (filter by free commercial license)
- [BOOTH](https://booth.pm/) (search "VRM free")

Update the model path in `avatar\src\renderer\` (see desktop-mascot-mcp's README for model loading config).

### 6. Run in development mode

```powershell
.\scripts\dev.ps1
```

Or individually:
```powershell
# Terminal 1 (brain):
brain\.venv\Scripts\python -m brain.main

# Terminal 2 (avatar):
npm --prefix avatar run start:electron
```

### 7. Test Phase 1 text mode

```powershell
# Health check:
curl http://127.0.0.1:8766/health

# Send a message:
curl -X POST http://127.0.0.1:8767/chat `
  -H "Content-Type: application/json" `
  -d '{"message": "Open Notepad"}'
```

---

## Wake Word Training (Phase 2+)

Phase 1 ships with a stock openWakeWord model ("hey_jarvis" by default).
To train a custom "Senjougahara" wake phrase:

1. Collect ~30-60 positive audio samples of the wake phrase
2. Use the openWakeWord training notebook: https://github.com/dscripka/openWakeWord/tree/main/notebooks
3. Export the trained `.onnx` model
4. Set `wake_word.custom_model_path` in `config.yaml`

This is documented as a Phase 2 fast-follow, not a Phase 1 blocker.

---

## Startup at Windows Login

```powershell
# Register to start at login (Scheduled Task, 15s delay):
.\launcher\install_startup.ps1

# Remove:
.\launcher\install_startup.ps1 -Uninstall
```