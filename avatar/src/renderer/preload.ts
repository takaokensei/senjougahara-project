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
});
