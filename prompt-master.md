# Senjougahara Project — Technology Stack Research & Architecture

**Deep research deliverable for an AI-powered anime desktop companion (Windows 10/11)**
Prepared as an architecture and repository-research pass, concluding in a single ready-to-paste implementation prompt for Antigravity.

---

## Part A — Executive Recommendation

### A.1 The one-sentence architecture

**A native Windows Electron avatar app (forked from `desktop-mascot-mcp`) talks over a local WebSocket/HTTP bridge to a Python "brain" process (LangGraph-or-simple-loop agent using Claude/GPT/Gemini/Ollama) that calls a small set of well-scoped tools — Windows UI Automation via `pywinauto`, Playwright for the browser, direct filesystem/subprocess calls, and `faster-whisper` for STT — with AivisSpeech/VOICEVOX for TTS, `openWakeWord` for the wake phrase, and a global-hotkey listener for manual activation.** Everything runs as native Windows processes; nothing requires WSL or Docker for the parts the user actually touches every day.

This deliberately does **not** fork `vierisid/jarvis` as the runtime brain, even though it is the most feature-complete "JARVIS-style" project found. Reasons are below (§A.3) — it is read closely as **reference architecture**, and several of its ideas (structured `{text, emotion, animation}` outputs, an authority/permission engine, a Go sidecar model, vault-style SQLite memory) are recommended for adoption in a much smaller, purpose-built implementation.

### A.2 Why this combination, not the obvious alternatives

**Avatar: 3D VRM over Live2D.** Both are viable, but VRM wins for this project specifically because (1) `@pixiv/three-vrm` + Three.js is MIT-licensed, actively maintained, and has zero per-model licensing friction (VRoid Hub has thousands of free/CC models); Live2D Cubism requires a proprietary Core SDK with its own commercial license terms and per-model rigging effort that a solo builder cannot easily produce for a custom "Senjougahara"-archetype character. (2) A working reference implementation already exists and matches almost exactly what's wanted: `desktop-mascot-mcp` (Electron + three-vrm + VOICEVOX-family TTS + VRMA gesture system + transparent always-on-top window, MIT license, Windows-tested). (3) VRM has a clean animation interchange format (VRMA) with a real pipeline (Mixamo → Blender/CLI converter → VRMA) for sourcing gestures, whereas Live2D motion files are typically bespoke per-model.

**Agent runtime: don't fork JARVIS's daemon; write a small Python/TS agent loop, borrow JARVIS's *patterns*.** `vierisid/jarvis` is genuinely excellent engineering, but two hard facts rule it out as the core dependency: its daemon explicitly **does not support native Windows** ("native Windows is not supported for the JARVIS daemon... use WSL2... or Docker"), and it ships under the **Jarvis Source Available License 2.0** (RSALv2-based), a source-available, *not* permissive OSI license, whose commercial-use restrictions are a poor foundation to build a personal product on top of. Its **sidecar**, however, is a native Windows Go binary doing exactly the Win32/UIAutomation work this project needs — that pattern (a small native automation service, separate from the brain) is worth reusing conceptually, but reimplementing it in ~500 lines of Python (`pywinauto` + `pygetwindow` + `pyperclip` + `subprocess`) is simpler than adopting a licensed, WSL-dependent daemon.

**STT: faster-whisper, not whisper.cpp, not cloud APIs.** Target hardware is Windows with likely NVIDIA GPUs; `faster-whisper`'s CTranslate2 backend is the fastest path on CUDA (roughly 4x real-time speedup over reference Whisper, MIT-licensed, pure Python + pip install), while whisper.cpp's CUDA path is well behind CTranslate2 and its main advantage (zero-dependency binary, Apple Metal) doesn't apply here. Cloud STT (e.g., Deepgram, Whisper API) is available as a pluggable fallback but is not the default, in line with the brief's privacy/reliability priority.

**Wake word: openWakeWord, not Porcupine.** openWakeWord is MIT-licensed, ONNX-based (installs cleanly on Windows), free for any use including commercial, and independent benchmarking shows it can match or beat Porcupine's accuracy on comparable test sets. Porcupine is the more "enterprise-polished" product but requires a Picovoice access key and has commercial licensing costs at scale — unnecessary friction for a personal project. `vierisid/jarvis` independently arrived at the same choice (openWakeWord, ONNX, in-browser), which is a good maintained-project signal.

**TTS: AivisSpeech primary, VOICEVOX-API-compatible fallback.** AivisSpeech is a Windows-first (no macOS/Linux binaries), free-for-commercial-use engine built on a VOICEVOX-compatible HTTP API but with materially better out-of-the-box emotional expressiveness — reviewers consistently describe it as needing "no adjustment" to sound natural and emotionally varied, versus VOICEVOX's playful-but-mechanical-unless-tuned default. Because both speak the same OpenAPI-shaped HTTP contract (`/audio_query`, `/synthesis`, speaker/style IDs), the TTS layer can be a single adapter class with an engine URL + speaker ID swap — exactly the "replace the TTS engine without rewriting the assistant" requirement in the brief. `desktop-mascot-mcp` already implements this adapter pattern and is the direct starting point.

