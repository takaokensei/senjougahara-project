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
      setIgnoreMouseEvents?: (ignore: boolean, forward?: boolean) => void;
      updateCharacterPosition?: (pos: { x: number; y: number; width?: number; height?: number }) => void;
      onResetToCenter?: (callback: () => void) => void;
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

function showErrorOverlay(title: string, message: string): void {
  const overlay = document.getElementById('error-overlay');
  const msgEl = document.getElementById('error-msg');
  if (overlay) {
    overlay.innerHTML = `<strong>${title}</strong><span>${message}</span>`;
    overlay.style.display = 'block';
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
    setupWindowAwarenessPolling();
    restoreWindowBounds();
    setupBeforeUnload();
    console.log('[Senjougahara] VRM Renderer initialized successfully');
  } catch (error: any) {
    console.error('[Senjougahara] Failed to initialize VRM Renderer:', error);
    const modelPath = config?.vrm?.modelPath || './assets/models/AliciaSolid.vrm';
    showErrorOverlay(
      '⚠️ VRM Model Not Found',
      `Could not load <code>${modelPath}</code><br><br>` +
      `Place a <code>.vrm</code> file (e.g. <code>AliciaSolid.vrm</code>) into:<br>` +
      `📁 <code>avatar/assets/models/</code><br><br>` +
      `<em>(Press <kbd>Ctrl+Shift+I</kbd> or <kbd>F12</kbd> for DevTools)</em>`
    );
  }
}

function setupWindowAwarenessPolling() {
  if (!vrmRenderer) return;
  const locomotion = vrmRenderer.getLocomotion();
  const brainAwarenessUrl = 'http://127.0.0.1:8766/awareness/foreground-window';

  const checkForegroundWindow = async () => {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 1500);
      const res = await fetch(
        `${brainAwarenessUrl}?screen_width=${window.innerWidth}&screen_height=${window.innerHeight}`,
        { signal: controller.signal }
      );
      clearTimeout(timeoutId);

      if (res.ok) {
        const data = await res.json();
        if (data.is_likely_fullscreen_content && data.window) {
          locomotion.avoidArea = {
            x: data.window.x,
            y: data.window.y,
            width: data.window.width,
            height: data.window.height,
          };
        } else {
          locomotion.avoidArea = null;
        }
      }
    } catch {
      // Degraded/disconnected mode: no restriction
      locomotion.avoidArea = null;
    }
  };

  // Immediate check then poll every 6s
  checkForegroundWindow();
  window.setInterval(checkForegroundWindow, 6000);
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

let subtitleTimeout: number | null = null;

function showSubtitle(text: string, durationMs?: number): void {
  const subtitleEl = document.getElementById('subtitle-overlay');
  if (!subtitleEl) return;

  if (subtitleTimeout) {
    clearTimeout(subtitleTimeout);
    subtitleTimeout = null;
  }

  // Extract Portuguese text if format is 'Japanese (Portuguese)'
  let displayText = text.trim();
  const parenMatch = displayText.match(/\(([^)]+)\)/);
  if (parenMatch) {
    displayText = parenMatch[1].trim();
  }

  subtitleEl.textContent = displayText;
  subtitleEl.classList.add('visible');

  if (durationMs && durationMs > 0) {
    subtitleTimeout = window.setTimeout(() => {
      hideSubtitle();
    }, durationMs);
  }
}

function hideSubtitle(): void {
  const subtitleEl = document.getElementById('subtitle-overlay');
  if (subtitleEl) {
    subtitleEl.classList.remove('visible');
  }
  if (subtitleTimeout) {
    clearTimeout(subtitleTimeout);
    subtitleTimeout = null;
  }
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
    hideSubtitle();
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
    hideSubtitle();
  };

  audio.play().catch((err) => {
    console.warn('[Senjougahara] audio.play() failed:', err);
    // If browser blocks audio autoplay, dismiss subtitle after estimated duration
    const subEl = document.getElementById('subtitle-overlay');
    const textLen = subEl?.textContent?.length || 20;
    const estTime = Math.max(3000, textLen * 85);
    subtitleTimeout = window.setTimeout(hideSubtitle, estTime);
  });
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

  window.vrmAPI.onResetToCenter?.(() => {
    console.log('[Senjougahara] Received reset-to-center command');
    vrmRenderer?.getLocomotion().resetToCenter();
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

      // Display Portuguese subtitle
      const caption = command.caption || command.text;
      if (caption) {
        const estimatedDuration = Math.max(3000, caption.length * 85);
        showSubtitle(caption, command.audio_url ? undefined : estimatedDuration);
      }

      if (command.audio_url) {
        playAudioWithLipSync(command.audio_url);
      }
    } else if (command.type === 'state_change') {
      const state = command.state;
      if (state === 'LISTENING' || state === 'THINKING' || state === 'ERROR') {
        hideSubtitle();
      }

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