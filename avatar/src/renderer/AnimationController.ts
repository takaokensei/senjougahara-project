import * as THREE from 'three';
import { VRM } from '@pixiv/three-vrm';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { VRMAnimationLoaderPlugin, createVRMAnimationClip } from '@pixiv/three-vrm-animation';
import {
  parseIdleVariationConfig,
  pickIdleDelay,
  pickIdleAnimation,
  DEFAULT_IDLE_VARIATION,
} from './logic/idleVariation.js';
import type { IdleVariationConfig } from './logic/idleVariation.js';

interface AnimationConfig {
  name: string;
  file: string;
  loop: boolean;
  fadeTime: number;
  returnToIdle: boolean;
  category: string;
  description: string;
}

interface AnimationState {
  clip: THREE.AnimationClip;
  action: THREE.AnimationAction;
  config: AnimationConfig;
}

/** VRMA ファイルから AnimationClip を読み込む関数。見つからなければ null を返す */
export type VrmAnimationLoader = (file: string, vrm: VRM) => Promise<THREE.AnimationClip | null>;

/**
 * 既定の VRMA ローダー（GLTFLoader + VRMAnimationLoaderPlugin）
 */
export const defaultVrmAnimationLoader: VrmAnimationLoader = async (file, vrm) => {
  const loader = new GLTFLoader();
  loader.register((parser) => new VRMAnimationLoaderPlugin(parser));

  const gltf = await loader.loadAsync(`./assets/animations/${file}`);
  const vrmAnimations = gltf.userData.vrmAnimations;

  if (!vrmAnimations || vrmAnimations.length === 0) {
    return null;
  }
  return createVRMAnimationClip(vrmAnimations[0], vrm);
};

/**
 * アニメーションの読み込み・再生・アイドルバリエーションを管理
 */
export class AnimationController {
  private animations: Map<string, AnimationState> = new Map();
  private currentAnimation: string = '';

  private finishedListeners: Array<(e: any) => void> = [];

  private idleVariationTimer: ReturnType<typeof setTimeout> | null = null;
  private idleVariation: IdleVariationConfig = { ...DEFAULT_IDLE_VARIATION };

  constructor(
    private vrm: VRM,
    private mixer: THREE.AnimationMixer,
    private loadClip: VrmAnimationLoader = defaultVrmAnimationLoader,
    private random: () => number = Math.random
  ) {}

  /**
   * animations.json からアニメーションを一括読み込み
   */
  async loadAll(configPath: string): Promise<void> {
    let config: any = null;
    try {
      const response = await fetch(configPath);
      if (response && response.ok === false) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      config = await response.json();
    } catch (err) {
      console.warn(
        `[desktop-mascot-mcp] Could not load animations config from '${configPath}' (${err}). ` +
        `Make sure 'animations.json' exists. You can initialize it from template via:\n` +
        `  copy avatar\\assets\\animations\\animations.example.json avatar\\assets\\animations\\animations.json`
      );
      return;
    }

    if (!config || !config.animations || config.animations.length === 0) {
      console.warn(
        `[desktop-mascot-mcp] Found 0 animation configs in '${configPath}'. ` +
        `Ensure 'animations.json' contains your animation list or copy from template:\n` +
        `  copy avatar\\assets\\animations\\animations.example.json avatar\\assets\\animations\\animations.json`
      );
      return;
    }

    console.log(`[desktop-mascot-mcp] Found ${config.animations.length} animation configs`);

    this.idleVariation = parseIdleVariationConfig(config.config?.idleVariation);
    console.log(
      `[desktop-mascot-mcp] Idle variation config loaded: enabled=${this.idleVariation.enabled}, ` +
      `delay=${this.idleVariation.delayMin}-${this.idleVariation.delayMax}ms, ` +
      `animations=${this.idleVariation.animations.join(',')}`
    );

    for (const animConfig of config.animations) {
      try {
        await this.loadAnimation(animConfig);
      } catch (error) {
        console.warn(`[desktop-mascot-mcp] Animation file '${animConfig.file}' for '${animConfig.name}' not found:`, error);
      }
    }

    console.log(`[desktop-mascot-mcp] Loaded ${this.animations.size} animations`);
  }

