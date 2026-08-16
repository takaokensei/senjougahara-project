const { contextBridge, ipcRenderer } = require('electron');

// Expose protected methods that allow the renderer process to use
// the ipcRenderer without exposing the entire object
contextBridge.exposeInMainWorld('vrmAPI', {
  onVowel: (callback: (vowel: 'a' | 'i' | 'u' | 'e' | 'o' | null) => void) => {
    ipcRenderer.on('vrm-vowel', (_event: any, vowel: any) => callback(vowel));
  },
  onEmotion: (callback: (emotion: 'neutral' | 'happy' | 'angry' | 'sad' | 'relaxed' | 'surprised') => void) => {
    ipcRenderer.on('vrm-emotion', (_event: any, emotion: any) => callback(emotion));
  },
  onSpeak: (callback: (data: { text: string; emotion?: string }) => void) => {
    ipcRenderer.on('vrm-speak', (_event: any, data: any) => callback(data));
  },
  onAnimation: (callback: (animation: string) => void) => {
    ipcRenderer.on('vrm-animation', (_event: any, animation: any) => callback(animation));
  },
  setWindowBounds: (bounds: { x: number; y: number; width: number; height: number }) => {
    ipcRenderer.send('set-window-bounds', bounds);
  },
  setIgnoreMouseEvents: (ignore: boolean, forward?: boolean) => {
    ipcRenderer.send('window:set-ignore-mouse-events', ignore, { forward: forward ?? true });
  },
  updateCharacterPosition: (pos: { x: number; y: number; width?: number; height?: number }) => {
    ipcRenderer.send('locomotion:update-position', pos);
  },
  onResetToCenter: (callback: () => void) => {
    ipcRenderer.on('locomotion:reset-to-center', () => callback());
  },
  // Senjougahara Bridge APIs
  onBridgeCommand: (callback: (command: any) => void) => {
    ipcRenderer.on('bridge:command', (_event: any, command: any) => callback(command));
  },
  onBrainConnected: (callback: () => void) => {
    ipcRenderer.on('bridge:brain_connected', () => callback());
  },
  sendActivate: (source: 'hotkey' | 'wake_word' | 'click') => {
    ipcRenderer.send('bridge:activate', source);
  },
  sendConfirmationResponse: (response: { request_id: string; confirmed: boolean }) => {
    ipcRenderer.send('bridge:confirmation_response', response);
  },
});
