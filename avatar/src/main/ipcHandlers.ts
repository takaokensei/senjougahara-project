import { ipcMain } from 'electron';
import { getMainWindow, updateCharacterBounds } from './window.js';

export function handleVowelCommand(data: { vowel: 'a' | 'i' | 'u' | 'e' | 'o' | null }): void {
  const win = getMainWindow();
  if (win) {
    win.webContents.send('vrm-vowel', data.vowel);
  }
}

export function handleEmotionCommand(data: { emotion: 'neutral' | 'happy' | 'angry' | 'sad' | 'relaxed' | 'surprised' }): void {
  const win = getMainWindow();
  if (win) {
    win.webContents.send('vrm-emotion', data.emotion);
  }
}

export function handleSpeakCommand(data: { text: string; emotion?: string }): void {
  const win = getMainWindow();
  if (win) {
    win.webContents.send('vrm-speak', data);
  }
}

export function handleAnimationCommand(data: { animation: string }): void {
  const win = getMainWindow();
  if (win) {
    win.webContents.send('vrm-animation', data.animation);
  }
}

export function registerIpcHandlers(): void {
  ipcMain.on('set-window-bounds', (_event: any, bounds: { x: number; y: number; width: number; height: number }) => {
    const win = getMainWindow();
    if (win) {
      win.setBounds(bounds);
    }
  });

  ipcMain.on('window:set-ignore-mouse-events', (event: any, ignore: boolean, options?: { forward?: boolean }) => {
    const win = getMainWindow();
    if (win && typeof (win as any).setIgnoreMouseEvents === 'function') {
      (win as any).setIgnoreMouseEvents(ignore, options || { forward: true });
    }
  });

  ipcMain.on('locomotion:update-position', (_event: any, data: { x: number; y: number; width?: number; height?: number }) => {
    updateCharacterBounds(data);
  });
}
