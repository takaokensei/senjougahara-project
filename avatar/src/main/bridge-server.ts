/**
 * avatar/src/main/bridge-server.ts
 *
 * WebSocket + REST bridge server in the Electron main process.
 * The Python brain connects as a WebSocket CLIENT to this server.
 *
 * - Forwards brain commands (speak, state_change, etc.) to the renderer via IPC
 * - Forwards avatar events (hotkey, click) back to the brain via WebSocket
 * - Serves GET /health REST endpoint
 *
 * See shared/schemas/bridge-messages.json for the full message schema.
 *
 * Inspired by the daemon<->sidecar IPC pattern from vierisid/jarvis
 * (studied as architectural reference only; RSALv2 license).
 */

import { BrowserWindow, ipcMain } from 'electron';
import * as http from 'http';
import { WebSocket, WebSocketServer } from 'ws';

export type AvatarState =
  | 'IDLE' | 'LISTENING' | 'THINKING' | 'TOOL_EXECUTION' | 'SPEAKING'
  | 'HAPPY' | 'CONFUSED' | 'SURPRISED' | 'ANNOYED' | 'SLEEPING'
  | 'GREETING' | 'GOODBYE' | 'ERROR';

export type Emotion = 'neutral' | 'happy' | 'sad' | 'angry' | 'surprised' | 'confused' | 'annoyed' | 'relaxed';

export interface SpeakCommand { type: 'speak'; text: string; emotion: Emotion; animation?: string; caption?: string; audio_url?: string; viseme_track?: Array<{ time: number; viseme: string }>; priority?: string; }
export interface StateChangeCommand { type: 'state_change'; state: AvatarState; reason?: string; }
export interface ConfirmationRequest { type: 'confirmation_request'; request_id: string; action_description: string; tool_name: string; risk_tier: string; timeout_seconds: number; }
export interface ConfirmationResponse { type: 'confirmation_response'; request_id: string; confirmed: boolean; }
export interface ActivateEvent { type: 'activate'; source: 'hotkey' | 'wake_word' | 'click'; timestamp: number; }

export type BrainMessage = SpeakCommand | StateChangeCommand | ConfirmationRequest | { type: 'error'; message: string; recoverable?: boolean } | { type: 'ping' } | { type: 'pong' };
export type AvatarMessage = ActivateEvent | ConfirmationResponse | { type: 'ping' } | { type: 'pong' };

export class BridgeServer {
  private wss: WebSocketServer;
  private httpServer: http.Server;
  private brainSocket: WebSocket | null = null;
  private mainWindow: BrowserWindow | null = null;
  private port: number;

  constructor(port = 8765) {
    this.port = port;
    this.httpServer = http.createServer(this.handleHttp.bind(this));
    this.wss = new WebSocketServer({ server: this.httpServer });
    this.wss.on('connection', this.handleBrainConnection.bind(this));
  }

  start(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.httpServer.listen(this.port, '127.0.0.1', () => {
        console.log(`[Bridge] Listening on ws://127.0.0.1:${this.port}`);
        resolve();
      });
      this.httpServer.on('error', reject);
    });
  }

  stop(): void {
    this.wss.close();
    this.httpServer.close();
  }

  setMainWindow(window: BrowserWindow): void {
    this.mainWindow = window;
    ipcMain.on('bridge:activate', (_evt, source: ActivateEvent['source']) => {
      this.sendToBrain({ type: 'activate', source, timestamp: Date.now() });
    });
    ipcMain.on('bridge:confirmation_response', (_evt, resp: ConfirmationResponse) => {
      this.sendToBrain(resp);
    });
  }

  private handleHttp(req: http.IncomingMessage, res: http.ServerResponse): void {
    if (req.method === 'GET' && req.url === '/health') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ avatar: 'ready', brain_connected: this.brainSocket !== null, ts: Date.now() }));
      return;
    }
    res.writeHead(404);
    res.end();
  }

  private handleBrainConnection(ws: WebSocket): void {
    if (this.brainSocket) {
      console.warn('[Bridge] Rejecting second connection.');
      ws.close(1008, 'Only one brain connection allowed.');
      return;
    }
    this.brainSocket = ws;
    console.log('[Bridge] Brain connected.');
    this.mainWindow?.webContents.send('bridge:brain_connected');

    ws.on('message', (data) => {
      let msg: BrainMessage;
      try { msg = JSON.parse(data.toString()) as BrainMessage; }
      catch { console.warn('[Bridge] Non-JSON message'); return; }
      if (msg.type === 'ping') { ws.send(JSON.stringify({ type: 'pong' })); return; }
      this.mainWindow?.webContents.send('bridge:command', msg);
    });

    ws.on('close', () => {
      console.log('[Bridge] Brain disconnected.');
      this.brainSocket = null;
      this.mainWindow?.webContents.send('bridge:command', { type: 'error', message: 'Brain disconnected.', recoverable: true });
    });

    ws.on('error', (err) => console.error('[Bridge] Socket error:', err));
  }

  private sendToBrain(message: AvatarMessage): void {
    if (this.brainSocket?.readyState === WebSocket.OPEN) {
      this.brainSocket.send(JSON.stringify(message));
    }
  }
}

let _instance: BridgeServer | null = null;
export function getBridgeServer(port = 8765): BridgeServer {
  if (!_instance) _instance = new BridgeServer(port);
  return _instance;
}