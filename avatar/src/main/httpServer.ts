/// <reference types="node" />

import { createServer } from 'http';
import type { Server as HttpServer, IncomingMessage, ServerResponse } from 'http';
import {
  handleVowelCommand,
  handleEmotionCommand,
  handleSpeakCommand,
  handleAnimationCommand,
} from './ipcHandlers';
import { validateVowel, validateEmotion, validateSpeakPayload, validateAnimationPayload } from './validation';

const HTTP_PORT = 3939;
const MAX_PAYLOAD_SIZE = 1024 * 1024; // 1MB

let httpServer: HttpServer | null = null;

export interface VrmCommandHandlers {
  onVowel: (data: { vowel: 'a' | 'i' | 'u' | 'e' | 'o' | null }) => void;
  onEmotion: (data: { emotion: 'neutral' | 'happy' | 'angry' | 'sad' | 'relaxed' | 'surprised' }) => void;
  onSpeak: (data: { text: string; emotion?: string }) => void;
  onAnimation: (data: { animation: string }) => void;
}

function sendJson(res: ServerResponse, status: number, payload: unknown): void {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(payload));
}

/**
 * VRM 制御 HTTP リクエストのハンドラーを生成する
 */
export function createRequestHandler(handlers: VrmCommandHandlers) {
  return (req: IncomingMessage, res: ServerResponse): void => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') {
      res.writeHead(200);
      res.end();
      return;
    }

    if (req.method === 'GET' && req.url === '/health') {
      sendJson(res, 200, { status: 'ok' });
      return;
    }

    if (req.method !== 'POST') {
      sendJson(res, 405, { error: 'Method not allowed' });
      return;
    }

    let body = '';
    let size = 0;

    req.on('data', (chunk: Buffer) => {
      size += chunk.length;
      if (size > MAX_PAYLOAD_SIZE) {
        sendJson(res, 413, { error: 'Payload too large' });
        req.destroy();
        return;
      }
      body += chunk.toString();
    });

    req.on('end', () => {
      if (res.headersSent) return;
      try {
        const data = JSON.parse(body);

        if (req.url === '/vrm/vowel') {
          if (!validateVowel(data.vowel)) {
            sendJson(res, 400, { error: 'Invalid vowel value' });
            return;
          }
          handlers.onVowel(data);
          sendJson(res, 200, { success: true });
        } else if (req.url === '/vrm/emotion') {
          if (!validateEmotion(data.emotion)) {
            sendJson(res, 400, { error: 'Invalid emotion value' });
            return;
          }
          handlers.onEmotion(data);
          sendJson(res, 200, { success: true });
        } else if (req.url === '/vrm/speak') {
          if (!validateSpeakPayload(data)) {
            sendJson(res, 400, { error: 'text must be a string' });
            return;
          }
          handlers.onSpeak(data);
          sendJson(res, 200, { success: true });
        } else if (req.url === '/vrm/animation') {
          if (!validateAnimationPayload(data)) {
            sendJson(res, 400, { error: 'animation must be a string' });
            return;
          }
          handlers.onAnimation(data);
          sendJson(res, 200, { success: true });
        } else {
          sendJson(res, 404, { error: 'Not found' });
        }
      } catch (error) {
        console.error('HTTP request error:', error);
        sendJson(res, 500, { error: 'Internal server error' });
      }
    });
  };
}

export function startHttpServer(): void {
  httpServer = createServer(createRequestHandler({
    onVowel: handleVowelCommand,
    onEmotion: handleEmotionCommand,
    onSpeak: handleSpeakCommand,
    onAnimation: handleAnimationCommand,
  }));

  httpServer.listen(HTTP_PORT, () => {
    console.log(`VRM control HTTP server listening on port ${HTTP_PORT}`);
  });
}

export function closeHttpServer(): void {
  if (httpServer) {
    httpServer.close();
  }
}
