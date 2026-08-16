import * as THREE from 'three';
import { VRM, VRMLoaderPlugin } from '@pixiv/three-vrm';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { AnimationController } from './AnimationController.js';
import { ExpressionController } from './ExpressionController.js';
import { LocomotionController } from './controllers/LocomotionController.js';

export class VRMRenderer {
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera;
  private renderer: THREE.WebGLRenderer;
  private controls: OrbitControls;
  private vrm: VRM | null = null;
  private clock: THREE.Clock;

  private animation: AnimationController | null = null;
  private expression: ExpressionController | null = null;
  private locomotion: LocomotionController;

  private readonly animationsConfigPath: string;
  private readonly storagePrefix: string;

  constructor(
    canvas: HTMLCanvasElement,
    animationsConfigPath: string = './assets/animations/animations.json',
    storagePrefix: string = 'desktop-mascot',
    cameraConfig?: {
      position: { x: number; y: number; z: number };
      lookAt: { x: number; y: number; z: number };
      fov: number;
    }
  ) {
    this.animationsConfigPath = animationsConfigPath;
    this.storagePrefix = storagePrefix;

    this.scene = new THREE.Scene();
    this.clock = new THREE.Clock();

    const fov = cameraConfig?.fov ?? 45;
    const position = cameraConfig?.position ?? { x: 0, y: 1.0, z: -1.0 };
    const lookAt = cameraConfig?.lookAt ?? { x: 0, y: 1.0, z: 0 };

    this.camera = new THREE.PerspectiveCamera(fov, window.innerWidth / window.innerHeight, 0.1, 100);
    this.camera.position.set(position.x, position.y, position.z);
    this.camera.lookAt(lookAt.x, lookAt.y, lookAt.z);

    this.locomotion = new LocomotionController(
      { fov, distance: Math.abs(position.z) || 1.5, targetY: lookAt.y },
      { x: Math.round(window.innerWidth * 0.5), y: Math.round(window.innerHeight * 0.65) }
    );

    this.renderer = new THREE.WebGLRenderer({ canvas, alpha: false, antialias: true });
    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.renderer.setPixelRatio(window.devicePixelRatio);
    this.renderer.setClearColor(0x000000, 0);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.target.set(0, 1.0, 0);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.05;
    this.controls.update();

    const light = new THREE.DirectionalLight(0xffffff, 1.0);
    light.position.set(1, 1, 1).normalize();
    this.scene.add(light);
    this.scene.add(new THREE.AmbientLight(0xffffff, 0.5));

    window.addEventListener('resize', () => this.onWindowResize());
  }

  async loadVRM(url: string): Promise<void> {
    const loader = new GLTFLoader();
    loader.register((parser) => new VRMLoaderPlugin(parser));

    try {
      const gltf = await loader.loadAsync(url);
      this.vrm = gltf.userData.vrm as VRM;

      if (!this.vrm) {
        throw new Error(`VRM model parse failed for url: ${url}`);
      }

      this.scene.add(this.vrm.scene);

      const mixer = new THREE.AnimationMixer(this.vrm.scene);
      this.animation = new AnimationController(this.vrm, mixer);
      this.expression = new ExpressionController(this.vrm);

      this.locomotion.setVRM(this.vrm);
      this.locomotion.setAnimationController(this.animation);

      try {
        await this.animation.loadAll(this.animationsConfigPath);
      } catch (error) {
        console.error('[desktop-mascot-mcp] Failed to load animations (continuing without):', error);
      }

      this.animation.applyInitialState();
      this.locomotion.startWanderLoop();

      console.log(`[desktop-mascot-mcp] VRM model loaded successfully: ${url}`);
    } catch (err) {
      console.error(`[VRM Error] Failed to load VRM model at "${url}":`, err);
      throw err;
    }
  }

  setVowel(vowel: 'a' | 'i' | 'u' | 'e' | 'o' | null): void {
    this.expression?.setVowel(vowel);
    if (vowel !== null) {
      this.animation?.resetIdleTimer();
    }
  }

  setEmotion(emotion: 'neutral' | 'happy' | 'angry' | 'sad' | 'relaxed' | 'surprised'): void {
    this.expression?.setEmotion(emotion);
    this.animation?.resetIdleTimer();
  }

  playAnimation(name: string): void {
    this.animation?.play(name);
  }

  startAnimation(): void {
    let lastBoundsUpdate = 0;

    const animate = () => {
      requestAnimationFrame(animate);

      const delta = this.clock.getDelta();
      this.animation?.update(delta);
      this.expression?.update();
      this.vrm?.update(delta);
      this.controls.update();

      this.renderer.render(this.scene, this.camera);

      const now = performance.now();
      if (now - lastBoundsUpdate > 50) {
        lastBoundsUpdate = now;
        this.emitScreenBounds();
      }
    };

    animate();
  }