**Desktop control: Python + pywinauto/UIA, Playwright for browser — not a bespoke Go sidecar (yet).** `pywinauto` is BSD-licensed, decade-mature, supports both the legacy Win32 backend and the modern UIA backend, and is the most-cited, most-battle-tested Windows GUI automation library in Python. A Go sidecar (JARVIS's approach) is architecturally cleaner for cross-machine scenarios this project doesn't need in v1; Python keeps the whole backend in one language and one process family, satisfying the brief's "avoid five unrelated runtimes" instruction. Playwright (not raw CDP) is used for browser automation because it is the de facto standard, ships codegen/tracing tooling, and is trivially callable from the same Python process via `playwright-python`.

**IPC: local HTTP + WebSocket on loopback, no message bus, no MCP-for-everything.** The brief explicitly says not to add MCP merely because it's fashionable. The recommended architecture uses **plain local WebSocket + REST on `127.0.0.1`** between the Electron avatar shell and the Python brain (this is exactly what `desktop-mascot-mcp` already does for its own `speak` command, and what JARVIS does between daemon and sidecar). **MCP is used in exactly one place with genuine payoff**: as an *optional*, swappable transport so the same Python tool implementations (filesystem, terminal, browser, desktop-control) can also be exposed to Claude Desktop / Cursor / other MCP clients during development and debugging, and so GitHub/Google-Calendar-style *external* integrations can be added later via existing community MCP servers instead of hand-rolled API clients. It is not used for the hot path between the avatar and the brain, which needs to be low-latency and does not benefit from MCP's discovery semantics.

### A.3 What was rejected, and why

| Considered | Rejected because |
|---|---|
| Forking `vierisid/jarvis` daemon wholesale | No native Windows support for the daemon (WSL2/Docker required); source-available license (RSALv2), not permissive; massive feature surface (workflow engine, goal/OKR tracking, multi-agent hierarchy, Telegram/Discord channels) far beyond what's asked for, meaning most of the codebase would be deadweight to strip out or maintain |
| Live2D as the primary avatar tech | Proprietary Cubism Core SDK licensing; no ready-made Windows-tested reference project as clean as `desktop-mascot-mcp`; the only found MCP-controllable Live2D projects (`live2d-mcp`, `live2d-automation`) are macOS-first or narrowly scoped to lip-sync-only companion apps, not full agentic control |
| `desktop-homunculus` (Bevy/Rust) as the avatar base | Genuinely excellent architecture (MOD system, MCP server, multi-monitor VRMA) but explicitly **early alpha** with a documented Windows caveat (manual NVIDIA Control Panel configuration required pre-launch or the window renders opaque black), and Rust adds a fourth language to the stack for no capability `desktop-mascot-mcp`'s Electron/TS stack doesn't already provide. Recommended as a **reference/inspiration**, not a fork target, primarily for its MOD-system and multi-monitor ideas. |
| `kiskaserver/interactive_assistent` (user-suggested) | This repository could not be located; the GitHub account `kiskaserver` has public repositories in unrelated domains (a co-op Godot game, a game-memory-reading tool) with no assistant/avatar project among them. Treated as a dead/renamed/private link and dropped from the shortlist — flagged explicitly per the brief's instruction not to blindly trust the user's starting points. |
| Porcupine for wake word | Proprietary, requires a Picovoice access key, commercial-scale licensing cost; openWakeWord is free, MIT, ONNX (Windows-native), and benchmarks competitively |
| Tauri as the primary shell | Tauri is a legitimate, lighter-weight alternative to Electron (smaller binary, Rust backend) but the strongest available reference implementation (`desktop-mascot-mcp`) is Electron-based and already solves transparent always-on-top VRM rendering on Windows; re-platforming it to Tauri is pure risk with no capability gain for v1. Documented as Architecture C in the tradeoff table (Part C) for completeness. |
| A single monolithic Electron app hosting the LLM/agent loop in Node | Node's ecosystem for Windows UI Automation, Whisper inference, and mature agent-loop tooling is weaker than Python's; splitting brain (Python) from shell (Electron/TS) keeps each half in the language best suited to it, at the cost of one IPC hop — an acceptable, well-precedented tradeoff (this is exactly JARVIS's daemon/sidecar split, and desktop-mascot-mcp's own MCP-server/renderer split) |

---

## Part B — Repository Comparison

Stars/activity as observed during this research pass (August 2026); all repos re-checked for license and Windows-support claims directly from their READMEs.

| Repository | Purpose | Language | Maintenance | License | Windows Support | Advantages | Disadvantages | Recommendation |
|---|---|---|---|---|---|---|---|---|
| **rennosuke-haresu/desktop-mascot-mcp** | 3D VRM desktop mascot, MCP-controlled, VOICEVOX-family TTS, lip-sync, VRMA gestures | TypeScript (93%) + Electron | Active — v0.3.3 latest release, 64 commits, 7 releases | MIT (assets excluded) | Explicitly tested and confirmed on Windows 10/11 | Exact match for the desired experience; transparent always-on-top window; camera/window state persistence; clean `speak(text, emotion, animation)` interface already matches the brief's requested API; small, readable codebase (easy to fork and extend) | Small project (1 star, single maintainer) — bus-factor risk; MCP-only control surface (no built-in HTTP/WS API, must be added); only 6 emotions and gesture set is whatever VRMA files you supply; no built-in STT or agent loop (by design — it's a rendering/voice server only) | **FORK.** This is the avatar/voice-output core. |
| **not-elm/desktop-homunculus** | Cross-platform VRM desktop mascot with MOD system and MCP server | Rust (Bevy engine) + TypeScript SDK | Active — 363 commits, 11 releases, alpha.6 latest | Dual MIT/Apache-2.0 (code), CC-BY-4.0 (assets) | "Supported" but requires manual NVIDIA Control Panel configuration pre-launch or window renders opaque black | More technically ambitious (multi-monitor, dynamic FPS limiting for power efficiency, TypeScript MOD SDK, WebView UI panels); healthier community (79 stars, 12 open PRs) | Early alpha — "APIs, features, and MOD interfaces may change without notice"; Rust adds a build toolchain not otherwise needed; documented Windows transparency bug is a real first-run risk for non-technical setup | **REFERENCE ONLY.** Study its MOD system and multi-monitor handling for v2+; do not fork for v1. |
| **vierisid/jarvis** | "Always-on autonomous AI daemon" — full agent platform: multi-LLM routing, browser control via CDP, Go desktop sidecar (Win32/UIAutomation/X11), multi-agent hierarchy, workflow builder, voice (openWakeWord + Edge TTS/ElevenLabs), authority/permission engine, SQLite knowledge vault | TypeScript/Bun (daemon) + Go (sidecar) | Very active — 273 commits, updated within days of this research, active Discord | Jarvis Source Available License 2.0 (RSALv2-based) — **not** OSI-approved permissive | Daemon: **not supported** (WSL2/Docker required). Sidecar: native Windows binary, does the actual Win32 automation | Best-in-class architecture reference: authority-gated tool execution, audit trail, structured personality config, vault-based SQLite memory extraction, sidecar/brain split, ambient "pebble" UI pattern worth studying | License precludes free commercial forking/redistribution without review; daemon's Windows story is WSL/Docker-only, contradicting the "feel like a native Windows app" requirement; enormous feature surface (workflows, OKRs, Telegram/Discord channels, multi-agent hierarchy) is overkill and would need aggressive stripping | **REFERENCE ONLY.** Read its source for the authority engine, sidecar RPC protocol, and personality/vault schema design. Do not clone into the product tree; do not depend on its packages. |
| **open-jarvis/OpenJarvis** | "Personal AI, on personal devices" — preset-based agent CLI (`jarvis ask`, `jarvis digest`), skill catalog, multi-agent modes | Mixed (CLI + Rust extension) | Active | Not fully verified in this pass — check before any use | Platform-specific install notes exist (WSL2, native-Windows scheduled task, desktop prerequisites) suggesting partial native-Windows support | Skill-catalog concept (composable, benchmarked skills) is a good pattern for the agent's tool layer | CLI/preset-oriented, not built around a persistent visual companion; unclear how mature the native-Windows path is versus WSL2 | **REFERENCE ONLY.** Worth a closer look for its skill-catalog abstraction if the agent's tool system needs to grow past a hand-written tool list. |
| **kiskaserver/interactive_assistent** (user-suggested) | Unknown — link could not be resolved | — | — | — | — | — | Repository not found under this account at the time of research; account's public work is unrelated (a Godot co-op game, a game-automation tool) | **DROP.** Could not verify existence; do not reference in the implementation prompt. If the user has a private fork or a corrected URL, re-verify before use. |
| **dmrr35/Open.Jarvis** | "Windows-first" open-source JARVIS-style assistant: voice/text, local routing, optional Groq fallback, diagnostics, cyber-style UI | Unspecified (appears JS/Node-based tooling) | Active, v1.0.0 stable tag reached | Not fully verified — check before use | Explicitly designed Windows-first, works in a "keyless degraded mode" without any cloud API | Genuinely Windows-native by design (unlike vierisid/jarvis); conservative safety-gating philosophy aligns with the brief's permission model; local-first with optional cloud fallback matches the "local and/or cloud LLMs" requirement | No avatar/visual layer at all — pure backend assistant; much smaller community/activity signal than vierisid/jarvis; needs its own license/architecture audit before any code is reused | **REFERENCE ONLY / possible tool-layer inspiration.** Worth reading for its "provider fallback + safety gate" pattern; not large or proven enough to depend on directly. |
| **pixiv/three-vrm** | VRM 3D model loading/rendering library for Three.js | TypeScript | Actively maintained by Pixiv (VRM format's own steward) | MIT | Runs anywhere Three.js/WebGL runs, including Electron on Windows | The canonical, first-party VRM renderer; what `desktop-mascot-mcp` itself is built on; excellent docs and format authority | Just a rendering library, not an app — needs a shell | **INTERNAL DEPENDENCY** (transitively, via desktop-mascot-mcp fork; pin the version explicitly) |
| **pywinauto/pywinauto** | Python Windows GUI automation (Win32 + UIA backends) | Python | Mature, long-running, community-maintained | BSD-3-Clause | Windows-only by design (its entire purpose) | Most mature, most documented Python Windows-automation library; dual backend covers both legacy Win32 apps and modern UWP/WPF apps; integrates trivially with any Python agent loop | Windows-only (not a downside here); not built for browser automation (use Playwright alongside it) | **REUSABLE LIBRARY** — pip dependency of the agent/tools layer |
| **dscripka/openWakeWord** | Open-source wake-word detection | Python (ONNX inference) | Actively maintained | Apache-2.0 | Windows-supported (ONNX runtime installs natively; note tflite-runtime is skipped on Windows, onnxruntime is used) | Free, no API key, competitive accuracy vs. Porcupine in independent benchmarks, lightweight enough to run continuously | Custom wake-word training has a real ML learning curve if the built-in phrase set doesn't include "Senjougahara"-like phrases (mitigation: use a generic phrase like "Hey Computer" for v1, train a custom model in Phase 2+) | **REUSABLE LIBRARY** — pip dependency of the speech-input layer |
| **SYSTRAN/faster-whisper** | CTranslate2-backed Whisper STT | Python (C++ backend) | Actively maintained | MIT | Runs on Windows with CUDA (NVIDIA) or CPU int8 fallback | Fastest local Whisper path on NVIDIA hardware; MIT license; simple `pip install` | Needs `cuBLAS`/`cuDNN` present for GPU path (documented, solvable via CUDA-enabled PyTorch/CTranslate2 wheels) | **REUSABLE LIBRARY** — pip dependency of the STT layer |
| **VOICEVOX / AivisSpeech engines** | VOICEVOX-API-compatible local TTS engines | C++/Python core, HTTP API | Both actively maintained; AivisSpeech is the newer, better-funded project (Aivis Project) | VOICEVOX: various OSS terms per component (check per-model); AivisSpeech: free for individual/commercial use per project statement — verify current terms before shipping | AivisSpeech: **Windows only**, by design. VOICEVOX: Windows/macOS/Linux | AivisSpeech gives materially more natural, emotionally varied speech "out of the box"; both expose the same HTTP contract so they're hot-swappable | AivisSpeech's Windows-only nature is a non-issue for this project but rules it out if cross-platform is ever wanted; per-model/per-voice licenses must be checked individually (some VOICEVOX voices restrict certain uses) | **EXTERNAL SERVICE** — run as a separate local process, spoken to over HTTP; not vendored into the repo |
| **microsoft/playwright-python** | Browser automation | Python | Actively maintained by Microsoft | Apache-2.0 | Full Windows support | Industry-standard, auto-installs browser binaries, has tracing/codegen tooling for debugging agent-driven browsing | Adds a Chromium/Firefox/WebKit download (hundreds of MB) — acceptable, document it | **REUSABLE LIBRARY** — pip dependency of the browser-tool layer |

---

## Part C — Final Architecture

### C.1 Architecture tradeoff comparison (Part 14 of the brief)

| | A. JARVIS + separate avatar | B. JARVIS + embedded VRM app | C. Tauri unified app | D. Electron unified app | **E. Native Win backend + web avatar renderer (SELECTED)** |
|---|---|---|---|---|---|
| Complexity | High (two ecosystems, WSL/Docker dependency) | High | Medium-high (Rust learning curve) | Medium | **Medium** |
| Performance | Good once running; WSL adds startup latency and a virtualization tax | Good | Best raw perf (Rust) | Good (Chromium overhead, but avatar is a small window) | **Good** — Python brain is not perf-critical (I/O-bound on LLM calls); Electron avatar window is small and GPU-light |
| Startup time | Slow — WSL/Docker boot adds seconds | Slow | Fast | Medium (Electron cold start ~1-2s) | **Medium**, and avoidable via a persistent background process + tray icon (avatar window shows once brain is warm) |
| Memory usage | High (WSL VM overhead alone is 500MB+) | High | Low | Medium (~150-300MB baseline for Electron) | **Medium** — one Electron avatar (~200MB) + one Python process (~100-300MB depending on loaded local models) |
| GPU usage | Depends on sidecar | Depends | Low overhead | Low-moderate (Three.js/WebGL in a small window) | **Low-moderate**, same as D |
| IPC | WebSocket (daemon↔sidecar) | Similar | In-process or Tauri IPC | In-process (Electron main↔renderer) + external WS to brain | **Local WebSocket/HTTP on 127.0.0.1** between two OS processes — simple, debuggable with any HTTP client, language-agnostic |
| Reliability | WSL/Docker adds a failure domain totally outside the app's control | Same | High (fewer moving parts) | High | **High** — two well-understood native Windows processes, each independently restartable |
| Dev velocity | Slow (must maintain WSL bridge) | Slow | Slower (Rust) | **Fast** (large ecosystem, this is what the reference repo already uses) | **Fast** |
| Windows integration | Poor (fights the "native app" requirement directly) | Poor | Excellent | Good | **Excellent** — both halves are native Windows processes; no VM, no container |
| Debugging | Hard (cross-VM boundary) | Hard | Medium (less tooling maturity than Electron/Node) | Easy (Chrome DevTools in the renderer) | **Easy** — Chrome DevTools for the avatar, standard Python debugger/logging for the brain |
| Packaging | Painful (must bundle/require WSL or Docker Desktop) | Painful | electron-builder-equivalent (tauri-bundler) is solid but younger | **electron-builder is mature and well-documented** | **electron-builder for the shell + PyInstaller (or a bundled venv) for the brain**, launched together via a small native launcher/tray app |
| Maintainability | Low (two upstream projects with divergent release cadences, one WSL-gated) | Low | Medium | High | **High** |
| Future extensibility | Constrained by upstream JARVIS's roadmap and license | Same | Good | Good | **Best** — brain and shell are both owned by the project and can evolve independently; MCP can be bolted on to the brain later without touching the avatar |

**Selected: Architecture E** — a native Windows Electron avatar/voice-output shell (forked from `desktop-mascot-mcp`) paired with a native Windows Python agent/tool-execution backend, communicating over a local WebSocket + REST API on loopback. This is closest to "D" in raw technology (Electron is still the avatar shell) but is listed separately because the defining decision is the **backend language split** (Python brain vs. Node/Electron-only), which the brief's own Part 9 diagram implies (`LLM → Tool selection → MCP/internal tool → Windows action`) and which every credible reference project (JARVIS daemon+sidecar, desktop-mascot-mcp MCP-server+renderer) independently converges on.

### C.2 System diagram

```
┌───────────────────────────────────────────────────────────────────────┐
│                         WINDOWS 10/11 HOST                            │
│                                                                       │
│  ┌─────────────────────────┐        ┌──────────────────────────────┐ │
│  │   AVATAR SHELL (Electron)│◄──────►│      AGENT BRAIN (Python)     │ │
│  │   forked from             │  WS/   │                                │ │
│  │   desktop-mascot-mcp       │  HTTP  │  ┌──────────────────────────┐ │ │
│  │                            │  :8765 │  │  Agent Loop               │ │ │
│  │  • three-vrm renderer      │◄──────►│  │  (LangGraph or hand-      │ │ │
│  │  • transparent, always-    │        │  │   rolled ReAct loop)      │ │ │
│  │    on-top window           │        │  │  Providers: Anthropic /   │ │ │
│  │  • VRMA gesture player     │        │  │  OpenAI / Gemini / Ollama │ │ │
│  │  • lip-sync (audio-driven) │        │  └──────────────┬───────────┘ │ │
│  │  • avatar state machine    │        │                 │             │ │
│  │    (IDLE/LISTENING/        │        │  ┌──────────────▼───────────┐ │ │
│  │     THINKING/SPEAKING/…)   │        │  │  Tool Layer                │ │ │
│  │  • system tray icon        │        │  │  • desktop_control          │ │ │
│  │  • hotkey listener (global)│        │  │    (pywinauto, UIA, Win32)  │ │ │
│  └──────────┬─────────────────┘        │  │  • browser (Playwright)     │ │ │
│             │ plays audio                │  │  • filesystem / terminal    │ │ │
│             │ (TTS output)               │  │  • screenshot + OCR/vision  │ │ │
│             ▼                            │  │  • app launcher              │ │ │
│  ┌─────────────────────────┐            │  └──────────────┬───────────┘ │ │
│  │  Local TTS Engine         │◄───HTTP───┤                 │             │ │
│  │  AivisSpeech (primary)    │  :10101   │  ┌──────────────▼───────────┐ │ │
│  │  or VOICEVOX (fallback)   │           │  │  Memory                     │ │ │
│  └─────────────────────────┘           │  │  SQLite (facts, prefs,      │ │ │
│                                          │  │  conversation summaries)    │ │ │
│  ┌─────────────────────────┐            │  │  + optional local vector    │ │ │
│  │  Speech Input Service     │────────►  │  │    store (Phase 5+)         │ │ │
│  │  • openWakeWord (ONNX)    │  audio/    │  └──────────────┬───────────┘ │ │
│  │  • global hotkey (NumPad+)│  text      │                 │             │ │
│  │  • faster-whisper (STT)   │            │  ┌──────────────▼───────────┐ │ │
│  └─────────────────────────┘            │  │  Personality Config          │ │ │
│                                          │  │  (YAML/JSON — traits, voice, │ │ │
│  ┌─────────────────────────┐            │  │   name — never hard-coded)   │ │ │
│  │  Startup Orchestrator      │           │  └──────────────┬───────────┘ │ │
│  │  (native launcher/tray;    │           │                 │             │ │
│  │   runs at Windows login,   │           │  ┌──────────────▼───────────┐ │ │
│  │   starts brain, waits for  │           │  │  Permission / Authority    │ │ │
│  │   health check, starts     │           │  │  Engine (LOW/MEDIUM/HIGH   │ │ │
│  │   avatar, triggers          │           │  │  risk gating + confirm)    │ │ │
│  │   greeting)                │           │  └────────────────────────────┘ │
│  └─────────────────────────┘           │                                  │
│                                          │  Optional: exposes the same     │
│                                          │  tool layer as an MCP server    │
│                                          │  for Claude Desktop / Cursor /  │
│                                          │  future external integrations   │
│                                          └──────────────────────────────────┘
└───────────────────────────────────────────────────────────────────────┘
```

### C.3 Turn-by-turn data flow (matches brief §15)

```
Hotkey (NumPad+) or wake word "Senjougahara"
        │
        ▼
Avatar shell → POST /activate → Brain
        │
        ▼
Brain starts audio capture, streams to faster-whisper (local, GPU if available)
        │
        ▼
STT text → Agent Loop (system prompt = personality config + memory context)
        │
        ▼
LLM emits either: (a) direct structured reply, or (b) tool_use calls
        │
        ├── tool_use: desktop_control.launch_app("VS Code")
        ├── tool_use: desktop_control.open_path(project_path)
        ├── tool_use: terminal.run("git log --oneline -10")
        │        │
        │        ▼
        │   Permission engine checks risk tier → LOW: auto-execute
        │        │
        │        ▼
        │   Tool result returned to LLM
        ▼
LLM produces final structured output:
   { "text": "...", "emotion": "happy", "animation": "nod", "priority": "normal" }
        │
        ▼
Brain → AivisSpeech HTTP API → WAV/MP3 audio + phoneme timing
        │
        ▼
Brain → Avatar shell (WS): { audio_url, emotion, animation, viseme_track }
        │
        ▼
Avatar: THINKING state → SPEAKING state (lip-sync + gesture) → IDLE
```

---

## Part D — Selected Technologies

| Layer | Technology | Rationale (one line) |
|---|---|---|
| **Agent orchestration** | Python, hand-rolled ReAct-style loop (upgradeable to LangGraph if multi-step planning complexity grows) | Keeps Phase 1 dependency-light; LangGraph adoption is a Phase 6 decision, not a Phase 1 requirement |
| **LLM providers** | Anthropic Claude (primary), OpenAI, Google Gemini, Ollama (local) — provider-agnostic adapter | Matches "local and/or cloud LLMs" requirement; mirrors JARVIS's proven multi-provider router pattern |
| **STT** | `faster-whisper` (CTranslate2, `small`/`medium` model, GPU int8 or fp16) | Fastest local Whisper path on Windows+NVIDIA; MIT license |
| **Wake word** | `openWakeWord` (ONNX) | Free, Windows-native, no API key, competitive accuracy |
| **Global hotkey** | `keyboard` (Python) or a small native AutoHotkey-style listener; Right Ctrl or NumPad+ as default | Must work while unfocused — both work at the OS input-hook level |
| **TTS** | AivisSpeech (primary, Windows-native, best emotional expressiveness) with VOICEVOX-API-compatible fallback | Hot-swappable via a single adapter; matches the brief's `speak(text, emotion, speed, pitch, animation)` interface goal |
| **Avatar renderer** | Electron + Three.js + `@pixiv/three-vrm`, forked from `desktop-mascot-mcp` | Only Windows-proven, MIT-licensed, feature-matching reference implementation found |
| **Avatar animation data** | VRMA format; sourced via VRoid/BOOTH free packs or Mixamo→VRMA conversion | Established pipeline documented in the fork target's own README |
| **Desktop automation** | `pywinauto` (Win32 + UIA backends), `pygetwindow`, `pyperclip`, `subprocess`/`asyncio.subprocess` | Most mature Python Windows automation library; BSD license |
| **Browser automation** | `playwright-python` | Industry standard; Apache-2.0; strong debugging tooling |
| **Screenshot / vision** | `mss` (fast cross-backend screenshot) + the LLM's native vision capability (Claude/GPT-4V/Gemini) for "what's on my screen" queries; Tesseract (`pytesseract`) as a free local OCR fallback | Avoids standing up a separate vision-model server for v1 |
| **Memory** | SQLite (`aiosqlite` or stdlib `sqlite3`) for facts/preferences/summaries; a JSON/YAML personality file is *not* memory and stays separate | Practical v1 architecture with a clear migration path (see §D.1) |
| **MCP** | Python `mcp` SDK, used to *optionally* re-expose the tool layer to external MCP clients (Claude Desktop, Cursor) and to consume community MCP servers (GitHub, calendar) in later phases | Genuine reuse value without forcing MCP onto the low-latency avatar↔brain hot path |
| **IPC (avatar ↔ brain)** | WebSocket (events, streaming state) + local REST (control calls), both on `127.0.0.1`, single port | Simple, debuggable, language-agnostic, matches both reference projects' own choices |
| **Packaging** | `electron-builder` for the avatar shell installer; `PyInstaller` (or a pinned venv shipped alongside) for the brain; a small native launcher (NSIS-generated or a tiny Rust/C# stub) registers Windows Startup and owns the tray icon | Keeps each half's packaging tool idiomatic to its ecosystem |
| **Configuration** | Single `config.yaml` (personality, voice, hotkey, provider keys via env-var references, permission policy) + `.env` for secrets | One human-editable source of truth, consistent with both reference repos |
| **Logging** | Python `logging` (brain, rotating file handler) + `electron-log` (shell) writing to `%APPDATA%\Senjougahara\logs\` | Standard, low-effort, greppable |

### D.1 Memory architecture and migration path

**v1 (Phase 5 in the roadmap, not Phase 1):** a single SQLite database (`memory.db`) with three tables — `facts` (key/value-ish long-term facts extracted from conversation), `preferences` (explicit user settings), and `conversation_log` (rolling window of recent turns, periodically summarized down by the LLM itself to control context size). This is deliberately close to what JARVIS calls its "Vault" but far simpler — no knowledge-graph relationships in v1.

**v2 migration path (Phase 6+, only if needed):** add a local embedding step (e.g., a small sentence-transformer or an API embedding call) and a vector column/sidecar index (SQLite + `sqlite-vec` extension, or a dedicated embedded vector store) for semantic recall across long histories. This is an additive migration — the `facts`/`preferences` tables don't change shape, a new `memory_embeddings` table is added alongside them. Do not build the vector layer in Phase 1; it solves a problem ("I have thousands of conversations and need semantic search over them") the project won't have for months.

---

## Part E — Repository / Fork Strategy

| Repository | Classification | What to do with it |
|---|---|---|
| `rennosuke-haresu/desktop-mascot-mcp` | **FORK** | Fork into `senjougahara/avatar-shell` (or as an `avatar/` subtree in the monorepo — see Part F). This becomes the base for the Electron avatar window, three-vrm rendering, VRMA gesture playback, and the AivisSpeech/VOICEVOX HTTP adapter. Its existing `speak` MCP tool is **replaced/extended** with a local WebSocket server so the Python brain can drive it directly without requiring an MCP-client host (Claude Desktop) to be running — the MCP interface can be kept as a *secondary* entry point for debugging, not the primary control path. |
| `pixiv/three-vrm` | **INTERNAL DEPENDENCY** | Pulled transitively via the fork's `package.json`; pin its version explicitly and re-verify compatibility on any Three.js upgrade. |
| `dscripka/openWakeWord` | **REUSABLE LIBRARY** | `pip install openwakeword`. No vendoring. Custom wake-word model training (Phase 2+) happens in a separate throwaway training script/notebook, not in the shipped repo. |
| `SYSTRAN/faster-whisper` | **REUSABLE LIBRARY** | `pip install faster-whisper`. No vendoring. |
| `pywinauto/pywinauto` | **REUSABLE LIBRARY** | `pip install pywinauto`. No vendoring. |
| `microsoft/playwright-python` | **REUSABLE LIBRARY** | `pip install playwright` + `playwright install chromium`. No vendoring. |
| AivisSpeech / VOICEVOX engines | **EXTERNAL SERVICE** | Installed and run by the *user* (or auto-launched by the startup orchestrator if a portable build is bundled) as a standalone local HTTP server on its own port. Never vendored or embedded in the repo — these are large binary distributions with their own installers and licensing terms. |
| `vierisid/jarvis` | **REFERENCE ONLY** | Do not clone into the working tree. Read (in a browser, or via `git clone` into a scratch/throwaway directory that is explicitly *not* part of the shipped repo and is `.gitignore`d) for architectural patterns: the authority/permission engine's risk-tiering, the sidecar RPC protocol shape, the SQLite vault schema, and the `{text, emotion, animation, priority}` structured-output convention (this convention is explicitly adopted in Part D above). Document any pattern borrowed this way with a code comment citing the inspiration, per the brief's "document every non-obvious architectural decision" instruction — do not copy code verbatim given the RSALv2 license. |
| `not-elm/desktop-homunculus` | **REFERENCE ONLY** | Same treatment — study its MOD system (TypeScript SDK + WebView UI panels) and multi-monitor VRM handling as inspiration for a post-v1 "MOD/plugin" system for community-contributed avatar behaviors, and its dynamic-FPS power-saving approach for the idle-animation performance requirement (§19 of the brief). Do not fork. |
| `open-jarvis/OpenJarvis`, `dmrr35/Open.Jarvis` | **REFERENCE ONLY** | Skim for the skill-catalog abstraction and the "keyless degraded mode" / provider-fallback pattern respectively. Neither is mature or proven enough to depend on directly; re-evaluate in a later phase if the hand-rolled agent loop's tool-registration system needs to grow more formal. |
| `kiskaserver/interactive_assistent` | **DROP** | Not found. Do not reference in the implementation prompt. If the user provides a corrected/private URL, re-run the same due-diligence pass (stars, commits, license, Windows support) before adopting it as a dependency. |

**General fork/merge discipline for Antigravity:** never merge `desktop-mascot-mcp`'s repository history directly into a monorepo without preserving attribution (keep its LICENSE.md, keep a `THIRD_PARTY_NOTICES.md` entry, ideally keep it as a git subtree or submodule rather than a history-losing copy-paste so upstream fixes can be pulled later). Everything under "REUSABLE LIBRARY" is a normal package-manager dependency (`pip`/`npm`) and must never be vendored/copied into the repo's own source tree.

---

## Part F — Directory Structure

```
senjougahara/
├── avatar/                          # Electron app — forked from desktop-mascot-mcp
│   ├── src/
│   │   ├── main/                    # Electron main process
│   │   │   ├── window.ts            # transparent, always-on-top window mgmt
│   │   │   ├── tray.ts              # system tray icon + menu
│   │   │   ├── hotkey.ts            # global hotkey registration (NumPad+/RightCtrl)
│   │   │   ├── bridge-server.ts     # WebSocket + REST server the Python brain talks to
│   │   │   └── mcp-server.ts        # optional: exposes `speak` etc. over MCP too
│   │   ├── renderer/                # Three.js / three-vrm scene
│   │   │   ├── vrm/                 # model loading, VRMA gesture playback
│   │   │   ├── lipsync/             # viseme-driven mouth-shape blending
│   │   │   ├── state-machine.ts     # IDLE/LISTENING/THINKING/SPEAKING/… (from Part D)
│   │   │   └── idle-behaviors.ts    # blink, breathing, glance, cursor-follow
│   │   └── preload/
│   ├── assets/
│   │   ├── models/                  # .vrm files (not committed if licensed)
│   │   └── animations/              # .vrma gesture files
│   ├── package.json
│   └── THIRD_PARTY_NOTICES.md       # carried over from desktop-mascot-mcp fork
│
├── brain/                           # Python agent backend
│   ├── agent/
│   │   ├── loop.py                  # ReAct-style tool-use loop
│   │   ├── providers/               # anthropic.py, openai.py, gemini.py, ollama.py
│   │   └── structured_output.py     # {text, emotion, animation, priority} schema + validation
│   ├── personality/
│   │   ├── loader.py                # loads personality.yaml — never hard-coded strings
│   │   └── profiles/
│   │       └── senjougahara.yaml    # example profile; swappable
│   ├── memory/
│   │   ├── db.py                    # SQLite connection/schema management
│   │   ├── facts.py
│   │   ├── preferences.py
│   │   └── conversation_log.py
│   ├── speech/
│   │   ├── stt.py                   # faster-whisper wrapper
│   │   ├── wakeword.py              # openWakeWord wrapper
│   │   └── tts.py                   # AivisSpeech/VOICEVOX HTTP adapter (engine-agnostic)
│   ├── tools/
│   │   ├── desktop_control.py       # pywinauto/UIA: launch, focus, type, click
│   │   ├── filesystem.py
│   │   ├── terminal.py              # subprocess execution, output capture
│   │   ├── browser.py               # Playwright wrapper
│   │   ├── screenshot.py            # mss + optional pytesseract OCR
│   │   └── registry.py              # tool registration/dispatch table
│   ├── permissions/
│   │   ├── policy.py                # LOW/MEDIUM/HIGH risk classification
│   │   └── policy.yaml              # user-editable risk-tier overrides
│   ├── mcp/
│   │   └── server.py                # optional: re-expose tools/ as an MCP server
│   ├── bridge/
│   │   └── client.py                # WebSocket/REST client talking to avatar/bridge-server.ts
│   ├── startup/
│   │   └── state_machine.py         # boot sequence + readiness checks (brief §5)
│   ├── config.py                    # loads config.yaml + .env
│   ├── main.py                      # entrypoint
│   └── requirements.txt
│
├── launcher/                        # Small native startup orchestrator + Windows Startup hook
│   ├── launcher.py (or a compiled stub)
│   └── install_startup.ps1          # registers Run key / Scheduled Task
│
├── config/
│   ├── config.example.yaml
│   └── .env.example
│
├── shared/
│   └── schemas/                     # JSON schema for the bridge protocol (avatar ⇄ brain),
│                                     # kept in one place so both TS and Python validate the same shape
│
├── docs/
│   ├── ARCHITECTURE.md              # long-form version of this report's Part C
│   ├── SETUP.md
│   └── PERMISSIONS.md
│
├── scripts/
│   ├── dev.ps1                      # runs avatar + brain together in dev mode
│   └── build.ps1
│
├── .gitignore
├── LICENSE
├── THIRD_PARTY_NOTICES.md           # aggregate notices for every forked/vendored piece
└── README.md
```

Note: this is a proposed structure, not a mandate — Antigravity should adapt file-level detail as it inspects the forked `desktop-mascot-mcp` codebase's actual internal layout, but the **top-level `avatar/` / `brain/` / `launcher/` / `config/` / `shared/` split should be preserved**, since it directly maps to the process/IPC boundary described in Part C.

---

## Part G — Dependency Matrix

| Component | Language | Package manager | Runtime | Key dependencies | GPU | Ports | Background process? |
|---|---|---|---|---|---|---|---|
| Avatar shell | TypeScript | npm | Node.js (bundled via Electron) | `electron`, `three`, `@pixiv/three-vrm`, `ws` | Yes — WebGL (integrated GPU is sufficient; discrete GPU improves idle-render headroom) | Bridge server: `127.0.0.1:8765` (configurable) | Yes — persistent while the companion is "on" |
| Agent brain | Python 3.11+ | pip (venv) | CPython | `anthropic`, `openai`, `google-generativeai`, `ollama` (client), `pywinauto`, `playwright`, `faster-whisper`, `openwakeword`, `mss`, `pytesseract` (optional), `mcp`, `pyyaml`, `python-dotenv`, `aiosqlite`/`sqlite3` | Optional — `faster-whisper` benefits from CUDA; falls back to CPU int8 | Talks out to avatar's `:8765`; TTS engine's `:10101`/`:50021` | Yes — this is the always-on brain |
| TTS engine (AivisSpeech/VOICEVOX) | C++/Python (upstream) | Installed via upstream installer, not a project dependency | Standalone Windows executable | — | Optional — GPU accelerates synthesis but CPU is usable | `10101` (AivisSpeech default) / `50021` (VOICEVOX default) | Yes — launched by the startup orchestrator or manually |
| Launcher/orchestrator | Python or a thin compiled stub | pip / (optional PyInstaller) | Native | `psutil` (health checks), OS scheduler APIs | No | — | Runs at login, supervises the above, exits after handoff or stays resident for tray icon |
| Browser automation | Python | pip (`playwright install`) | Chromium (downloaded by Playwright) | — | No | — | Launched on demand by the `browser` tool, not persistent |

**Runtime coherence check (brief §13):** the stack uses exactly **two** primary runtimes — **Node.js** (for the Electron avatar shell, because the only strong reference implementation is Electron/TS) and **Python** (for the agent brain and all Windows/browser automation, because that ecosystem is strongest there). No Rust, no Go, no Bun, no C++ build step is required for the shipped product — Bun (JARVIS) and Rust (desktop-homunculus) were both deliberately avoided as *runtime* dependencies precisely to keep this coherent, even though both appear in reference/inspiration projects. PyInstaller is a build-time tool only, not a third runtime.

**License summary:** MIT (`desktop-mascot-mcp` fork base, `three-vrm`, `faster-whisper`), Apache-2.0 (`openWakeWord`, `playwright`), BSD-3-Clause (`pywinauto`). No GPL/AGPL dependencies in the core path. AivisSpeech/VOICEVOX and their voice models each carry their own terms (verify per chosen voice model before any commercial distribution — this matters even for a personal project if the character voice is ever shared publicly).

---

## Part H — Runtime Architecture

### H.1 Process startup sequence (implements brief §5 and §17)

```
1. Windows Startup (Run key or Scheduled Task, created by launcher/install_startup.ps1)
        │
        ▼
2. Launcher process starts
        │
        ├─→ 2a. Checks/launches TTS engine (AivisSpeech) if not already running
        │        Health check: GET http://127.0.0.1:10101/version
        │
        ├─→ 2b. Starts Brain (Python) as a subprocess
        │        Brain internally runs its own startup state machine:
        │           CHECKING_LLM_PROVIDER → CHECKING_STT → CHECKING_TTS →
        │           CHECKING_DESKTOP_BRIDGE → LOADING_MEMORY → LOADING_PERSONALITY → READY
        │        Brain exposes GET /health once READY
        │
        ├─→ 2c. Waits for Brain /health == READY (bounded retry, e.g. 30s timeout with backoff)
        │
        ├─→ 2d. Starts Avatar (Electron) process
        │        Avatar connects its WS client to Brain's bridge server
        │
        └─→ 2e. Once Avatar reports "connected" AND this is a cold boot (not a
                 mid-session service restart — tracked via a small state file /
                 IPC flag, not just process existence), Brain triggers ONE
                 greeting: emits {text: "...", emotion: "happy", animation: "greeting"}
        │
        ▼
3. System enters steady state: Avatar in IDLE animation loop, Brain listening
   for hotkey/wake-word activation events
```

**Why the greeting must not repeat:** the brief is explicit that "the greeting must not happen every time the system briefly restarts a service." This is solved by having the *Launcher* — not the Brain and not the Avatar individually — own a small persisted `session_state.json` (`{ "greeted_at": <timestamp or null> }`) written to `%LOCALAPPDATA%\Senjougahara\`. The greeting only fires when `greeted_at` is null or older than a configurable threshold (default: a new calendar day, or N hours of total inactivity) — a Brain crash-and-restart 30 seconds later does not re-trigger it, but genuinely coming back to the PC "the next morning" does.

### H.2 IPC mechanism decision

- **Avatar ⇄ Brain:** WebSocket for streaming/event traffic (state changes, audio-ready notifications) + plain REST for one-shot control calls (activate, get-status). Both on loopback only (`127.0.0.1`), never bound to `0.0.0.0`. JSON payloads validated against a shared schema kept in `shared/schemas/` so both the TypeScript and Python sides can validate the same message shapes without drifting.
- **Brain → TTS engine:** REST (the engine's own VOICEVOX-compatible HTTP API).
- **Brain → LLM providers:** each provider's own SDK/HTTPS API (cloud) or local HTTP (Ollama).
- **Brain → MCP (optional):** the same `tools/` implementations are wrapped and exposed via `mcp/server.py` using stdio or SSE transport, purely as an *additional* entry point for external MCP clients — this is never the path used for the hotkey→speech→action→speech loop, keeping the latency-critical path free of MCP's extra indirection.
- Rejected: a full message bus (Redis/NATS/etc.) — unnecessary infrastructure for two local processes on one machine, explicitly against the brief's "avoid unnecessarily complicated infrastructure" instruction. Rejected: named pipes — WebSocket/HTTP is equally fast on loopback and vastly easier to debug (any browser or `curl`/Postman can inspect it).

---

## Part I — Security / Permission Model

Directly implements brief §16, informed by `vierisid/jarvis`'s authority-engine pattern (studied as reference, not copied as code).

### I.1 Risk tiers

| Tier | Default behavior | Example actions |
|---|---|---|
| **LOW** | Execute automatically, log to audit trail | Opening an already-installed application; reading files; taking a screenshot; searching the filesystem; navigating to a URL; answering questions |
| **MEDIUM** | Configurable — default is "notify and proceed" (avatar announces the action before/while doing it), user can flip to "always ask" per action-type in `permissions/policy.yaml` | Writing/creating a new file; closing a window; filling a web form; running a read-only shell command (`git log`, `dir`) |
| **HIGH** | Always require explicit confirmation (voice "yes"/"confirm" or a click on an avatar-rendered confirmation prompt), never auto-approved regardless of policy overrides | Deleting files; installing/uninstalling software; running commands with elevation or that mutate system state (`git push --force`, `rm`/`del` on non-temp paths, registry edits); sending a message/email on the user's behalf; anything resembling a purchase; modifying security/firewall/network settings |

### I.2 Enforcement mechanics

- Every entry in `tools/registry.py` is tagged with a risk tier at registration time (`@tool(risk="LOW")`), not decided by the LLM at call time — the model **proposes** a tool call, the **permission engine decides** whether it needs confirmation, mirroring the brief's explicit warning that "dangerous operations should not execute blindly" regardless of what the agent's reasoning concluded.
- HIGH-risk confirmations block the agent loop until the user responds (via voice, or a rendered confirm/cancel affordance on the avatar overlay); a timeout auto-cancels (fails safe) rather than auto-approving.
- All tool executions (any tier) are appended to an audit log (`%LOCALAPPDATA%\Senjougahara\logs\audit.jsonl`) with timestamp, tool name, arguments, risk tier, and outcome — cheap insurance and directly useful for debugging "why did she do that."
- `policy.yaml` lets the user re-tier specific actions (e.g., someone comfortable with auto-file-deletion in a scratch folder can lower that specific action's tier) but the HIGH tier's confirmation requirement is **not overridable to fully silent** — only the specific action list moves between tiers, and a small hard-coded "never auto-approve" set (destructive filesystem operations outside a sandboxed workspace, OS security settings, anything sending data externally on the user's behalf) stays fixed regardless of policy file contents, so a compromised or malformed config file cannot silently disable all safety gating.
- Screen/context awareness ("what's on my screen") is itself LOW risk (read-only) but the *decision to take a screenshot* should still be visible to the user (a brief avatar animation/icon change) rather than fully silent background capture, for trust/transparency reasons — this is a UX choice, not just a security one, and directly supports the brief's "prioritize reliability and privacy" instruction for passive listening/observation features generally.

---

## Part J — Development Roadmap

Matches brief §21 exactly in spirit; each phase should be independently demoable and independently useful.

**Phase 1 — Minimal assistant.** Text input only (no voice yet). Brain: agent loop + one LLM provider (start with Anthropic) + personality loader + 2-3 trivial tools (open an app, read a file). Avatar: forked `desktop-mascot-mcp` shell running as-is, driven by the Brain's WS bridge instead of MCP, static idle pose, TTS wired up via AivisSpeech. Goal: type "open notepad," see and hear a response.

**Phase 2 — Voice input.** Add global hotkey (start with Right Ctrl or NumPad+ — see Part K rationale), `faster-whisper` STT, and `openWakeWord` wake-word detection (ship with a stock/generic phrase first — e.g. "Hey Computer" — and treat training a custom "Senjougahara" wake model as a fast-follow, not a Phase 2 blocker). Both activation modes configurable (hotkey-only / wake-word-only / both).

**Phase 3 — Desktop control.** `pywinauto`-based window/app control, `playwright` browser tool, filesystem search, terminal execution, screenshot capture. Wire in the permission/risk-tier engine from Part I before shipping any MEDIUM/HIGH-risk tool.

**Phase 4 — Advanced avatar.** Full emotion set beyond the base six, richer gesture library (source additional VRMA via Mixamo conversion), idle micro-behaviors (blink timing, breathing, cursor-follow glance), improved lip-sync (viseme-accurate rather than amplitude-only), the full state machine from Part C's diagram (THINKING/TOOL_EXECUTION/SURPRISED/CONFUSED/etc., not just IDLE/SPEAKING).

**Phase 5 — Memory.** SQLite-backed facts/preferences/conversation-log per Part D.1; personality-aware summarization of long conversations to keep context bounded; "remember this" as an explicit user-invokable action in addition to automatic extraction.

**Phase 6 — Advanced autonomy.** Proactive suggestions (only if the user opts in — this is exactly the kind of "always-listening" feature the brief says not to assume is necessary), scheduled/recurring tasks, and — only if genuinely needed by then — evaluate whether the vector-memory migration (Part D.1) or a heavier orchestration framework (LangGraph) earns its complexity cost.

**Explicit non-goal for v1-v6:** multi-machine sidecars, a visual workflow builder, Telegram/Discord channels, and a multi-agent hierarchy — all present in `vierisid/jarvis` — are out of scope. They solve problems ("control machines I'm not sitting at," "give non-technical teammates a chat interface into my automations") this single-user desktop-companion project does not have.

---

## Part K — Activation Key Recommendation

**Default: Right Ctrl (held or double-tapped, configurable), with NumPad+ as the documented alternative.**

Reasoning: Right Ctrl is present on effectively every physical keyboard (unlike NumPad+, which is absent on laptops and compact/TKL keyboards — a real risk for a "desktop companion" that should work identically on a laptop) and is almost never independently bound by games or productivity software the way Right Ctrl's neighbor keys can be. F13-F24 are excellent (zero collision risk, since most keyboards don't physically have them and no software defaults to them) but are **not present on most consumer keyboards**, making them a poor *default* even though they're worth documenting as a power-user option for people with programmable keyboards (many mechanical keyboards can remap a spare key to send F13). NumPad+ is a fine secondary default specifically for full-size-keyboard desktop users, and is what the brief's own example flow uses, so it should be offered as an easy one-click preset in settings, with Right Ctrl as the true out-of-box default given the laptop-compatibility concern. All three (and any other key) should be user-remappable via a single `hotkey:` field in `config.yaml`, captured through a native global low-level keyboard hook (works regardless of window focus, satisfying the brief's "must work globally" requirement) — on Windows this is a `WH_KEYBOARD_LL` hook (accessible from Python via the `keyboard` package, or natively in the Electron main process via a small native module) rather than a per-application accelerator, which by definition only fires when that application has focus.

---

# ANTIGRAVITY IMPLEMENTATION PROMPT

*Copy everything below this line into Antigravity as a single prompt.*

---

## Project Objective

Build **Senjougahara** — a persistent, AI-powered anime desktop companion for Windows 10/11. A 3D VRM anime character lives on the desktop as a transparent, always-on-top, movable window. The user activates her via a global hotkey or a wake word, speaks a request, and she performs **real actions on the computer** (launching applications, controlling windows, browsing the web, running terminal commands, reading files, taking and reasoning about screenshots) — not just describing what to do. She responds with natural speech (local TTS), lip-synced animation, contextual facial expressions/gestures, and remembers relevant context across sessions. This is not a chatbot with an avatar bolted on: the avatar is the interface, an LLM-driven agent is the brain, a Windows automation layer is the hands, local speech recognition is the ears, and local TTS is the voice — all separately swappable pieces of one cohesive system.

## Selected Architecture (Architecture E — do not deviate without strong justification)

Two native Windows processes communicating over a local WebSocket/REST bridge on `127.0.0.1`:

1. **`avatar/`** — an Electron + Three.js + `@pixiv/three-vrm` desktop shell, forked from `rennosuke-haresu/desktop-mascot-mcp`, rendering the transparent always-on-top VRM character, playing TTS audio with lip-sync, running the avatar state machine (IDLE/LISTENING/THINKING/SPEAKING/etc.), owning the system tray icon, and registering the global hotkey.
2. **`brain/`** — a Python 3.11+ agent backend running the LLM tool-use loop, speech-to-text (`faster-whisper`), wake-word detection (`openWakeWord`), TTS orchestration (calling a local AivisSpeech/VOICEVOX-compatible HTTP engine), Windows desktop automation (`pywinauto`), browser automation (`playwright`), filesystem/terminal tools, SQLite-backed memory, a YAML-driven personality layer, and a risk-tiered permission/confirmation engine.

No WSL, no Docker, no Linux dependency anywhere in the shipped runtime path. No Rust, no Go, no Bun runtime dependency — only Node.js (for Electron) and Python (for the brain) as the two coherent runtimes, per the dependency-coherence requirement below.

## Repositories

### Authoritative (fork this)

- **`https://github.com/rennosuke-haresu/desktop-mascot-mcp`** — MIT licensed. This is the base for `avatar/`. It already implements: an Electron transparent always-on-top window; Three.js + `@pixiv/three-vrm` rendering; a VOICEVOX-compatible TTS HTTP client (works with both VOICEVOX and AivisSpeech, since AivisSpeech implements the same API surface); a 6-emotion expression system; VRMA gesture playback with an `animations.json` registry; window/camera position persistence; and an MCP server exposing a `speak(text, emotion, animation)` tool. **Fork it, preserve its `LICENSE.md`, keep its `THIRD_PARTY_NOTICES.md` and extend it (don't replace it).** Add a WebSocket + REST bridge server (`avatar/src/main/bridge-server.ts`) so the Python brain can drive the avatar directly (send speak/emotion/animation/state-change commands, receive activation events) without requiring an MCP-client host to be running. Keep the existing MCP entry point as a secondary/debug interface — do not remove it, since it's a working MIT-licensed reference implementation worth preserving for parity testing.

### Reference only (read for architecture patterns, do not clone into the shipped repo, do not copy code — RSALv2 is not a permissive license)

- **`https://github.com/vierisid/jarvis`** — Read for: (1) the "authority engine" risk-tiered permission model with an audit trail; (2) the structured `{text, emotion, animation, priority}` LLM output convention (this convention IS adopted — reimplement your own `structured_output.py` schema inspired by it, do not import their code); (3) the daemon/sidecar RPC protocol shape as inspiration for the avatar↔brain bridge; (4) their SQLite "Vault" memory schema as inspiration for `memory/`. Do **not** attempt to install, run, or depend on this project's npm/bun packages — its daemon has no native Windows support (requires WSL2/Docker) and its license (Jarvis Source Available License 2.0 / RSALv2) is not compatible with unrestricted forking. If you clone it locally to read source, put it outside the project's git tree (e.g., a `.reference/` folder added to `.gitignore`, or read it directly via the GitHub web UI) so no trace of it enters the shipped repository or its git history.

### Inspiration (optional light reading, no code reuse)

- **`https://github.com/not-elm/desktop-homunculus`** — Rust/Bevy VRM mascot, MOD system, multi-monitor support, dynamic FPS power-saving. Worth 20 minutes of reading for the idle-performance and future-plugin-system ideas; not a dependency.
- **`https://github.com/open-jarvis/OpenJarvis`** and **`https://github.com/dmrr35/Open.Jarvis`** — skim only if the hand-rolled tool-registration system in `brain/tools/registry.py` needs a more formal "skill catalog" pattern later; not required for the phases below.

### Explicitly dropped

- The user-suggested `kiskaserver/interactive_assistent` could not be located on GitHub at research time and must **not** be referenced, cloned, or assumed to exist. If Antigravity independently finds a plausible match, verify license/maintenance/Windows-support before using it, and flag the discrepancy to the user rather than silently substituting it.

## Directory Structure

Create this top-level layout (adapt internal file-level detail to what the forked `desktop-mascot-mcp` codebase actually contains after inspection, but preserve the top-level split):

```
senjougahara/
├── avatar/                 # forked desktop-mascot-mcp (Electron + three-vrm)
│   ├── src/main/            # main process: window, tray, hotkey, bridge-server, mcp-server
│   ├── src/renderer/        # VRM scene, lipsync, state-machine, idle-behaviors
│   ├── src/preload/
│   └── assets/{models,animations}/
├── brain/                  # Python agent backend
│   ├── agent/{loop.py, providers/, structured_output.py}
│   ├── personality/{loader.py, profiles/senjougahara.yaml}
│   ├── memory/{db.py, facts.py, preferences.py, conversation_log.py}
│   ├── speech/{stt.py, wakeword.py, tts.py}
│   ├── tools/{desktop_control.py, filesystem.py, terminal.py, browser.py, screenshot.py, registry.py}
│   ├── permissions/{policy.py, policy.yaml}
│   ├── mcp/server.py
│   ├── bridge/client.py
│   ├── startup/state_machine.py
│   ├── config.py, main.py, requirements.txt
├── launcher/                # startup orchestrator + Windows Startup registration
├── config/{config.example.yaml, .env.example}
├── shared/schemas/          # bridge protocol JSON schemas, validated by both sides
├── docs/{ARCHITECTURE.md, SETUP.md, PERMISSIONS.md}
├── scripts/{dev.ps1, build.ps1}
├── .gitignore, LICENSE, THIRD_PARTY_NOTICES.md, README.md
```

## Package Managers, Runtimes, Dependencies

- **`avatar/`**: npm, Node.js (Electron-bundled). Core deps: `electron`, `three`, `@pixiv/three-vrm`, `ws`, plus whatever `desktop-mascot-mcp` already declares — inspect its `package.json` before adding anything new, and don't duplicate a capability it already has.
- **`brain/`**: pip, Python 3.11+, a dedicated virtual environment (`brain/.venv`, gitignored). Core deps: `anthropic`, `openai`, `google-generativeai`, `ollama`, `pywinauto`, `playwright`, `faster-whisper`, `openwakeword`, `mss`, `pytesseract` (optional/lazy import), `mcp`, `pyyaml`, `python-dotenv`, `keyboard` (or equivalent for the global hotkey hook if not handled in Electron main), `aiosqlite`, `websockets`, `fastapi`+`uvicorn` (or an equally light HTTP/WS server — do not pull in a heavy web framework for a two-endpoint local bridge).
- **External, not vendored:** AivisSpeech (or VOICEVOX) engine, installed separately by the user or auto-launched by `launcher/` if bundled as a portable distribution; Playwright's browser binaries (`playwright install chromium`).
- **Do not introduce:** Rust, Go, Bun, Docker, WSL, or a message-bus dependency (Redis/NATS/etc.) anywhere in the default runtime path. If a future phase genuinely needs one of these, document the justification in `docs/ARCHITECTURE.md` before adding it.

## Environment Variables (`.env`, gitignored; `.env.example` committed)

```
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GOOGLE_API_KEY=
OLLAMA_BASE_URL=http://localhost:11434
TTS_ENGINE_BASE_URL=http://127.0.0.1:10101       # AivisSpeech default; VOICEVOX default is :50021
TTS_SPEAKER_ID=
BRIDGE_HOST=127.0.0.1
BRIDGE_PORT=8765
```

## Development & Build Setup

1. Clone/fork `desktop-mascot-mcp` into `avatar/`; run its existing `npm install`; confirm the unmodified fork still runs (`npm run build:electron && npm run start:electron`) with a placeholder VRM model before making any changes — this validates the base is healthy before you build on top of it.
2. Set up `brain/.venv`; `pip install -r requirements.txt`; `playwright install chromium`.
3. Install and run AivisSpeech (or VOICEVOX) locally; verify `GET /version` on its port responds before wiring the TTS adapter.
4. `scripts/dev.ps1` should start the brain (`python brain/main.py`) and the avatar (`npm --prefix avatar run start:electron`) together for local development, with clear console output distinguishing which process logged what.
5. Packaging (later phase): `electron-builder` for `avatar/` → installer/portable `.exe`; `PyInstaller` (or a pinned, self-contained venv copy) for `brain/`; `launcher/` ties both together and registers Windows Startup (Run key or Scheduled Task — prefer Scheduled Task for more reliable "run at logon with a short delay" semantics).

## Process & IPC Architecture

Implement exactly the startup sequence and bridge protocol described in this research (Part H of the accompanying report): Launcher → TTS engine health check → Brain subprocess → Brain internal startup state machine (CHECKING_LLM_PROVIDER → CHECKING_STT → CHECKING_TTS → CHECKING_DESKTOP_BRIDGE → LOADING_MEMORY → LOADING_PERSONALITY → READY) → Avatar process → WS handshake → **one** greeting, gated by a persisted `session_state.json` (`%LOCALAPPDATA%\Senjougahara\`) so restarting a crashed service never re-triggers a redundant greeting, but a genuine "new session" (new day / long idle gap, configurable) does. Avatar ⇄ Brain communicate over WebSocket (streaming/events) + REST (control calls) on `127.0.0.1:8765` (configurable), validated against shared JSON schemas in `shared/schemas/`. Do not introduce a message bus or named pipes; do not bind the bridge to any interface other than loopback.

## Avatar Integration

Build on `desktop-mascot-mcp`'s existing three-vrm renderer and VRMA gesture system. Implement the full avatar state machine: `IDLE, LISTENING, THINKING, TOOL_EXECUTION, SPEAKING, HAPPY, CONFUSED, SURPRISED, ANNOYED, SLEEPING, GREETING, GOODBYE, ERROR`. The LLM never controls animation directly — it emits a structured `{text, emotion, animation, priority}` object (schema owned by `brain/agent/structured_output.py`, mirrored in `shared/schemas/`), and the avatar's state machine interprets that into concrete animation/expression transitions. Idle behaviors (breathing, blinking, occasional glance, cursor-following where practical) should run continuously and independently of the state machine's "big" states, and should reduce render/update frequency while idle to conserve GPU (dynamic FPS throttling — `desktop-homunculus` is worth a glance for this specific technique).

## STT / Wake-Word / Hotkey Integration

- STT: `faster-whisper`, default model size `small` or `medium` (configurable), GPU (CUDA int8/fp16) with automatic CPU int8 fallback if no CUDA device is detected at startup.
- Wake word: `openWakeWord`, ship with a stock/generic phrase for v1 (do not block Phase 2 on training a custom "Senjougahara" model — treat custom wake-word training as a documented fast-follow task with its own short how-to in `docs/SETUP.md`).
- Hotkey: global low-level keyboard hook, default **Right Ctrl** (fallback/alternative preset: NumPad+), fully remappable via `config.yaml`'s `hotkey:` field, must fire regardless of which application currently has focus.
- All three (hotkey-only / wake-word-only / both) must be independently toggleable in config.

## TTS Integration

`brain/speech/tts.py` implements a single adapter class with an interface matching `speak(text, emotion, speed, pitch, animation)`, internally translating `emotion` into whatever style/intonation parameters the underlying VOICEVOX-compatible API exposes, and calling out over HTTP to `TTS_ENGINE_BASE_URL`. It must be trivially possible to point this at AivisSpeech or VOICEVOX (or a future engine implementing the same API shape) purely via config, with zero code changes to the agent loop or avatar.

## Agent / LLM Integration

`brain/agent/loop.py` implements a ReAct-style tool-use loop: system prompt built from the active personality profile (`personality/profiles/*.yaml`) + relevant memory context, calling into `brain/agent/providers/*` for the configured LLM (Anthropic default, OpenAI/Gemini/Ollama as swappable alternatives via one config field), looping on tool calls until the model produces a final structured `{text, emotion, animation, priority}` response, which is then sent to TTS and the avatar bridge. **Do not hard-code personality, character name, or voice anywhere outside `personality/` and `config/`** — the character identity must be swappable by editing config alone, per the brief's explicit requirement.

## Desktop-Control / Browser Integration

`brain/tools/desktop_control.py` wraps `pywinauto` (both `win32` and `uia` backends available, chosen per-target as needed) for launching applications, focusing/moving/resizing windows, sending keystrokes, and reading window/control state. `brain/tools/browser.py` wraps `playwright-python` for navigation, clicking, form-filling, and content extraction. `brain/tools/filesystem.py` and `terminal.py` provide sandboxed-by-default file search/read/write and subprocess execution respectively. `brain/tools/screenshot.py` uses `mss` for capture and either the active LLM's native vision capability or `pytesseract` for OCR, used for "what's on my screen" / "what's this error" style requests. Every tool function is registered in `brain/tools/registry.py` with an explicit risk tier (LOW/MEDIUM/HIGH) at definition time — this tier is metadata the permission engine reads, not something the LLM decides at call time.

## Memory Architecture

Phase 5 (not Phase 1): SQLite database (`brain/memory/memory.db`, gitignored, lives in `%LOCALAPPDATA%\Senjougahara\`) with `facts`, `preferences`, and `conversation_log` tables as described in this research's Part D.1. Do not build a vector/embedding layer in early phases — it is an explicit, additive Phase 6+ migration (add a `memory_embeddings` table alongside the existing ones; do not restructure what's already there) to be undertaken only if genuinely needed.

## MCP Architecture

`brain/mcp/server.py` optionally re-exposes the same `tools/` implementations via the MCP Python SDK (stdio or SSE transport) so external MCP clients (Claude Desktop, Cursor, etc.) can also drive the same desktop-control/filesystem/browser tools during development and debugging, and so future external integrations (GitHub, calendar) can be added by consuming existing community MCP servers instead of writing bespoke API clients. MCP is **never** the transport for the avatar↔brain hot path (hotkey→STT→agent→TTS→avatar) — that stays on the plain WebSocket/REST bridge for latency and simplicity.

## Startup Behavior

Implement exactly as specified in "Process & IPC Architecture" above and Part H of the accompanying research report. The greeting fires exactly once per genuine session (not per service restart), gated by the persisted `session_state.json`.

## Personality System

`personality/profiles/senjougahara.yaml` (or whatever the user names it) holds: character name, core traits (calm, intelligent, dryly sarcastic, elegant, affectionate-but-restrained, occasionally teasing, capable of serious professional register), speech style notes, default voice/speaker ID, and default emotion baseline. `personality/loader.py` is the **only** place that reads this file into the system prompt — no other module may embed character-specific strings. Swapping the active profile must be a one-line config change.

## Avatar State Machine

As specified above under "Avatar Integration" — implement all listed states, driven exclusively by the structured LLM output plus system-level events (activation, tool-execution-start/end, error), never by free-form LLM text parsing.

## Security Model

Implement the three-tier risk model (LOW auto-execute / MEDIUM notify-and-proceed-by-default-but-configurable / HIGH always-confirm-and-never-silently-overridable) exactly as specified in Part I of the accompanying research report, including: per-tool risk tagging at registration time, an audit log (`audit.jsonl`) recording every tool execution regardless of tier, a fixed "never auto-approve" action set that `policy.yaml` cannot override, and fail-safe (cancel, don't execute) behavior on confirmation timeout.

## Logging

Python `logging` with a rotating file handler in `brain/`, writing to `%APPDATA%\Senjougahara\logs\brain.log`; `electron-log` (or equivalent) in `avatar/`, writing to `%APPDATA%\Senjougahara\logs\avatar.log`. Both should log tool executions, state transitions, and errors at appropriate levels; avoid logging raw API keys or full conversation transcripts at default verbosity.

## Configuration

Single `config/config.yaml` (personality profile selection, hotkey binding, wake-word toggle, LLM provider selection, TTS engine URL/speaker, memory settings, permission policy overrides) plus `.env` for secrets, per the schema sketched above. `config.example.yaml` and `.env.example` are committed; the real files are gitignored.

## Testing Strategy

- `avatar/`: unit tests for the state machine transition logic (pure functions, easy to test in isolation) and the bridge protocol message parsing; manual/visual verification for rendering (VRM loading, lip-sync timing) since that's inherently visual.
- `brain/`: unit tests for `structured_output.py` schema validation, `permissions/policy.py` risk-tier logic (this is safety-critical — test it thoroughly, including the "policy file cannot override the fixed never-auto-approve set" behavior), and each `tools/` function against mocked `pywinauto`/`playwright` calls. Integration test for the full startup state machine (mocking the TTS/LLM/STT health checks) to verify the greeting-gating logic specifically, since that's an easy thing to get subtly wrong.
- End-to-end: a scripted "type a request, verify the expected tool call sequence and structured output shape" test harness that doesn't require actual audio hardware, for CI-friendly regression testing; real voice/avatar verification remains manual.

## Implementation Phases

Follow the six-phase roadmap from Part J of the accompanying research report exactly: **Phase 1** minimal text-only assistant (agent loop + one LLM provider + personality + 2-3 tools + forked avatar shell + TTS); **Phase 2** voice input (hotkey + STT + wake word, both toggleable); **Phase 3** desktop control (Windows automation + browser + filesystem + terminal + screenshots, with the permission engine wired in before any MEDIUM/HIGH tool ships); **Phase 4** advanced avatar (full emotion/gesture set, idle micro-behaviors, complete state machine, better lip-sync); **Phase 5** memory (SQLite facts/preferences/conversation-log); **Phase 6** advanced autonomy (proactive suggestions opt-in, scheduled tasks, and only then reassess whether vector memory or a heavier orchestration framework is actually needed). Do not attempt to build all phases at once or let Phase 1 balloon into a rewrite of later phases' scope.

## Standing Instructions (apply throughout every phase)

1. **Inspect every cloned/forked repository before modifying anything** — read its README, `package.json`/`requirements.txt`, build files, and LICENSE before writing a line of new code against it.
2. Read relevant upstream source (not just docs) before extending `desktop-mascot-mcp` — understand its existing IPC/window/rendering code before adding the bridge server alongside it.
3. **Do not blindly copy repositories together.** `desktop-mascot-mcp` is forked with care (preserve its license and structure); `vierisid/jarvis` and other reference-only projects are never cloned into the shipped tree and never code-copied, only read for pattern inspiration, which must be documented via a code comment citing the source of the idea (not the code).
4. **Preserve upstream functionality wherever practical** — don't rip out `desktop-mascot-mcp`'s existing MCP `speak` tool just because the new WebSocket bridge is the primary path; keep both working.
5. **Prefer adapters/interfaces over tight coupling** — the TTS adapter, the LLM provider adapter, and the personality loader are the three clearest examples; follow the same pattern for anything else that might reasonably be swapped later.
6. **Keep avatar, voice, STT, agent, and desktop-control layers modular** — each should be independently testable and independently replaceable without touching the others' internals, communicating only through the defined bridge protocol / tool interfaces.
7. **Use existing implementations when already correct** — don't reimplement VRM loading, Whisper inference, or Windows UI Automation from scratch when `three-vrm`, `faster-whisper`, and `pywinauto` already solve those problems well.
8. **Resolve dependency conflicts deliberately** — if `desktop-mascot-mcp`'s pinned `three`/`three-vrm` versions conflict with a newer feature you need, document the tradeoff and the resolution in `docs/ARCHITECTURE.md` rather than silently forcing a version bump.
9. **Remove redundant dependencies** — if a capability `desktop-mascot-mcp` already provides gets accidentally reimplemented, delete the duplicate.
10. **Do not create unnecessary microservices** — the two-process (avatar/brain) split is the intended granularity; do not further split the brain into multiple network services without a concrete, documented reason.
11. **Prefer local communication** — loopback WebSocket/REST only; no cloud relay for the avatar↔brain hot path.
12. **Ensure the resulting architecture is Windows-first** — no feature should require WSL, Docker, or a Linux-only tool to function in the default configuration.
13. **Document every non-obvious architectural decision** in `docs/ARCHITECTURE.md`, especially anywhere this prompt's guidance had to be adapted based on what inspecting the actual forked codebase revealed.
14. **Build incrementally and verify each subsystem before moving on** — confirm the forked avatar shell runs unmodified before touching it; confirm the brain's health check works before wiring the avatar bridge; confirm text-only Phase 1 works fully before adding voice in Phase 2.
15. **Maintain a clean Git history** — meaningful, scoped commits; the fork of `desktop-mascot-mcp` should be a clean starting commit (or subtree/submodule) before any project-specific changes begin, so the diff against upstream stays reviewable.

## First-Run Experience to Validate

After Phase 2 is complete, this exact flow must work end-to-end: Windows boots → Senjougahara launches automatically → the anime character appears on the desktop, idle → the user presses the configured hotkey (default Right Ctrl) → the character visibly reacts (state → LISTENING) → the microphone activates → the user says a greeting (any language the configured STT model supports — Whisper is multilingual) → STT transcribes it → the agent loop processes it with the active personality → a structured response with emotion/animation is produced → local TTS speaks it → the avatar lip-syncs and gestures appropriately → the character returns to IDLE. This is the acceptance test for Phase 2; do not consider voice activation "done" until this flow works reliably, including the case where the hotkey is pressed while another application (e.g., a game, VS Code) has full focus.

---