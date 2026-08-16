import * as THREE from 'three';
import { VRM, VRMLoaderPlugin } from '@pixiv/three-vrm';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { AnimationController } from './AnimationController.js';
import { ExpressionController } from './ExpressionController.js';

export class VRMRenderer {
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera;
  private renderer: THREE.WebGLRenderer;
  private controls: OrbitControls;
  private vrm: VRM | null = null;
  private clock: THREE.Clock;

  private animation: AnimationController | null = null;
  private expression: ExpressionController | null = null;

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

    const gltf = await loader.loadAsync(url);
    this.vrm = gltf.userData.vrm as VRM;

    if (!this.vrm) {
      throw new Error('Failed to load VRM model');
    }

    this.scene.add(this.vrm.scene);

    const mixer = new THREE.AnimationMixer(this.vrm.scene);
    this.animation = new AnimationController(this.vrm, mixer);
    this.expression = new ExpressionController(this.vrm);

    try {
      await this.animation.loadAll(this.animationsConfigPath);
    } catch (error) {
      console.error('[desktop-mascot-mcp] Failed to load animations (continuing without):', error);
    }

    // アニメーション読み込みの成否にかかわらず初期状態を適用
    this.animation.applyInitialState();

    console.log('[desktop-mascot-mcp] VRM model loaded');
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
    const animate = () => {
      requestAnimationFrame(animate);

      const delta = this.clock.getDelta();
      this.animation?.update(delta);
      this.expression?.update();
      this.vrm?.update(delta);
      this.controls.update();

      this.renderer.render(this.scene, this.camera);
    };

    animate();
  }

  getVRM(): VRM | null {
    return this.vrm;
  }

  private onWindowResize(): void {
    this.camera.aspect = window.innerWidth / window.innerHeight;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(window.innerWidth, window.innerHeight);
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
