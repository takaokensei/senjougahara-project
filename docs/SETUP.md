# Setup Guide

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Windows | 10 or 11 | No WSL or Docker needed |
| Python | 3.11+ | [python.org](https://python.org) or installed via uv |
| uv | Latest | [astral.sh/uv](https://docs.astral.sh/uv/) (fast Python manager) |
| Node.js | 20+ | [nodejs.org](https://nodejs.org) |
| AivisSpeech | Latest | [aivis-project.com](https://aivis-project.com/) — OR VOICEVOX as fallback |
| Anthropic API Key | — | [console.anthropic.com](https://console.anthropic.com) (or Ollama locally) |
| Git | Latest | Version control |

---

## Step-by-Step Installation

### 1. Set up the Python brain with uv

```powershell
# Install uv if needed:
# powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Create virtual environment and install dependencies:
uv venv brain\.venv
uv pip install -r brain\requirements.txt --python brain\.venv\Scripts\python.exe

# Install Playwright's Chromium browser (used for browser automation)
brain\.venv\Scripts\playwright install chromium
```

### 2. Set up the Avatar (Electron)

```powershell
npm --prefix avatar install
npm --prefix avatar run build:electron
```

### 3. Add a VRM 3D Model

Place a `.vrm` character model file into `avatar\assets\models\AliciaSolid.vrm` (or specify your custom filename in `avatar\dist\renderer\config.json`).

Free / CC VRM models:
- [VRoid Hub](https://hub.vroid.com/) (filter by "Free commercial use")
- [BOOTH.pm](https://booth.pm/en) (search "VRM free")
- [UniVRM Alicia Solid](https://github.com/dwango/UniVRM/tree/master/Assets/VRM/Models/AliciaSolid)

*(If no VRM file is present, the window will open with a helper badge prompting you to add a model).*

### 4. Install and run AivisSpeech

1. Download AivisSpeech from https://aivis-project.com/
2. Install and launch it
3. Verify it is running: `curl http://127.0.0.1:10101/version`

### 5. Configure the project

```powershell
# Create your local .env (gitignored — never commit this)
copy config\.env.example .env

# Create your local config.yaml
copy config\config.example.yaml config\config.yaml
# Edit config/config.yaml as needed (Ollama/Anthropic, hotkey, etc.)
```

### 6. Run in development mode

```powershell
.\scripts\dev.ps1
```

Or run individually:
```powershell
# Terminal 1 (brain):
python -m brain.main

# Terminal 2 (avatar):
npm --prefix avatar run start:electron
```

### 7. Interact

- **Voice (Primary)**: Press `Right Ctrl` anywhere in Windows, speak into your mic.
- **Health check**: `curl http://127.0.0.1:8766/health`
- **Text chat (Debug)**:
  ```powershell
  curl -X POST http://127.0.0.1:8766/chat `
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