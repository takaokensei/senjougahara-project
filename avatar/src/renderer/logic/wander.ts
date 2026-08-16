/**
 * avatar/src/renderer/logic/wander.ts
 *
 * Spontaneous wandering and target picking logic for the VRM avatar.
 */

import { ScreenPoint, ScreenBounds, calculateScreenDistance } from './screenPosition.js';

export interface AvoidArea {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface WanderTarget {
  target: ScreenPoint;
  speed: 'walk' | 'run';
  durationMs: number;
}

export interface WanderOptions {
  marginPct?: number;
  runDistanceThresholdPct?: number;
  walkSpeedPxPerSec?: number;
  runSpeedPxPerSec?: number;
  avoidArea?: AvoidArea;
}

/**
 * Pick a random destination on screen and determine locomotion speed (walk vs run).
 * Pure function with injected `random` for deterministic testing.
 */
export function pickWanderTarget(
  currentPos: ScreenPoint,
  bounds: ScreenBounds,
  random: () => number = Math.random,
  options?: WanderOptions
): WanderTarget {
  const marginPct = options?.marginPct ?? 0.08;
  const runThresholdPct = options?.runDistanceThresholdPct ?? 0.35;
  const walkSpeed = options?.walkSpeedPxPerSec ?? 140;
  const runSpeed = options?.runSpeedPxPerSec ?? 320;

  const minX = Math.round(bounds.width * marginPct);
  const maxX = Math.round(bounds.width * (1 - marginPct));
  const minY = Math.round(bounds.height * marginPct);
  const maxY = Math.round(bounds.height * (1 - marginPct));

  let targetX = Math.round(minX + random() * (maxX - minX));
  let targetY = Math.round(minY + random() * (maxY - minY));

  // If avoidArea is specified (e.g. fullscreen window in focus), shift target out of that area
  if (options?.avoidArea) {
    const area = options.avoidArea;
    const inside =
      targetX >= area.x &&
      targetX <= area.x + area.width &&
      targetY >= area.y &&
      targetY <= area.y + area.height;

    if (inside) {
      if (random() < 0.5) {
        targetX = random() < 0.5 ? Math.max(minX, area.x - 80) : Math.min(maxX, area.x + area.width + 80);
      } else {
        targetY = Math.min(maxY, area.y + area.height + 60);
      }
    }
  }

  const target: ScreenPoint = { x: targetX, y: targetY };
  const distance = calculateScreenDistance(currentPos, target);
  const runThresholdPx = bounds.width * runThresholdPct;

  const speed: 'walk' | 'run' = distance > runThresholdPx ? 'run' : 'walk';
  const speedPxPerSec = speed === 'run' ? runSpeed : walkSpeed;
  const durationMs = Math.round((distance / speedPxPerSec) * 1000);

  return {
    target,
    speed,
    durationMs: Math.max(1000, durationMs),
  };
}
