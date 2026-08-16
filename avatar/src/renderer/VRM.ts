import { VRMRenderer } from './VRMRenderer.js';

// Declare extended vrmAPI interface
declare global {
  interface Window {
    vrmAPI?: {
      onVowel: (callback: (vowel: 'a' | 'i' | 'u' | 'e' | 'o' | null) => void) => void;
      onEmotion: (callback: (emotion: 'neutral' | 'happy' | 'angry' | 'sad' | 'relaxed' | 'surprised') => void) => void;
      onSpeak: (callback: (data: { text: string; emotion?: string }) => void) => void;
      onAnimation: (callback: (animation: string) => void) => void;
      setWindowBounds: (bounds: { x: number; y: number; width: number; height: number }) => void;
      onBridgeCommand?: (callback: (command: any) => void) => void;
      onBrainConnected?: (callback: () => void) => void;
      sendActivate?: (source: 'hotkey' | 'wake_word' | 'click') => void;
      sendConfirmationResponse?: (response: { request_id: string; confirmed: boolean }) => void;
    };
  }
}

interface Config {
  vrm: {
    modelPath: string;
  };
  animations?: {
    configPath: string;
  };
  camera: {
    position: { x: number; y: number; z: number };
    lookAt: { x: number; y: number; z: number };
    fov: number;
  };
  window: {
    storagePrefix: string;
  };
}

let vrmRenderer: VRMRenderer | null = null;
let config: Config;
let currentAudio: HTMLAudioElement | null = null;
let lipSyncInterval: number | null = null;

async function loadConfig(): Promise<Config> {
  try {
    const response = await fetch('./config.json');
    if (!response.ok) {
      throw new Error(`Failed to load config.json: ${response.statusText}`);
    }
    return await response.json();
  } catch (error) {
    console.log('[Senjougahara] Using default configuration');
    return {
      vrm: {
        modelPath: './assets/models/AliciaSolid.vrm'
      },
      animations: {
        configPath: './assets/animations/animations.json'
      },
      camera: {
        position: { x: 0, y: 1.3, z: -1.5 },
        lookAt: { x: 0, y: 1.2, z: 0 },
        fov: 45
      },
      window: {
        storagePrefix: 'senjougahara'
      }
    };
  }
}

async function init() {
  const canvas = document.getElementById('canvas') as HTMLCanvasElement;
  if (!canvas) {
    console.error('Canvas element not found');
    return;
  }

  try {
    config = await loadConfig();
    const animationsConfigPath = config.animations?.configPath ?? './assets/animations/animations.json';

    vrmRenderer = new VRMRenderer(
      canvas,
      animationsConfigPath,
      config.window.storagePrefix,
      config.camera
    );
    await vrmRenderer.loadVRM(config.vrm.modelPath);
    vrmRenderer.loadCameraState();
    vrmRenderer.startAnimation();
    setupIPCListeners();
    setupCanvasClick(canvas);
    restoreWindowBounds();
    setupBeforeUnload();
    console.log('[Senjougahara] VRM Renderer initialized');
  } catch (error) {
    console.error('Failed to initialize VRM Renderer:', error);
  }
}

function setupCanvasClick(canvas: HTMLCanvasElement) {
  canvas.addEventListener('dblclick', () => {
    console.log('[Senjougahara] Canvas double clicked -> send activate');
    window.vrmAPI?.sendActivate?.('click');
  });
}

function restoreWindowBounds() {
  const storageKey = `${config.window.storagePrefix}-window-bounds`;
  const stored = localStorage.getItem(storageKey);
  if (!stored || !window.vrmAPI) return;

  try {
    const bounds = JSON.parse(stored);
    if (bounds.x != null && bounds.y != null && bounds.width && bounds.height) {
      window.vrmAPI.setWindowBounds(bounds);
    }
  } catch (error) {
    console.error('Failed to restore window bounds:', error);
  }
}

function setupBeforeUnload() {
  window.addEventListener('beforeunload', () => {
    if (vrmRenderer) {
      vrmRenderer.saveCameraState();
    }
    const bounds = {
      x: window.screenX,
      y: window.screenY,
      width: window.outerWidth,
      height: window.outerHeight,
    };
    const storageKey = `${config.window.storagePrefix}-window-bounds`;
    localStorage.setItem(storageKey, JSON.stringify(bounds));
  });
}

function playAudioWithLipSync(audioUrl: string) {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }
  if (lipSyncInterval) {
    clearInterval(lipSyncInterval);
    lipSyncInterval = null;
  }

  const audio = new Audio(audioUrl);
  currentAudio = audio;

  const vowels: Array<'a' | 'i' | 'u' | 'e' | 'o'> = ['a', 'i', 'u', 'e', 'o'];
  let vowelIdx = 0;

  audio.onplay = () => {
    lipSyncInterval = window.setInterval(() => {
      if (vrmRenderer) {
        const vowel = vowels[vowelIdx % vowels.length];
        vrmRenderer.setVowel(vowel);
        vowelIdx++;
      }
    }, 120);
  };

  audio.onended = () => {
    if (lipSyncInterval) {
      clearInterval(lipSyncInterval);
      lipSyncInterval = null;
    }
    if (vrmRenderer) {
      vrmRenderer.setVowel(null);
    }
  };

  audio.onerror = (e) => {
    console.warn('[Senjougahara] Audio playback error:', e);
    if (lipSyncInterval) {
      clearInterval(lipSyncInterval);
      lipSyncInterval = null;
    }
    if (vrmRenderer) {
      vrmRenderer.setVowel(null);
    }
  };

  audio.play().catch((err) => console.warn('[Senjougahara] audio.play() failed:', err));
}

function setupIPCListeners() {
  if (!window.vrmAPI) {
    console.warn('vrmAPI not available - IPC communication disabled');
    return;
  }

  window.vrmAPI.onVowel((vowel) => {
    vrmRenderer?.setVowel(vowel);
  });

  window.vrmAPI.onEmotion((emotion) => {
    vrmRenderer?.setEmotion(emotion);
  });

  window.vrmAPI.onSpeak((data) => {
    if (vrmRenderer && data.emotion) {
      vrmRenderer.setEmotion(data.emotion as any);
    }
  });

  window.vrmAPI.onAnimation((animation) => {
    vrmRenderer?.playAnimation(animation);
  });

  // Senjougahara Bridge Commands Handler
  window.vrmAPI.onBridgeCommand?.((command) => {
    console.log('[Senjougahara] Received bridge command:', command);
    if (!vrmRenderer) return;

    if (command.type === 'speak') {
      if (command.emotion) {
        vrmRenderer.setEmotion(command.emotion);
      }
      if (command.animation && command.animation !== 'idle') {
        vrmRenderer.playAnimation(command.animation);
      }
      if (command.audio_url) {
        playAudioWithLipSync(command.audio_url);
      }
    } else if (command.type === 'state_change') {
      const state = command.state;
      switch (state) {
        case 'LISTENING':
          vrmRenderer.setEmotion('neutral');
          break;
        case 'THINKING':
          vrmRenderer.setEmotion('relaxed');
          vrmRenderer.playAnimation('thinking');
          break;
        case 'HAPPY':
          vrmRenderer.setEmotion('happy');
          break;
        case 'CONFUSED':
          vrmRenderer.setEmotion('surprised');
          break;
        case 'ANNOYED':
          vrmRenderer.setEmotion('angry');
          break;
        case 'ERROR':
          vrmRenderer.setEmotion('sad');
          break;
        case 'IDLE':
          vrmRenderer.setEmotion('neutral');
          break;
      }
    }
  });
}

init();