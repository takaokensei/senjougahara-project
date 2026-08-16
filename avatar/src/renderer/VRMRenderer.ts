import * as THREE from 'three';
import { VRM, VRMLoaderPlugin } from '@pixiv/three-vrm';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { AnimationController } from './AnimationController.js';
import { ExpressionController } from './ExpressionController.js';
import { LocomotionController } from './controllers/LocomotionController.js';

// Fixed camera configuration for the portrait waist-up view
const FIXED_CAMERA = {
  fov: 28,
  posX: 0,
  posY: 1.22,
  posZ: -0.75,
  lookX: 0,
  lookY: 1.18,
  lookZ: 0,
} as const;

export class VRMRenderer {
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera;
  private renderer: THREE.WebGLRenderer;
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
    // cameraConfig is accepted but ignored — camera is always fixed to the portrait preset
    _cameraConfig?: unknown
  ) {
    this.animationsConfigPath = animationsConfigPath;
    this.storagePrefix = storagePrefix;

    this.scene = new THREE.Scene();
    this.clock = new THREE.Clock();

    // Fixed portrait camera — always looking at the model from the front
    this.camera = new THREE.PerspectiveCamera(FIXED_CAMERA.fov, window.innerWidth / window.innerHeight, 0.1, 100);
    this.camera.position.set(FIXED_CAMERA.posX, FIXED_CAMERA.posY, FIXED_CAMERA.posZ);
    this.camera.lookAt(FIXED_CAMERA.lookX, FIXED_CAMERA.lookY, FIXED_CAMERA.lookZ);

    // Locomotion still drives the avatar's screen position (bottom-left anchor)
    // but wander is never started, so she stays stationary
    this.locomotion = new LocomotionController(
      { fov: FIXED_CAMERA.fov, distance: Math.abs(FIXED_CAMERA.posZ), targetY: FIXED_CAMERA.lookY },
      { x: Math.round(window.innerWidth * 0.15), y: Math.round(window.innerHeight * 0.80) }
    );

    this.renderer = new THREE.WebGLRenderer({ canvas, alpha: false, antialias: true });
    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.renderer.setPixelRatio(window.devicePixelRatio);
    this.renderer.setClearColor(0x000000, 0);

    // Lighting
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
      // Do NOT start wander loop — avatar is pinned to the bottom-left anchor position

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
      // No controls.update() — OrbitControls removed to prevent user camera rotation

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

  // Camera is fixed — no animateCameraTo, no presets, no reset

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
    // Keep camera fixed on resize
    this.camera.position.set(FIXED_CAMERA.posX, FIXED_CAMERA.posY, FIXED_CAMERA.posZ);
    this.camera.lookAt(FIXED_CAMERA.lookX, FIXED_CAMERA.lookY, FIXED_CAMERA.lookZ);
  }

  // Camera state is always fixed — nothing to save or restore
  saveCameraState(): void {}
  loadCameraState(): void {}
}

