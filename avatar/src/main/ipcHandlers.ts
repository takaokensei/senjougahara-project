import { ipcMain } from 'electron';
import { getMainWindow } from './window';

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
}
