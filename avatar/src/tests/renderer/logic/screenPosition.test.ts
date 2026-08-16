import { describe, it, expect } from 'vitest';
import {
  screenToWorld,
  interpolateScreenPoint,
  calculateScreenDistance,
  calculateFacingAngle,
} from '../../../renderer/logic/screenPosition.js';

describe('screenPosition', () => {
  const bounds = { width: 1920, height: 1080 };
  const camera = { fov: 45, distance: 1.5, targetY: 1.0 };

  it('center of screen maps to (0, 0, 0) world coordinates', () => {
    const centerPoint = { x: 960, y: 540 };
    const world = screenToWorld(centerPoint, bounds, camera);
    expect(world.x).toBeCloseTo(0, 2);
    expect(world.y).toBeCloseTo(0, 2);
    expect(world.z).toBe(0);
  });

  it('screen corners map to symmetrical world coordinates', () => {
    const leftPoint = { x: 0, y: 540 };
    const rightPoint = { x: 1920, y: 540 };

    const worldLeft = screenToWorld(leftPoint, bounds, camera);
    const worldRight = screenToWorld(rightPoint, bounds, camera);

    expect(worldLeft.x).toBeGreaterThan(0);
    expect(worldRight.x).toBeLessThan(0);
    expect(Math.abs(worldLeft.x)).toBeCloseTo(Math.abs(worldRight.x), 2);
  });

  it('interpolateScreenPoint handles start, mid, and end progress correctly', () => {
    const p1 = { x: 100, y: 200 };
    const p2 = { x: 300, y: 600 };

    expect(interpolateScreenPoint(p1, p2, 0)).toEqual({ x: 100, y: 200 });
    expect(interpolateScreenPoint(p1, p2, 0.5)).toEqual({ x: 200, y: 400 });
    expect(interpolateScreenPoint(p1, p2, 1)).toEqual({ x: 300, y: 600 });
    expect(interpolateScreenPoint(p1, p2, 1.5)).toEqual({ x: 300, y: 600 }); // Clamped
  });

  it('calculateScreenDistance calculates Euclidean distance accurately', () => {
    const p1 = { x: 0, y: 0 };
    const p2 = { x: 300, y: 400 };
    expect(calculateScreenDistance(p1, p2)).toBe(500);
  });

  it('calculateFacingAngle gives correct directional yaw angles', () => {
    const p1 = { x: 500, y: 500 };
    const pRight = { x: 800, y: 500 };
    const pLeft = { x: 200, y: 500 };
    const pStationary = { x: 502, y: 500 };

    expect(calculateFacingAngle(p1, pRight)).toBeCloseTo(Math.PI / 2, 2);
    expect(calculateFacingAngle(p1, pLeft)).toBeCloseTo(-Math.PI / 2, 2);
    expect(calculateFacingAngle(p1, pStationary)).toBe(0);
  });
});
