import * as fs from 'fs';
import * as path from 'path';
import { app, BrowserWindow } from 'electron';
import { createWindow, getMainWindow, isRecreating } from './window';
import { startHttpServer, closeHttpServer } from './httpServer';
import { registerIpcHandlers } from './ipcHandlers';
import { getBridgeServer } from './bridge-server';

function checkVrmModels(): void {
  const modelsDir = path.join(__dirname, '../renderer/assets/models');
  const srcModelsDir = path.join(__dirname, '../../assets/models');
  
  const hasModels = (fs.existsSync(modelsDir) && fs.readdirSync(modelsDir).some(f => f.toLowerCase().endsWith('.vrm'))) ||
                    (fs.existsSync(srcModelsDir) && fs.readdirSync(srcModelsDir).some(f => f.toLowerCase().endsWith('.vrm')));

  if (!hasModels) {
    console.warn('\n' + '='.repeat(64));
    console.warn('  ⚠️  [AVATAR WARNING] No .vrm model found in avatar/assets/models/!');
    console.warn('  The avatar window will open, but will remain transparent/invisible');
    console.warn('  until you place a .vrm character model (e.g. AliciaSolid.vrm) in:');
    console.warn(`  📁 ${path.resolve(__dirname, '../../assets/models/')}`);
    console.warn('  See README.md for instructions and free VRM download links.');
    console.warn('='.repeat(64) + '\n');
  }
}

app.on('window-all-closed', () => {
  // ウィンドウ再作成中は終了しない
  if (isRecreating()) return;

  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.whenReady().then(async () => {
  console.error('Desktop Mascot VRM Window started');
  checkVrmModels();
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
