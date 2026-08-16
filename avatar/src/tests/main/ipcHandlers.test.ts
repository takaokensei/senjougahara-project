import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('electron', () => ({
  ipcMain: { on: vi.fn() },
  BrowserWindow: vi.fn(),
}));

vi.mock('../../main/window.js', () => ({
  getMainWindow: vi.fn(),
}));

import { ipcMain } from 'electron';
import { getMainWindow } from '../../main/window.js';
import {
  handleVowelCommand,
  handleEmotionCommand,
  handleSpeakCommand,
  handleAnimationCommand,
  registerIpcHandlers,
} from '../../main/ipcHandlers.js';

function makeWindow() {
  return {
    webContents: { send: vi.fn() },
    setBounds: vi.fn(),
  };
}

beforeEach(() => {
  vi.mocked(getMainWindow).mockReset();
  vi.mocked(ipcMain.on).mockReset();
});

describe('VRM コマンドハンドラー - ウィンドウがある場合', () => {
  it('handleVowelCommand が vrm-vowel を送る', () => {
    const win = makeWindow();
    vi.mocked(getMainWindow).mockReturnValue(win as never);
    handleVowelCommand({ vowel: 'a' });
    expect(win.webContents.send).toHaveBeenCalledWith('vrm-vowel', 'a');
  });

  it('handleEmotionCommand が vrm-emotion を送る', () => {
    const win = makeWindow();
    vi.mocked(getMainWindow).mockReturnValue(win as never);
    handleEmotionCommand({ emotion: 'happy' });
    expect(win.webContents.send).toHaveBeenCalledWith('vrm-emotion', 'happy');
  });

  it('handleSpeakCommand は payload をそのまま送る', () => {
    const win = makeWindow();
    vi.mocked(getMainWindow).mockReturnValue(win as never);
    const payload = { text: 'やあ', emotion: 'sad' };
    handleSpeakCommand(payload);
    expect(win.webContents.send).toHaveBeenCalledWith('vrm-speak', payload);
  });

  it('handleAnimationCommand が vrm-animation を送る', () => {
    const win = makeWindow();
    vi.mocked(getMainWindow).mockReturnValue(win as never);
    handleAnimationCommand({ animation: 'wave' });
    expect(win.webContents.send).toHaveBeenCalledWith('vrm-animation', 'wave');
  });
});

describe('VRM コマンドハンドラー - ウィンドウが無い場合', () => {
  beforeEach(() => {
    vi.mocked(getMainWindow).mockReturnValue(null);
  });

  it('いずれのハンドラーも例外を投げない', () => {
    expect(() => handleVowelCommand({ vowel: 'a' })).not.toThrow();
    expect(() => handleEmotionCommand({ emotion: 'happy' })).not.toThrow();
    expect(() => handleSpeakCommand({ text: 'やあ' })).not.toThrow();
    expect(() => handleAnimationCommand({ animation: 'wave' })).not.toThrow();
  });
});

describe('registerIpcHandlers', () => {
  it('set-window-bounds を購読する', () => {
    registerIpcHandlers();
    expect(ipcMain.on).toHaveBeenCalledWith('set-window-bounds', expect.any(Function));
  });

  it('受信した bounds をウィンドウに適用する', () => {
    const win = makeWindow();
    vi.mocked(getMainWindow).mockReturnValue(win as never);
    registerIpcHandlers();
    const listener = vi.mocked(ipcMain.on).mock.calls[0][1];
    const bounds = { x: 1, y: 2, width: 300, height: 400 };
    listener({} as never, bounds);
    expect(win.setBounds).toHaveBeenCalledWith(bounds);
  });

  it('ウィンドウが無ければ何もしない', () => {
    vi.mocked(getMainWindow).mockReturnValue(null);
    registerIpcHandlers();
    const listener = vi.mocked(ipcMain.on).mock.calls[0][1];
    expect(() => listener({} as never, { x: 0, y: 0, width: 1, height: 1 })).not.toThrow();
  });
});