  private emitScreenBounds(): void {
    if (!this.vrm || typeof window === 'undefined' || !(window as any).vrmAPI?.updateCharacterBounds) {
      return;
    }

    try {
      const box = new THREE.Box3().setFromObject(this.vrm.scene);
      if (box.isEmpty()) return;

      const corners = [
        new THREE.Vector3(box.min.x, box.min.y, box.min.z),
        new THREE.Vector3(box.min.x, box.min.y, box.max.z),
        new THREE.Vector3(box.min.x, box.max.y, box.min.z),
        new THREE.Vector3(box.min.x, box.max.y, box.max.z),
        new THREE.Vector3(box.max.x, box.min.y, box.min.z),
        new THREE.Vector3(box.max.x, box.min.y, box.max.z),
        new THREE.Vector3(box.max.x, box.max.y, box.min.z),
        new THREE.Vector3(box.max.x, box.max.y, box.max.z),
      ];

      let minX = Infinity;
      let maxX = -Infinity;
      let minY = Infinity;
      let maxY = -Infinity;

      const halfW = window.innerWidth / 2;
      const halfH = window.innerHeight / 2;

      for (const corner of corners) {
        corner.project(this.camera);
        const screenX = (corner.x * halfW) + halfW;
        const screenY = (-(corner.y * halfH)) + halfH;

        if (screenX < minX) minX = screenX;
        if (screenX > maxX) maxX = screenX;
        if (screenY < minY) minY = screenY;
        if (screenY > maxY) maxY = screenY;
      }

      const padding = 20;
      (window as any).vrmAPI.updateCharacterBounds({
        minX: Math.max(0, Math.round(minX - padding)),
        maxX: Math.min(window.innerWidth, Math.round(maxX + padding)),
        minY: Math.max(0, Math.round(minY - padding)),
        maxY: Math.min(window.innerHeight, Math.round(maxY + padding)),
      });
    } catch {
      // Safe fallback
    }
  }

  animateCameraTo(
    targetPos: { x: number; y: number; z: number },
    targetLookAt: { x: number; y: number; z: number },
    durationMs: number = 800
  ): void {
    const startPos = this.camera.position.clone();
    const startTarget = this.controls.target.clone();
    const endPos = new THREE.Vector3(targetPos.x, targetPos.y, targetPos.z);
    const endTarget = new THREE.Vector3(targetLookAt.x, targetLookAt.y, targetLookAt.z);

    const startTime = performance.now();

    const step = (now: number) => {
      const elapsed = now - startTime;
      const progress = Math.min(1.0, elapsed / durationMs);
      const ease = 1 - Math.pow(1 - progress, 3);

      this.camera.position.lerpVectors(startPos, endPos, ease);
      this.controls.target.lerpVectors(startTarget, endTarget, ease);
      this.controls.update();

      if (progress < 1.0) {
        requestAnimationFrame(step);
      }
    };

    requestAnimationFrame(step);
  }

  applyPresetBottomLeftWaistUp(): void {
    this.locomotion.stop();

    const targetPos = {
      x: Math.round(window.innerWidth * 0.16),
      y: Math.round(window.innerHeight * 0.72),
    };

    this.locomotion.wanderTo(targetPos, 'walk', 1000, () => {
      this.locomotion.startWanderLoop();
    });

    this.animateCameraTo(
      { x: 0, y: 1.18, z: -0.65 },
      { x: 0, y: 1.15, z: 0 },
      1000
    );
  }

  resetToCenterAndDefaultCamera(): void {
    this.locomotion.resetToCenter();
    this.animateCameraTo(
      { x: 0, y: 1.3, z: -1.5 },
      { x: 0, y: 1.2, z: 0 },
      1000
    );
  }

  getVRM(): VRM | null {
    return this.vrm;
  }

  getLocomotion(): LocomotionController {
    return this.locomotion;
  }

  private onWindowResize(): void {
    this.camera.aspect = window.innerWidth / window.innerHeight;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.locomotion.updateBounds(window.innerWidth, window.innerHeight);
  }

  saveCameraState(): void {
    const state = {
      position: {
        x: this.camera.position.x,
        y: this.camera.position.y,
        z: this.camera.position.z,
      },
      target: {
        x: this.controls.target.x,
        y: this.controls.target.y,
        z: this.controls.target.z,
      },
    };
    localStorage.setItem(`${this.storagePrefix}-camera-state`, JSON.stringify(state));
  }

  loadCameraState(): void {
    const stored = localStorage.getItem(`${this.storagePrefix}-camera-state`);
    if (!stored) return;

    try {
      const state = JSON.parse(stored);
      if (state.position) {
        this.camera.position.set(state.position.x, state.position.y, state.position.z);
      }
      if (state.target) {
        this.controls.target.set(state.target.x, state.target.y, state.target.z);
      }
      this.controls.update();
      console.log('[desktop-mascot-mcp] Camera state restored');
    } catch (error) {
      console.error('[desktop-mascot-mcp] Failed to load camera state:', error);
    }
  }
}
