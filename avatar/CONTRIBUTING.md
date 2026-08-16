# Contributing to Desktop Mascot MCP / コントリビューションガイド

Thank you for your interest in contributing!
コントリビューションに興味を持っていただきありがとうございます！

---

## Getting Started / 開発環境のセットアップ

### Prerequisites / 必要なもの

- Node.js 18+
- Git
- MCP-compatible AI tool (e.g. Claude Desktop)
- VOICEVOX-compatible TTS engine (e.g. VOICEVOX, AivisSpeech)
- A VRM model file (`.vrm`)

### Setup / セットアップ

```bash
git clone https://github.com/rennosuke-haresu/desktop-mascot-mcp.git
cd desktop-mascot-mcp
npm install
cp config.example.json config.json
# Edit config.json to set your VRM model path
```

### Build / ビルド

```bash
# Full build (MCP server + Electron app)
npm run build

# Electron app only (includes asset copy)
npm run build:electron
```

### Run / 起動

```bash
# Start Electron window (run after starting your TTS engine)
npm run start:electron
```

---

## How to Contribute / コントリビューションの方法

### Reporting Bugs / バグ報告

Please use the [Bug Report issue template](.github/ISSUE_TEMPLATE/bug_report.md).
Include your OS, Node.js version, TTS engine, and steps to reproduce.

バグ報告は [Bug Report テンプレート](.github/ISSUE_TEMPLATE/bug_report.md) を使用してください。
OS・Node.jsバージョン・TTSエンジン・再現手順を含めてください。

### Feature Requests / 機能要望

Use the [Feature Request issue template](.github/ISSUE_TEMPLATE/feature_request.md).

[Feature Request テンプレート](.github/ISSUE_TEMPLATE/feature_request.md) を使用してください。

### Pull Requests

1. Fork the repository
2. Create a branch: `git checkout -b feat/your-feature` or `fix/your-fix`
3. Make your changes
4. Build and verify: `npm run build:electron`
5. Commit with a clear message (see below)
6. Open a Pull Request

---

1. リポジトリを Fork する
2. ブランチを作成: `git checkout -b feat/your-feature` または `fix/your-fix`
3. 変更を加える
4. ビルドして動作確認: `npm run build:electron`
5. コミットメッセージを書く（下記参照）
6. Pull Request を開く

---

## Commit Messages / コミットメッセージ

Use [Conventional Commits](https://www.conventionalcommits.org/) format:

```
feat: add new animation support
fix: correct lip-sync timing offset
docs: update README setup steps
refactor: simplify VRM loader logic
```

---

## Code Style / コードスタイル

- TypeScript strict mode
- Follow the existing module system:
  - MCP server (`src/index.ts`): ESModule
  - Electron main (`src/main/`): CommonJS (compiled to `.cjs`)
  - Electron renderer (`src/renderer/`): ESModule
- Use `console.error()` in MCP server code (stdout is reserved for JSON protocol)

---

## License / ライセンス

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE.md).

コントリビューションは [MIT License](LICENSE.md) のもとで提供されることに同意したものとみなします。
