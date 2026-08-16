import { BrowserWindow, screen } from 'electron';
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

  let windowWidth = 800;
  let windowHeight = 600;
  let windowX: number | undefined;
  let windowY: number | undefined;

  if (isNormalMode) {
    try {
      const primary = screen.getPrimaryDisplay();
      if (primary && primary.workAreaSize) {
        windowWidth = primary.workAreaSize.width;
        windowHeight = primary.workAreaSize.height;
        windowX = primary.workArea?.x || 0;
        windowY = primary.workArea?.y || 0;
      }
    } catch {
      // Fallback
    }
  }

  mainWindow = new BrowserWindow({
    x: windowX,
    y: windowY,
    width: windowWidth,
    height: windowHeight,
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

  if (isNormalMode && typeof (mainWindow as any).setIgnoreMouseEvents === 'function') {
    (mainWindow as any).setIgnoreMouseEvents(true, { forward: true });
  }

  // Forward renderer console logs to the Node terminal for dev visibility
  mainWindow.webContents.on('console-message', (event: any, ...args: any[]) => {
    let level = 1;
    let message = '';
    let sourceId = '';
    let line = 0;

    if (typeof args[0] === 'object' && args[0] !== null) {
      level = args[0].level ?? 1;
      message = args[0].message ?? '';
      sourceId = args[0].sourceId ?? '';
      line = args[0].lineNumber ?? 0;
    } else {
      level = args[0] ?? 1;
      message = args[1] ?? '';
      line = args[2] ?? 0;
      sourceId = args[3] ?? '';
    }

    if (typeof message === 'string' && message.includes('Electron Security Warning')) return;

    const levelStr = level === 3 ? '[AVATAR RENDERER ERROR]' : (level === 2 ? '[AVATAR RENDERER WARN]' : '[AVATAR RENDERER]');
    const loc = sourceId ? ` (${path.basename(sourceId)}:${line})` : '';
    console.log(`${levelStr} ${message}${loc}`);
  });

  mainWindow.webContents.on('did-fail-load', (event, errorCode, errorDescription) => {
    console.error(`[AVATAR ERROR] Failed to load renderer page: ${errorDescription} (code: ${errorCode})`);
  });

  // Hotkeys: Ctrl+, (toggle mode) | Ctrl+Shift+I or F12 (toggle DevTools)
  mainWindow.webContents.on('before-input-event', (event, input) => {
    if (input.type === 'keyDown') {
      if (input.key === ',' && input.control) {
        event.preventDefault();
        toggleWindowMode();
      } else if ((input.control && input.shift && input.key.toLowerCase() === 'i') || input.key === 'F12') {
        event.preventDefault();
        mainWindow?.webContents.toggleDevTools();
      }
    }
  });

  mainWindow.loadFile(path.join(__dirname, '../renderer/VRM.html'));

  mainWindow.on('closed', () => {
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