  private isTransitioningToDefaultPose = false;
  private transitionStartTime = 0;
  private transitionDuration = 0.5;
  private startBoneRotations: Map<string, { x: number; y: number; z: number }> = new Map();
  private idleClock = 0;

  /**
   * idle アニメーションがあれば再生、なければデフォルトポーズを適用する。
   * アニメーション読み込み後に必ず呼ぶ。
   */
  applyInitialState(): void {
    if (this.animations.has('idle')) {
      this.play('idle', false);
    } else {
      console.warn('[desktop-mascot-mcp] No idle animation found - applying default pose');
      this.currentAnimation = 'idle';
      this.setDefaultPose();
    }
    this.scheduleIdleVariation();
  }

  private async loadAnimation(config: AnimationConfig): Promise<void> {
    const clip = await this.loadClip(config.file, this.vrm);

    if (!clip) {
      console.warn(`[desktop-mascot-mcp] No VRM animations found in ${config.file}`);
      return;
    }

    const action = this.mixer.clipAction(clip);

    action.loop = config.loop ? THREE.LoopRepeat : THREE.LoopOnce;
    action.clampWhenFinished = true;

    if (!config.loop && config.returnToIdle) {
      const listener = (e: any) => {
        if (e.action === action) {
          this.play('idle', false);
        }
      };
      this.finishedListeners.push(listener);
      this.mixer.addEventListener('finished', listener);
    }

    this.animations.set(config.name, { clip, action, config });
  }

  /**
   * アニメーションをクロスフェードで再生
   */
  play(name: string, resetTimer: boolean = true): void {
    const targetState = this.animations.get(name);
    const currentState = this.animations.get(this.currentAnimation);

    // Fallback when returning to or playing 'idle' without an idle animation clip
    if (name === 'idle' && !targetState) {
      if (currentState) {
        const fadeTime = 0.5;
        currentState.action.fadeOut(fadeTime);
      }
      this.currentAnimation = 'idle';
      this.startDefaultPoseTransition(0.5);
      if (resetTimer) this.resetIdleTimer();
      return;
    }

    if (!targetState) {
      console.warn(`[desktop-mascot-mcp] Animation not found: ${name}`);
      return;
    }

    this.isTransitioningToDefaultPose = false;

    if (!currentState) {
      targetState.action.reset().play();
      this.currentAnimation = name;
      console.log(`[desktop-mascot-mcp] Playing animation: ${name}`);
      if (resetTimer) this.resetIdleTimer();
      return;
    }

    if (name === this.currentAnimation) return;

    const fadeTime = targetState.config.fadeTime;
    targetState.action.reset().fadeIn(fadeTime).play();
    currentState.action.fadeOut(fadeTime);
    this.currentAnimation = name;

    console.log(`[desktop-mascot-mcp] Playing animation: ${name} (fade: ${fadeTime}s)`);
    if (resetTimer) this.resetIdleTimer();
  }

  /**
   * アイドルタイマーをリセット（外部からの操作通知用）
   */
  resetIdleTimer(): void {
    this.scheduleIdleVariation();
  }

  private setDefaultPose(): void {
    if (!this.vrm.humanoid) return;
    try {
      (this.vrm.humanoid as any).resetNormalizedPose?.();
    } catch {
      // ignore
    }
    const leftUpperArm = this.vrm.humanoid.getNormalizedBoneNode('leftUpperArm');
    const rightUpperArm = this.vrm.humanoid.getNormalizedBoneNode('rightUpperArm');
    if (leftUpperArm && leftUpperArm.rotation) leftUpperArm.rotation.z = Math.PI / 3;
    if (rightUpperArm && rightUpperArm.rotation) rightUpperArm.rotation.z = -Math.PI / 3;
  }

  private startDefaultPoseTransition(durationSec: number = 0.5): void {
    this.isTransitioningToDefaultPose = true;
    this.transitionStartTime = performance.now();
    this.transitionDuration = durationSec;

    this.startBoneRotations.clear();
    if (!this.vrm.humanoid) return;

    const boneNames = [
      'leftUpperArm', 'rightUpperArm', 'leftLowerArm', 'rightLowerArm',
      'leftHand', 'rightHand', 'head', 'neck', 'spine', 'chest'
    ];

    for (const name of boneNames) {
      const node = this.vrm.humanoid.getNormalizedBoneNode(name as any);
      if (node && node.rotation) {
        this.startBoneRotations.set(name, {
          x: node.rotation.x,
          y: node.rotation.y,
          z: node.rotation.z,
        });
      }
    }
  }

