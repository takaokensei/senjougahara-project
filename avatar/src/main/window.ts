/// <reference types="node" />

import { BrowserWindow } from 'electron';
import type { BrowserWindow as BrowserWindowType } from 'electron';
import * as path from 'path';

let mainWindow: BrowserWindowType | null = null;
let isNormalMode = true;
let isRecreatingWindow = false;

export function getMainWindow(): BrowserWindowType | null {
  return mainWindow;
}

export function isRecreating(): boolean {
  return isRecreatingWindow;
}

export function createWindow(): void {
  console.log(`[desktop-mascot-mcp] Creating window in ${isNormalMode ? 'Normal' : 'Settings'} mode`);
  console.log(`[desktop-mascot-mcp] Window settings - transparent: ${isNormalMode}, frame: ${!isNormalMode}, alwaysOnTop: ${isNormalMode}`);

  const preloadPath = path.join(__dirname, '../renderer/preload.js');

  mainWindow = new BrowserWindow({
    width: 800,
    height: 600,
    transparent: isNormalMode,
    backgroundColor: isNormalMode ? '#00000000' : '#222222',
    frame: !isNormalMode,
    resizable: true,
    alwaysOnTop: isNormalMode,
    skipTaskbar: isNormalMode,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: preloadPath,
    },
  });

  mainWindow!.webContents.on('before-input-event', (event, input) => {
    if (input.type === 'keyDown' && input.key === ',' && input.control) {
      event.preventDefault();
      toggleWindowMode();
    }
  });

  mainWindow!.loadFile(path.join(__dirname, '../renderer/VRM.html'));

  mainWindow!.on('closed', () => {
    mainWindow = null;
  });
}

export function toggleWindowMode(): void {
  if (!mainWindow) return;

  isNormalMode = !isNormalMode;
  console.log(`[desktop-mascot-mcp] Window mode switched to ${isNormalMode ? 'Normal' : 'Settings'}`);

  const [x, y] = mainWindow.getPosition();
  const [width, height] = mainWindow.getSize();

  isRecreatingWindow = true;

  mainWindow.once('closed', () => {
    createWindow();
    mainWindow!.setPosition(x, y);
    mainWindow!.setSize(width, height);
    isRecreatingWindow = false;
  });

  mainWindow.close();
}
