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
    const response = await fetch(configPath);
    const config = await response.json();
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
        console.error(`[desktop-mascot-mcp] Failed to load animation ${animConfig.name}:`, error);
      }
    }

    console.log(`[desktop-mascot-mcp] Loaded ${this.animations.size} animations`);
  }

  /**
   * idle アニメーションがあれば再生、なければデフォルトポーズを適用する。
   * アニメーション読み込み後に必ず呼ぶ。
   */
  applyInitialState(): void {
    if (this.animations.has('idle')) {
      this.play('idle', false);
    } else {
      console.warn('[desktop-mascot-mcp] No idle animation found - applying default pose');
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

    if (!targetState) {
      console.warn(`[desktop-mascot-mcp] Animation not found: ${name}`);
      return;
    }

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
    const leftUpperArm = this.vrm.humanoid.getNormalizedBoneNode('leftUpperArm');
    const rightUpperArm = this.vrm.humanoid.getNormalizedBoneNode('rightUpperArm');
    if (leftUpperArm) leftUpperArm.rotation.z = Math.PI / 3;
    if (rightUpperArm) rightUpperArm.rotation.z = -Math.PI / 3;
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
