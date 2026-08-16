/// <reference types="node" />

import { app, BrowserWindow } from 'electron';
import { createWindow, getMainWindow, isRecreating } from './window';
import { startHttpServer, closeHttpServer } from './httpServer';
import { registerIpcHandlers } from './ipcHandlers';
import { getBridgeServer } from './bridge-server';

app.on('window-all-closed', () => {
  // ウィンドウ再作成中は終了しない
  if (isRecreating()) return;

  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.whenReady().then(async () => {
  console.error('Desktop Mascot VRM Window started');
  createWindow();
  startHttpServer();
  registerIpcHandlers();

  // Start Senjougahara bridge server for Python brain integration
  const bridgeServer = getBridgeServer();
  const win = getMainWindow();
  if (win) {
    bridgeServer.setMainWindow(win);
  }
  try {
    await bridgeServer.start();
  } catch (err) {
    console.error('[Bridge] Failed to start bridge server:', err);
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
      const newWin = getMainWindow();
      if (newWin) {
        bridgeServer.setMainWindow(newWin);
      }
    }
  });
});

// Cleanup on quit
app.on('before-quit', () => {
  closeHttpServer();
  getBridgeServer().stop();
});
