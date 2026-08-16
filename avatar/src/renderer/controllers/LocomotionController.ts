/**
 * avatar/src/renderer/controllers/LocomotionController.ts
 *
 * Coordinates character locomotion, smooth spatial interpolation across the screen,
 * and spontaneous wander behaviors.
 */

import type { VRM } from '@pixiv/three-vrm';
import type { AnimationController } from '../AnimationController.js';
import {
  ScreenPoint,
  ScreenBounds,
  CameraParameters,
  screenToWorld,
  interpolateScreenPoint,
  calculateFacingAngle,
} from '../logic/screenPosition.js';
import { pickWanderTarget, AvoidArea, WanderOptions } from '../logic/wander.js';

export class LocomotionController {
  private vrm: VRM | null = null;
  private animationController: AnimationController | null = null;
  private cameraParams: CameraParameters;
  private bounds: ScreenBounds;

  private currentScreenPos: ScreenPoint;
  private isMoving = false;
  private wanderTimer: number | null = null;
  private moveRafId: number | null = null;

  public enabled = true;
  public avoidArea: AvoidArea | null = null;

  constructor(
    cameraParams: CameraParameters = { fov: 45, distance: 1.5, targetY: 1.0 },
    initialScreenPos?: ScreenPoint
  ) {
    this.cameraParams = cameraParams;
    this.bounds = {
      width: typeof window !== 'undefined' ? window.innerWidth : 1920,
      height: typeof window !== 'undefined' ? window.innerHeight : 1080,
    };
    this.currentScreenPos = initialScreenPos || {
      x: Math.round(this.bounds.width / 2),
      y: Math.round(this.bounds.height / 2),
    };
  }

  setVRM(vrm: VRM | null): void {
    this.vrm = vrm;
    if (vrm) {
      // Always face front — never inherit a rotated state from wander
      vrm.scene.rotation.y = 0;
    }
    this.applyPosition();
  }

  setAnimationController(anim: AnimationController | null): void {
    this.animationController = anim;
  }

  updateBounds(width: number, height: number): void {
    this.bounds = { width, height };
  }

  getCurrentPosition(): ScreenPoint {
    return { ...this.currentScreenPos };
  }

  startWanderLoop(minDelayMs = 25000, maxDelayMs = 50000): void {
    this.stop();
    if (!this.enabled) return;

    const scheduleNext = () => {
      if (!this.enabled) return;
      const delay = Math.round(minDelayMs + Math.random() * (maxDelayMs - minDelayMs));
      this.wanderTimer = window.setTimeout(() => {
        if (!this.isMoving && this.enabled) {
          const wanderOpts: WanderOptions = {};
          if (this.avoidArea) {
            wanderOpts.avoidArea = this.avoidArea;
          }
          const { target, speed, durationMs } = pickWanderTarget(
            this.currentScreenPos,
            this.bounds,
            Math.random,
            wanderOpts
          );
          this.wanderTo(target, speed, durationMs, scheduleNext);
        } else {
          scheduleNext();
        }
      }, delay);
    };

    scheduleNext();
  }

  wanderTo(
    target: ScreenPoint,
    speed: 'walk' | 'run',
    durationMs: number,
    onComplete?: () => void
  ): void {
    if (this.isMoving) return;
    this.isMoving = true;

    const startPos = { ...this.currentScreenPos };
    const facing = calculateFacingAngle(startPos, target);
    if (this.vrm) {
      this.vrm.scene.rotation.y = facing;
    }

    // Try to trigger walk/run clip in AnimationController (gracefully fall back if not in config)
    try {
      this.animationController?.play(speed);
    } catch {
      // If walk/run clip not found, continues translating in idle pose
    }

    const startTime = performance.now();

    const step = (now: number) => {
      const elapsed = now - startTime;
      const progress = Math.min(1.0, elapsed / durationMs);

      this.currentScreenPos = interpolateScreenPoint(startPos, target, progress);
      this.applyPosition();

      if (progress < 1.0) {
        this.moveRafId = requestAnimationFrame(step);
      } else {
        this.isMoving = false;
        if (this.vrm) {
          this.vrm.scene.rotation.y = 0;
        }
        try {
          this.animationController?.play('idle');
        } catch {}
        onComplete?.();
      }
    };

    this.moveRafId = requestAnimationFrame(step);
  }

  private applyPosition(): void {
    if (!this.vrm) return;
    const world = screenToWorld(this.currentScreenPos, this.bounds, this.cameraParams);
    this.vrm.scene.position.set(world.x, world.y, world.z);

    if (typeof window !== 'undefined' && (window as any).vrmAPI?.updateCharacterPosition) {
      try {
        (window as any).vrmAPI.updateCharacterPosition({
          x: this.currentScreenPos.x,
          y: this.currentScreenPos.y,
          width: 280,
          height: 480,
        });
      } catch {
        // Safe fallback
      }
    }
  }

  resetToCenter(): void {
    this.stop();
    const target: ScreenPoint = {
      x: Math.round(this.bounds.width / 2),
      y: Math.round(this.bounds.height * 0.65),
    };
    this.wanderTo(target, 'walk', 1200, () => {
      this.startWanderLoop();
    });
  }

  stop(): void {
    if (this.wanderTimer) {
      clearTimeout(this.wanderTimer);
      this.wanderTimer = null;
    }
    if (this.moveRafId) {
      cancelAnimationFrame(this.moveRafId);
      this.moveRafId = null;
    }
    this.isMoving = false;
  }
}
