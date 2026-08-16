import { describe, it, expect } from 'vitest';
import { pickWanderTarget } from '../../../renderer/logic/wander.js';

describe('wander', () => {
  const bounds = { width: 1000, height: 800 };

  it('picks target within safe screen margins', () => {
    const current = { x: 500, y: 400 };
    // Injected pseudo-random generator returning 0.5
    const mockRandom = () => 0.5;

    const result = pickWanderTarget(current, bounds, mockRandom, { marginPct: 0.1 });
    // Min X = 100, Max X = 900 -> mid = 500
    // Min Y = 80, Max Y = 720 -> mid = 400
    expect(result.target.x).toBeGreaterThanOrEqual(100);
    expect(result.target.x).toBeLessThanOrEqual(900);
    expect(result.target.y).toBeGreaterThanOrEqual(80);
    expect(result.target.y).toBeLessThanOrEqual(720);
  });

  it('selects run speed for large distances across screen', () => {
    const current = { x: 100, y: 100 };
    // Random returns 1.0 (far right/bottom)
    const mockRandom = () => 1.0;

    const result = pickWanderTarget(current, bounds, mockRandom, {
      marginPct: 0.05,
      runDistanceThresholdPct: 0.35,
    });

    // Distance ~ 900px > 350px threshold -> should run
    expect(result.speed).toBe('run');
    expect(result.durationMs).toBeGreaterThan(1000);
  });

  it('selects walk speed for short distances', () => {
    const current = { x: 500, y: 400 };
    // Random returns slightly offset point
    const mockRandom = () => 0.52;

    const result = pickWanderTarget(current, bounds, mockRandom, {
      marginPct: 0.1,
      runDistanceThresholdPct: 0.5,
    });

    expect(result.speed).toBe('walk');
  });

  it('respects avoidArea and pushes target outside', () => {
    const current = { x: 500, y: 400 };
    const fullscreenAvoid = { x: 200, y: 150, width: 600, height: 500 };
    const mockRandom = () => 0.5; // Would normally land right at (500, 400) inside avoidArea

    const result = pickWanderTarget(current, bounds, mockRandom, {
      marginPct: 0.05,
      avoidArea: fullscreenAvoid,
    });

    const isInsideAvoid =
      result.target.x >= fullscreenAvoid.x &&
      result.target.x <= fullscreenAvoid.x + fullscreenAvoid.width &&
      result.target.y >= fullscreenAvoid.y &&
      result.target.y <= fullscreenAvoid.y + fullscreenAvoid.height;

    expect(isInsideAvoid).toBe(false);
  });
});
