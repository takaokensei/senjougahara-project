#!/usr/bin/env node

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import { TtsService } from './services/TtsService.js';
import { VRMControlService } from './services/VRMControlService.js';
import { createSpeakTool } from './tools/speak.js';

/**
 * MCPサーバーのメイン処理
 */
async function main() {
  // 環境変数から設定を読み込む
  const baseUrl = process.env.VOICEVOX_BASE_URL || 'http://127.0.0.1:10101';
  const speakerId = parseInt(process.env.VOICEVOX_SPEAKER_ID || '888753760', 10);

  // VRMコントロールサービスを初期化
  const vrmControlService = new VRMControlService(3939);

  // 音声合成サービスを初期化（リップシンク対応）
  const ttsService = new TtsService({
    baseUrl,
    speakerId,
    timeout: 30000, // 30秒
    maxRetries: 3,
    retryDelay: 1000,
  }, vrmControlService);

  // MCPサーバーを作成
  const server = new Server(
    {
      name: 'desktop-mascot-mcp',
      version: '1.0.0',
    },
    {
      capabilities: {
        tools: {},
      },
    }
  );

  // speak toolを作成
  const speakTool = createSpeakTool(ttsService, vrmControlService);

  // tools/listハンドラ: 利用可能なツール一覧を返す
  server.setRequestHandler(ListToolsRequestSchema, async () => {
    return {
      tools: [
        {
          name: speakTool.name,
          description: speakTool.description,
          inputSchema: speakTool.inputSchema,
        },
      ],
    };
  });

  // tools/callハンドラ: ツールを実行
  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;

    if (name === speakTool.name) {
      return await speakTool.handler(args as { text: string; emotion?: string; animation?: string });
    }

    throw new Error(`Unknown tool: ${name}`);
  });

  // Stdio通信で接続
  const transport = new StdioServerTransport();
  await server.connect(transport);

  console.error('Desktop Mascot MCP Server started successfully');
}

// サーバー起動
main().catch((error) => {
  console.error('Fatal error:', error);
  process.exit(1);
});
