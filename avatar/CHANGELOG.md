# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.3.4] - 2026-08-07

### Added
- Added 259 unit tests for the logic layer and enforced 100% coverage (statements / branches / functions / lines) in CI
- `src/utils/audioPlayer.ts` — per-OS audio playback command construction (pure function) with an injectable player
- `src/renderer/logic/expression.ts` — vowel-to-blendshape mapping, lerp interpolation, and emotion values (pure functions)
- `src/renderer/logic/idleVariation.ts` — idle variation config parsing and selection (pure functions)

### Changed
- Tests now live under `src/tests/`, mirroring the source tree exactly
- `TtsService` now accepts an injectable `AudioPlayer` as its third constructor argument; `TtsConfig` gained `playbackStartOffsetMs`
- Extracted the request handler out of `httpServer` as `createRequestHandler(handlers)` (`startHttpServer` still wires up the real handlers on port 3939 as before)
- `window.ts` / `ipcHandlers.ts` / `httpServer.ts` switched from `require()` to ESM `import` for `electron` / `http` (`tsconfig.main.json` unchanged; build output and behavior unchanged)
- Reduced `ExpressionController` / `AnimationController` to thin adapters over pure functions in `logic/`; `AnimationController` now accepts an injectable clip loader and random source, and uses `globalThis.setTimeout`
- Switched macOS / Linux audio playback from shell-based `exec` to `execFile` (hardening)
- `ExpressionController.setEmotion` now calls `setValue` 5 times instead of 6 (final VRM state is unchanged)
- Removed 3 unreachable defensive branches: the `Error.captureStackTrace` guard in `utils/errors.ts`, the `mainWindow` guard inside the `closed` callback in `window.ts`'s `toggleWindowMode`, and the `!animation` guard in `AnimationController.playIdleVariation`

### Fixed
- Fixed test files (`*.test.ts`) being compiled into `dist/`

---

## [0.3.3] - 2026-05-07

### Added
- GitHub Actions CI workflow to run the test suite on push/PR
- Vitest test runner installed and configured
- `src/utils/audio.ts` extracted with unit tests
- `src/main/validation.ts` extracted for HTTP payload validation, with unit tests
- Unit tests for `TtsError` and the error factory

### Changed
- Rewrote `docs/getting-started.md` for absolute beginners (JP section), with added screenshots and an animation setup step

### Fixed
- `validateSpeakPayload` now validates the optional `emotion` field
- Guarded against negative audio duration in `audio.ts`
- Updated Node.js download instructions to match the current nodejs.org UI
- CI uses `npm install` instead of `npm ci` to avoid cross-platform lock file issues

---

## [0.3.2] - 2026-05-06

### Fixed
- HTTP server now sends 413 response before destroying request socket
- Window mode toggle (`Ctrl+,`) uses `'closed'` event instead of `setTimeout` to eliminate race condition
- Windows audio playback uses `execFile` with argument array to prevent shell injection
- VRM HTTP requests now time out after 5 seconds to prevent indefinite hang
- HTTP endpoints validate input types before forwarding to IPC
- `AnimationController` cleans up `'finished'` event listeners on dispose
- Replaced `console.warn` with `console.error` in MCP server process for stdout safety
- Removed debug log from preload; moved startup message inside `app.whenReady()`

---

## [0.3.1] - 2026-05-06

### Added
- Windows installer packaging via electron-builder (NSIS + zip)
- `npm run dist:win` script for one-command Windows release build
- `scripts/zip-win.mjs` to zip installer for BOOTH distribution

### Fixed
- `dist/main/package.json` generated at build time to resolve ESM/CommonJS conflict with new modules

### Changed
- Rewrote `docs/getting-started.md` for BOOTH distribution with beginner-friendly installer guide (JP/EN)

---

## [0.3.0] - 2026-04-23

### Added
- Graceful degradation when TTS engine or VRM character is unavailable

### Changed
- All log and error messages translated to English (TtsService, errors.ts)

### Fixed
- Default pose arm direction corrected; angle set to 45 degrees
- Default pose now applied when animations fail to load or config is absent

---

## [0.2.0] - 2026-03-10

### Added
- Multi-platform audio playback: Windows (PowerShell), macOS (afplay), Linux (aplay)
- Playback start offset tuned per OS for accurate lip-sync timing (Windows: 150ms, others: 50ms)
- `docs/getting-started.md` — concise 5-step setup guide for first-time users (JP/EN)
- TTS engine OS compatibility table in README

### Changed
- `AivisSpeechService` → `TtsService` (engine-neutral rename)
- `AivisSpeechConfig` → `TtsConfig`
- `AivisSpeechError` → `TtsError`
- `AivisSpeechErrorData` → `TtsErrorData`
- README platform support section updated to reflect multi-platform status

---

## [0.1.1] - 2026-02-27

### Added
- Settings mode documentation in README (Ctrl+, to toggle)
- `animations.example.json` as a template for animations.json (mirrors config.example.json pattern)
- Bilingual README (Japanese + English) with anchor-link switcher

### Changed
- Refactored VRMRenderer monolith into `AnimationController` + `ExpressionController`
- DRY'd `VRMControlService` with shared `makeRequest()` private method
- Fixed `isVRMWindowRunning()`: was inadvertently sending `emotion=neutral` as a side effect; now uses dedicated `GET /health` endpoint
- Added `GET /health` endpoint and 1MB payload size limit to the HTTP server
- Updated LICENSE copyright holder

### Removed
- `assets/animations/LICENSE.md` (animation acquisition guide merged into README)
- `assets/animations/animations.json` removed from git tracking (added to `.gitignore`)

---

## [0.1.0] - 2026-02-18

### Added
- Initial public release
- VRM 3D character display via Electron + Three.js + @pixiv/three-vrm
- VOICEVOX-compatible TTS integration (AivisSpeech / VOICEVOX / COEIROINK)
- Lip-sync synchronized with audio playback using mora timing
- 6 emotion expressions: neutral, happy, sad, angry, relaxed, surprised
- VRMA animation support with 10 built-in animation slots
- Idle variation animations with configurable interval
- Transparent always-on-top window (desktop mascot style)
- Settings mode (Ctrl+,) for window resizing and repositioning
- Camera and window position persistence
- MCP `speak` tool with text, emotion, and animation parameters
- `config.example.json` for configuration template
- CONTRIBUTING.md and GitHub issue/PR templates
