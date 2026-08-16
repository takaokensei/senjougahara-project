import { BrowserWindow, screen } from 'electron';
import type { BrowserWindow as BrowserWindowType } from 'electron';
import * as path from 'path';

let mainWindow: BrowserWindowType | null = null;
let isNormalMode = true;
let isRecreatingWindow = false;
let cursorPollInterval: NodeJS.Timeout | null = null;
let currentCharacterBounds: { minX: number; maxX: number; minY: number; maxY: number } | null = null;
let isCurrentlyIgnoringMouse = true;
let isEmergencyInteractivityForced = false;

export function getMainWindow(): BrowserWindowType | null {
  return mainWindow;
}

export function isRecreating(): boolean {
  return isRecreatingWindow;
}

export function updateCharacterBounds(bounds: {
  minX?: number;
  maxX?: number;
  minY?: number;
  maxY?: number;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
}): void {
  if (
    bounds.minX !== undefined &&
    bounds.maxX !== undefined &&
    bounds.minY !== undefined &&
    bounds.maxY !== undefined
  ) {
    currentCharacterBounds = {
      minX: bounds.minX,
      maxX: bounds.maxX,
      minY: bounds.minY,
      maxY: bounds.maxY,
    };
  } else if (bounds.x !== undefined && bounds.y !== undefined) {
    const halfWidth = (bounds.width ?? 280) / 2;
    const halfHeight = (bounds.height ?? 480) / 2;
    currentCharacterBounds = {
      minX: bounds.x - halfWidth,
      maxX: bounds.x + halfWidth,
      minY: bounds.y - halfHeight,
      maxY: bounds.y + halfHeight,
    };
  }
}

export function startCursorPolling(): void {
  stopCursorPolling();
  if (!isNormalMode) return;

  cursorPollInterval = setInterval(() => {
    if (!mainWindow || isEmergencyInteractivityForced) {
      return;
    }

    try {
      if (typeof screen.getCursorScreenPoint !== 'function') return;
      const cursor = screen.getCursorScreenPoint();
      const [winX, winY] = typeof mainWindow.getPosition === 'function' ? mainWindow.getPosition() : [0, 0];

      // Calculate relative coordinates in window
      const relX = cursor.x - winX;
      const relY = cursor.y - winY;

      let isOver = false;
      if (currentCharacterBounds) {
        isOver =
          relX >= currentCharacterBounds.minX &&
          relX <= currentCharacterBounds.maxX &&
          relY >= currentCharacterBounds.minY &&
          relY <= currentCharacterBounds.maxY;
      }

      const shouldIgnore = !isOver;
      if (shouldIgnore !== isCurrentlyIgnoringMouse) {
        isCurrentlyIgnoringMouse = shouldIgnore;
        if (typeof (mainWindow as any).setIgnoreMouseEvents === 'function') {
          (mainWindow as any).setIgnoreMouseEvents(shouldIgnore, { forward: true });
        }
      }
    } catch {
      // Safe fallback
    }
  }, 40);
}

export function stopCursorPolling(): void {
  if (cursorPollInterval) {
    clearInterval(cursorPollInterval);
    cursorPollInterval = null;
  }
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

  isEmergencyInteractivityForced = false;
  isCurrentlyIgnoringMouse = isNormalMode;

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
    startCursorPolling();
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

  // Hotkeys:
  // - Ctrl+, : Toggle window mode (Normal vs Settings)
  // - Ctrl+Shift+I / F12 : DevTools
  // - Ctrl+Alt+I : Emergency mouse interactivity ON
  // - Ctrl+Home : Reset character position to center
  // - Ctrl+0 : Preset bottom-left waist-up close-up view
  mainWindow.webContents.on('before-input-event', (event, input) => {
    if (input.type === 'keyDown') {
      if (input.key === ',' && input.control) {
        event.preventDefault();
        toggleWindowMode();
      } else if ((input.control && input.shift && input.key?.toLowerCase() === 'i') || input.key === 'F12') {
        event.preventDefault();
        mainWindow?.webContents.toggleDevTools();
      } else if (input.key?.toLowerCase() === 'i' && input.control && input.alt) {
        event.preventDefault();
        isEmergencyInteractivityForced = true;
        isCurrentlyIgnoringMouse = false;
        if (typeof (mainWindow as any)?.setIgnoreMouseEvents === 'function') {
          (mainWindow as any).setIgnoreMouseEvents(false);
        }
        console.log('[desktop-mascot-mcp] EMERGENCY: forced mouse events ON (Ctrl+Alt+I)');
      } else if ((input.key === 'Home' || input.key === 'home') && input.control) {
        event.preventDefault();
        mainWindow?.webContents.send('locomotion:reset-to-center');
        console.log('[desktop-mascot-mcp] Reset character to center (Ctrl+Home)');
      } else if ((input.key === '0' || input.key === 'Digit0' || input.key === 'Numpad0') && input.control && !input.alt && !input.shift) {
        event.preventDefault();
        mainWindow?.webContents.send('preset:bottom-left-waist-up');
        console.log('[desktop-mascot-mcp] Preset bottom-left waist-up triggered (Ctrl+0)');
      }
    }
  });

  mainWindow.loadFile(path.join(__dirname, '../renderer/VRM.html'));

  mainWindow.on('closed', () => {
    stopCursorPolling();
    mainWindow = null;
  });
}

export function toggleWindowMode(): void {
  if (!mainWindow) return;

  stopCursorPolling();
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
