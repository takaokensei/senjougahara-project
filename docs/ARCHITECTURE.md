# Architecture

## Selected Architecture: E (Native Win Backend + Web Avatar Renderer)

Two native Windows processes, both on `127.0.0.1`, communicating over WebSocket/REST.

```
avatar/ (Electron)  <--WS/HTTP:8765-->  brain/ (Python)
       |                                       |
   three-vrm                            agent loop
   lip-sync                             LLM providers
   state machine                        tools (pywinauto, playwright)
   system tray                          TTS adapter
   hotkey listener                      permission engine
       |
   AivisSpeech (separate process, :10101)
```

## Key Design Decisions

### Why Electron + three-vrm (not Tauri, not Live2D)
- `desktop-mascot-mcp` (MIT) is the only Windows-proven, MIT-licensed reference implementation that ticks all requirements: transparent always-on-top window, three-vrm, VOICEVOX-compatible TTS, VRMA gestures.
- Live2D requires a proprietary Cubism Core SDK with commercial licensing friction.
- Tauri is a legitimate alternative but adds Rust as a third runtime and the reference implementation is Electron.

### Why Python for the brain (not Node/Electron monolith)
- Python's ecosystem is strongest for: Windows UI automation (pywinauto), Whisper STT (faster-whisper), agent frameworks (LangGraph if needed), and ML dependencies in later phases.
- Keeps each half in the language best suited to it, at the cost of one IPC hop (acceptable, well-precedented).

### Why WebSocket/REST (not MCP, not named pipes, not message bus)
- Simple, debuggable with any HTTP client or browser DevTools.
- Language-agnostic (TypeScript avatar + Python brain both support it natively).
- MCP is used in exactly one place with genuine payoff: optionally re-exposing the tool layer to Claude Desktop / Cursor for debugging. It is never on the hot path.
- Named pipes: less debuggable, not meaningfully faster on loopback.
- Redis/NATS: unnecessary infrastructure for two local processes.

### Why AivisSpeech over VOICEVOX
- Both expose the same VOICEVOX-compatible HTTP API (trivially hot-swappable via config).
- AivisSpeech provides materially better emotional expressiveness out of the box.
- AivisSpeech is Windows-only, which is fine for this project.

### Why not fork vierisid/jarvis
- Its daemon has no native Windows support (requires WSL2/Docker).
- Licensed under Jarvis Source Available License 2.0 (RSALv2), not permissive.
- Enormous feature surface (workflow engine, OKRs, Telegram/Discord, multi-agent) is mostly deadweight for a personal desktop companion.
- Its patterns (authority engine, structured output, vault memory) ARE adopted, reimplemented independently.

## IPC Protocol

See `shared/schemas/bridge-messages.json` for the full JSON schema.

| Message | Direction | Transport |
|---|---|---|
| `speak` | Brain -> Avatar | WebSocket |
| `state_change` | Brain -> Avatar | WebSocket |
| `confirmation_request` | Brain -> Avatar | WebSocket |
| `error` | Brain -> Avatar | WebSocket |
| `activate` | Avatar -> Brain | WebSocket |
| `confirmation_response` | Avatar -> Brain | WebSocket |
| `ping`/`pong` | Both | WebSocket |

## Port Allocation

| Port | Service |
|---|---|
| 8765 | Avatar bridge WebSocket server (brain connects here) |
| 8766 | Brain health check HTTP + audio file server |
| 8767 | Brain chat REST endpoint (Phase 1 text input) |
| 10101 | AivisSpeech TTS engine (external, default) |
| 50021 | VOICEVOX TTS engine (external, fallback) |

## Startup Sequence

```
Windows Login
  -> Launcher (launcher/launcher.py)
       -> Check TTS engine (/version)
       -> Start Brain (python -m brain.main)
            -> StartupStateMachine:
               CHECKING_LLM_PROVIDER
               CHECKING_TTS
               CHECKING_DESKTOP_BRIDGE
               LOADING_PERSONALITY
               READY
            -> Expose GET /health on :8766
       -> Poll /health until {"status": "ready"}
       -> Start Avatar (npm run start:electron)
            -> BridgeServer starts on :8765
            -> Brain BridgeClient connects
       -> Check session_state.json -> greeting (once per session)
```

## Memory Architecture (Phase 5+)

SQLite at `%LOCALAPPDATA%\Senjougahara\memory.db`:
- `facts` (key/value long-term facts)
- `preferences` (user settings)
- `conversation_log` (rolling window, periodically summarized)

Phase 6+ option: add `memory_embeddings` table (sqlite-vec) for semantic recall.

## Non-Goals (v1-v6)

- Multi-machine sidecars
- Visual workflow builder
- Telegram/Discord channels
- Multi-agent hierarchy
- Cross-platform (macOS/Linux) support