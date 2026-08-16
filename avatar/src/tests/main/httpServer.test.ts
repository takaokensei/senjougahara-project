import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createServer, request } from 'http';
import type { Server } from 'http';
import type { AddressInfo } from 'net';
import { EventEmitter } from 'events';

vi.mock('electron', () => ({
  ipcMain: { on: vi.fn() },
  BrowserWindow: vi.fn(),
}));

import { createRequestHandler, closeHttpServer, startHttpServer } from '../../main/httpServer.js';

function makeHandlers() {
  return {
    onVowel: vi.fn(),
    onEmotion: vi.fn(),
    onSpeak: vi.fn(),
    onAnimation: vi.fn(),
  };
}

let server: Server;
let baseUrl: string;
let handlers: ReturnType<typeof makeHandlers>;

beforeEach(async () => {
  handlers = makeHandlers();
  server = createServer(createRequestHandler(handlers));
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  baseUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(async () => {
  await new Promise<void>((resolve) => server.close(() => resolve()));
  vi.restoreAllMocks();
});

function post(path: string, body: string) {
  return fetch(`${baseUrl}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
  });
}

describe('CORS と OPTIONS', () => {
  it('OPTIONS に 200 と CORS ヘッダーを返す', async () => {
    const res = await fetch(`${baseUrl}/vrm/vowel`, { method: 'OPTIONS' });
    expect(res.status).toBe(200);
    expect(res.headers.get('access-control-allow-origin')).toBe('*');
    expect(res.headers.get('access-control-allow-methods')).toBe('GET, POST, OPTIONS');
    expect(res.headers.get('access-control-allow-headers')).toBe('Content-Type');
  });
});

describe('GET', () => {
  it('/health は 200 と status:ok', async () => {
    const res = await fetch(`${baseUrl}/health`);
    expect(res.status).toBe(200);
    await expect(res.json()).resolves.toEqual({ status: 'ok' });
  });

  it('/health 以外の GET は 405', async () => {
    const res = await fetch(`${baseUrl}/vrm/vowel`);
    expect(res.status).toBe(405);
    await expect(res.json()).resolves.toEqual({ error: 'Method not allowed' });
  });

  it('DELETE も 405', async () => {
    const res = await fetch(`${baseUrl}/health`, { method: 'DELETE' });
    expect(res.status).toBe(405);
  });
});

describe('POST /vrm/vowel', () => {
  it('有効な母音でハンドラーを呼び 200 を返す', async () => {
    const res = await post('/vrm/vowel', JSON.stringify({ vowel: 'a' }));
    expect(res.status).toBe(200);
    await expect(res.json()).resolves.toEqual({ success: true });
    expect(handlers.onVowel).toHaveBeenCalledWith({ vowel: 'a' });
  });

  it('null も有効値として受け付ける', async () => {
    const res = await post('/vrm/vowel', JSON.stringify({ vowel: null }));
    expect(res.status).toBe(200);
    expect(handlers.onVowel).toHaveBeenCalledWith({ vowel: null });
  });

  it('不正な母音は 400 でハンドラーを呼ばない', async () => {
    const res = await post('/vrm/vowel', JSON.stringify({ vowel: 'x' }));
    expect(res.status).toBe(400);
    await expect(res.json()).resolves.toEqual({ error: 'Invalid vowel value' });
    expect(handlers.onVowel).not.toHaveBeenCalled();
  });
});

describe('POST /vrm/emotion', () => {
  it('有効な感情でハンドラーを呼び 200 を返す', async () => {
    const res = await post('/vrm/emotion', JSON.stringify({ emotion: 'happy' }));
    expect(res.status).toBe(200);
    expect(handlers.onEmotion).toHaveBeenCalledWith({ emotion: 'happy' });
  });

  it('不正な感情は 400 でハンドラーを呼ばない', async () => {
    const res = await post('/vrm/emotion', JSON.stringify({ emotion: 'excited' }));
    expect(res.status).toBe(400);
    await expect(res.json()).resolves.toEqual({ error: 'Invalid emotion value' });
    expect(handlers.onEmotion).not.toHaveBeenCalled();
  });
});

describe('POST /vrm/speak', () => {
  it('text だけでも 200 を返す', async () => {
    const res = await post('/vrm/speak', JSON.stringify({ text: 'やあ' }));
    expect(res.status).toBe(200);
    expect(handlers.onSpeak).toHaveBeenCalledWith({ text: 'やあ' });
  });

  it('text が文字列でなければ 400', async () => {
    const res = await post('/vrm/speak', JSON.stringify({ text: 123 }));
    expect(res.status).toBe(400);
    await expect(res.json()).resolves.toEqual({ error: 'text must be a string' });
    expect(handlers.onSpeak).not.toHaveBeenCalled();
  });
});

describe('POST /vrm/animation', () => {
  it('animation が文字列なら 200', async () => {
    const res = await post('/vrm/animation', JSON.stringify({ animation: 'wave' }));
    expect(res.status).toBe(200);
    expect(handlers.onAnimation).toHaveBeenCalledWith({ animation: 'wave' });
  });

  it('animation が無ければ 400', async () => {
    const res = await post('/vrm/animation', JSON.stringify({}));
    expect(res.status).toBe(400);
    await expect(res.json()).resolves.toEqual({ error: 'animation must be a string' });
    expect(handlers.onAnimation).not.toHaveBeenCalled();
  });
});

describe('エラー処理', () => {
  it('未知のパスは 404', async () => {
    const res = await post('/vrm/unknown', JSON.stringify({}));
    expect(res.status).toBe(404);
    await expect(res.json()).resolves.toEqual({ error: 'Not found' });
  });

  it('不正な JSON は 500', async () => {
    const res = await post('/vrm/vowel', '{ not json');
    expect(res.status).toBe(500);
    await expect(res.json()).resolves.toEqual({ error: 'Internal server error' });
  });

  it('1MB を超えるチャンクで 413 を書き込み接続を破棄する', () => {
    // スタブの req/res を直接駆動し、ペイロード超過時にサーバーが書き込む
    // レスポンス内容とソケット破棄を決定的に検証する（プラットフォーム非依存）。
    const stubHandlers = makeHandlers();
    const handler = createRequestHandler(stubHandlers);

    const req = new EventEmitter() as EventEmitter & { method: string; url: string; destroy: ReturnType<typeof vi.fn> };
    req.method = 'POST';
    req.url = '/vrm/speak';
    req.destroy = vi.fn();

    const res = new EventEmitter() as EventEmitter & {
      headersSent: boolean;
      setHeader: ReturnType<typeof vi.fn>;
      writeHead: ReturnType<typeof vi.fn>;
      end: ReturnType<typeof vi.fn>;
    };
    res.headersSent = false;
    res.setHeader = vi.fn();
    res.writeHead = vi.fn(() => {
      res.headersSent = true;
    });
    res.end = vi.fn();

    handler(req as any, res as any);

    req.emit('data', Buffer.alloc(1024 * 1024 + 1));

    expect(res.writeHead).toHaveBeenCalledWith(413, { 'Content-Type': 'application/json' });
    expect(res.end).toHaveBeenCalledWith(JSON.stringify({ error: 'Payload too large' }));
    expect(req.destroy).toHaveBeenCalled();
    expect(stubHandlers.onVowel).not.toHaveBeenCalled();
    expect(stubHandlers.onEmotion).not.toHaveBeenCalled();
    expect(stubHandlers.onSpeak).not.toHaveBeenCalled();
    expect(stubHandlers.onAnimation).not.toHaveBeenCalled();
  });

  it('1MB を超えるボディでは接続が切断され、ハンドラーが呼ばれない', async () => {
    // ワイヤーレベルの実ソケットでの挙動を確認する。サーバーは 413 応答の直後に
    // req.destroy() で接続を切る（意図的な挙動、履歴コミット e871c57 参照）。
    // このため OS の TCP スタックによっては、クライアント側でレスポンスを読み
    // 切る前に RST を受け取り ECONNRESET になることがある（Windows 上では生の
    // http.request でも決定的に再現することを別途確認済み）。ステータスコード
    // 413 が実際に書き込まれることの決定的な証明は、上の
    // 「1MB を超えるチャンクで 413 を書き込み接続を破棄する」テストが担う。
    // このテストは「接続が切断されること」と「ハンドラーが呼ばれないこと」を
    // 実ソケット経由で検証する。
    const outcome = await new Promise<{ status: number } | { error: string }>((resolve, reject) => {
      const req = request(
        `${baseUrl}/vrm/speak`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' } },
        (res) => {
          res.resume();
          resolve({ status: res.statusCode! });
        }
      );
      req.on('error', (err: NodeJS.ErrnoException) => {
        if (err.code === 'ECONNRESET') {
          resolve({ error: err.code });
        } else {
          reject(err);
        }
      });
      // 512KB を 3 回書き込んで 1MB を超えさせる
      const chunk = 'x'.repeat(512 * 1024);
      req.write(chunk);
      req.write(chunk);
      req.write(chunk);
      req.end();
    });
    if ('status' in outcome) {
      expect(outcome.status).toBe(413);
    } else {
      expect(outcome.error).toBe('ECONNRESET');
    }
    expect(handlers.onSpeak).not.toHaveBeenCalled();
  });
});

describe('res.headersSent ガード', () => {
  // 実ソケット経由では req.destroy() 後に 'end' イベントは発火しないことを
  // 別途確認済み（コミット e871c57 で追加された防御的ガード）。
  // スタブの req/res を使い、413 応答後に 'end' が発火するケースを直接再現して、
  // 二重応答を防ぐガードそのものを検証する。
  it('413 応答後に end イベントが発火しても二重応答しない', () => {
    const handlers = makeHandlers();
    const handler = createRequestHandler(handlers);

    const req = new EventEmitter() as EventEmitter & { method: string; url: string; destroy: () => void };
    req.method = 'POST';
    req.url = '/vrm/speak';
    req.destroy = vi.fn();

    const res = new EventEmitter() as EventEmitter & {
      headersSent: boolean;
      setHeader: (...args: unknown[]) => void;
      writeHead: (...args: unknown[]) => void;
      end: (...args: unknown[]) => void;
    };
    res.headersSent = false;
    res.setHeader = vi.fn();
    res.writeHead = vi.fn(() => {
      res.headersSent = true;
    });
    res.end = vi.fn();

    handler(req as any, res as any);

    req.emit('data', Buffer.alloc(1024 * 1024 + 1));
    expect(res.writeHead).toHaveBeenCalledWith(413, { 'Content-Type': 'application/json' });
    expect(req.destroy).toHaveBeenCalled();

    const endCallsAfter413 = (res.end as ReturnType<typeof vi.fn>).mock.calls.length;
    req.emit('end');
    expect(res.end).toHaveBeenCalledTimes(endCallsAfter413);
    expect(handlers.onSpeak).not.toHaveBeenCalled();
  });
});

describe('closeHttpServer', () => {
  it('サーバー未起動でも例外を投げない', () => {
    expect(() => closeHttpServer()).not.toThrow();
  });
});

describe('startHttpServer', () => {
  it('ポート 3939 で待ち受け、closeHttpServer で停止できる', async () => {
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
    startHttpServer();
    try {
      await vi.waitFor(() => expect(logSpy).toHaveBeenCalledWith(
        'VRM control HTTP server listening on port 3939'
      ));
      const res = await fetch('http://127.0.0.1:3939/health');
      expect(res.status).toBe(200);
    } finally {
      closeHttpServer();
    }
  });
});
