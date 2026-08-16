import { VRMRenderer } from './VRMRenderer.js';

// Declare vrmAPI interface
declare global {
  interface Window {
    vrmAPI: {
      onVowel: (callback: (vowel: 'a' | 'i' | 'u' | 'e' | 'o' | null) => void) => void;
      onEmotion: (callback: (emotion: 'neutral' | 'happy' | 'angry' | 'sad' | 'relaxed' | 'surprised') => void) => void;
      onSpeak: (callback: (data: { text: string; emotion?: string }) => void) => void;
      onAnimation: (callback: (animation: string) => void) => void;
      setWindowBounds: (bounds: { x: number; y: number; width: number; height: number }) => void;
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

async function loadConfig(): Promise<Config> {
  try {
    const response = await fetch('./config.json');
    if (!response.ok) {
      throw new Error(`Failed to load config.json: ${response.statusText}`);
    }
    return await response.json();
  } catch (error) {
    console.error('[desktop-mascot-mcp] Failed to load config.json, using defaults:', error);
    // Fallback to default configuration
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
        storagePrefix: 'desktop-mascot'
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
    // Load configuration
    config = await loadConfig();
    console.log('[desktop-mascot-mcp] Configuration loaded:', config);

    const animationsConfigPath = config.animations?.configPath ?? './assets/animations/animations.json';

    vrmRenderer = new VRMRenderer(
      canvas,
      animationsConfigPath,
      config.window.storagePrefix,
      config.camera
    );
    await vrmRenderer.loadVRM(config.vrm.modelPath);
    vrmRenderer.loadCameraState(); // カメラ状態を復元
    vrmRenderer.startAnimation();
    setupIPCListeners();
    restoreWindowBounds(); // ウィンドウ状態を復元
    setupBeforeUnload(); // ウィンドウを閉じる前に状態を保存
    console.log('[desktop-mascot-mcp] VRM Renderer initialized');
  } catch (error) {
    console.error('Failed to initialize VRM Renderer:', error);
  }
}

function restoreWindowBounds() {
  const storageKey = `${config.window.storagePrefix}-window-bounds`;
  const stored = localStorage.getItem(storageKey);
  if (!stored || !window.vrmAPI) return;

  try {
    const bounds = JSON.parse(stored);
    if (bounds.x != null && bounds.y != null && bounds.width && bounds.height) {
      window.vrmAPI.setWindowBounds(bounds);
      console.log('[desktop-mascot-mcp] Window bounds restored');
    }
  } catch (error) {
    console.error('[desktop-mascot-mcp] Failed to restore window bounds:', error);
  }
}

function setupBeforeUnload() {
  window.addEventListener('beforeunload', () => {
    if (vrmRenderer) {
      vrmRenderer.saveCameraState();
    }

    // Save window bounds
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

function setupIPCListeners() {
  if (!window.vrmAPI) {
    console.warn('vrmAPI not available - IPC communication disabled');
    return;
  }

  // Listen for vowel changes
  window.vrmAPI.onVowel((vowel) => {
    if (vrmRenderer) {
      vrmRenderer.setVowel(vowel);
    }
  });

  // Listen for emotion changes
  window.vrmAPI.onEmotion((emotion) => {
    if (vrmRenderer) {
      vrmRenderer.setEmotion(emotion);
    }
  });

  // Listen for speak commands
  window.vrmAPI.onSpeak((data) => {
    if (vrmRenderer && data.emotion) {
      const emotion = data.emotion as 'neutral' | 'happy' | 'angry' | 'sad' | 'relaxed' | 'surprised';
      vrmRenderer.setEmotion(emotion);
    }
  });

  // Listen for animation commands
  window.vrmAPI.onAnimation((animation) => {
    if (vrmRenderer) {
      vrmRenderer.playAnimation(animation);
    }
  });
}

init();