  private updateDefaultPoseTransition(): void {
    if (!this.vrm.humanoid) return;

    if (this.isTransitioningToDefaultPose) {
      const elapsed = (performance.now() - this.transitionStartTime) / 1000;
      const progress = Math.min(1.0, elapsed / this.transitionDuration);
      // Cubic ease out
      const t = 1 - Math.pow(1 - progress, 3);

      const targetRotations: Record<string, { x: number; y: number; z: number }> = {
        leftUpperArm: { x: 0, y: 0, z: Math.PI / 3 },
        rightUpperArm: { x: 0, y: 0, z: -Math.PI / 3 },
        leftLowerArm: { x: 0, y: 0, z: 0 },
        rightLowerArm: { x: 0, y: 0, z: 0 },
        leftHand: { x: 0, y: 0, z: 0 },
        rightHand: { x: 0, y: 0, z: 0 },
        head: { x: 0, y: 0, z: 0 },
        neck: { x: 0, y: 0, z: 0 },
        spine: { x: 0, y: 0, z: 0 },
        chest: { x: 0, y: 0, z: 0 },
      };

      for (const [name, target] of Object.entries(targetRotations)) {
        const node = this.vrm.humanoid.getNormalizedBoneNode(name as any);
        const start = this.startBoneRotations.get(name) || { x: 0, y: 0, z: 0 };
        if (node && node.rotation) {
          node.rotation.x = start.x + (target.x - start.x) * t;
          node.rotation.y = start.y + (target.y - start.y) * t;
          node.rotation.z = start.z + (target.z - start.z) * t;
        }
      }

      if (progress >= 1.0) {
        this.isTransitioningToDefaultPose = false;
        this.setDefaultPose();
      }
    } else if (this.currentAnimation === 'idle' && !this.animations.has('idle')) {
      // Subtle procedural breathing micro-motion while resting in idle
      const breath = Math.sin(this.idleClock * 2.0);
      const chest = this.vrm.humanoid.getNormalizedBoneNode('chest');
      const spine = this.vrm.humanoid.getNormalizedBoneNode('spine');
      const leftUpperArm = this.vrm.humanoid.getNormalizedBoneNode('leftUpperArm');
      const rightUpperArm = this.vrm.humanoid.getNormalizedBoneNode('rightUpperArm');

      if (chest && chest.rotation) chest.rotation.x = breath * 0.015;
      if (spine && spine.rotation) spine.rotation.x = breath * 0.01;
      if (leftUpperArm && leftUpperArm.rotation) leftUpperArm.rotation.z = (Math.PI / 3) + (breath * 0.01);
      if (rightUpperArm && rightUpperArm.rotation) rightUpperArm.rotation.z = (-Math.PI / 3) - (breath * 0.01);
    }
  }

  private scheduleIdleVariation(): void {
    if (!this.idleVariation.enabled || this.idleVariation.animations.length === 0) return;

    if (this.idleVariationTimer !== null) {
      clearTimeout(this.idleVariationTimer);
    }

    const delay = pickIdleDelay(this.idleVariation, this.random());

    this.idleVariationTimer = globalThis.setTimeout(() => {
      this.playIdleVariation();
    }, delay);
  }

  private playIdleVariation(): void {
    if (this.currentAnimation !== 'idle') return;

    const animation = pickIdleAnimation(this.idleVariation.animations, this.random())!;

    console.log(`[desktop-mascot-mcp] Playing idle variation: ${animation}`);
    this.play(animation, false);
    this.scheduleIdleVariation();
  }

  /**
   * フレームごとの更新（レンダリングループから呼び出す）
   */
  update(delta: number): void {
    this.mixer.update(delta);
    this.idleClock += delta;
    this.updateDefaultPoseTransition();
  }

  dispose(): void {
    for (const listener of this.finishedListeners) {
      this.mixer.removeEventListener('finished', listener);
    }
    this.finishedListeners = [];
    this.mixer.stopAllAction();
    if (this.idleVariationTimer !== null) {
      clearTimeout(this.idleVariationTimer);
      this.idleVariationTimer = null;
    }
  }
}
