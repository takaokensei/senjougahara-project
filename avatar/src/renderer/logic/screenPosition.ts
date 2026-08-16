/**
 * avatar/src/renderer/logic/screenPosition.ts
 *
 * Pure functions for mapping between 2D screen pixel coordinates and 3D world space
 * coordinates for placing and moving the VRM character across the screen.
 */

export interface ScreenPoint {
  x: number;
  y: number;
}

export interface ScreenBounds {
  width: number;
  height: number;
}

export interface WorldPosition {
  x: number;
  y: number;
  z: number;
}

export interface CameraParameters {
  fov: number; // in degrees, e.g. 45
  distance: number; // distance from camera to character plane, e.g. 1.5
  targetY?: number; // baseline camera lookAt Y, e.g. 1.0
}

/**
 * Converts 2D pixel coordinates to 3D world coordinates at the character's depth plane.
 */
export function screenToWorld(
  screenPoint: ScreenPoint,
  bounds: ScreenBounds,
  camera: CameraParameters
): WorldPosition {
  const { width, height } = bounds;
  if (width <= 0 || height <= 0) {
    return { x: 0, y: 0, z: 0 };
  }

  const fovRad = (camera.fov * Math.PI) / 180;
  const planeHeight = 2 * camera.distance * Math.tan(fovRad / 2);
  const planeWidth = planeHeight * (width / height);

  // NDC: u in [-1, 1] (left to right), v in [-1, 1] (bottom to top)
  const u = (screenPoint.x / width) * 2 - 1;
  const v = 1 - (screenPoint.y / height) * 2;

  // In Three.js camera viewed from negative Z, X is inverted
  const worldX = -u * (planeWidth / 2);
  const worldY = v * (planeHeight / 2);

  return {
    x: Number(worldX.toFixed(4)),
    y: Number(worldY.toFixed(4)),
    z: 0,
  };
}

/**
 * Linearly interpolate between two screen points.
 */
export function interpolateScreenPoint(from: ScreenPoint, to: ScreenPoint, progress: number): ScreenPoint {
  const t = Math.max(0, Math.min(1, progress));
  return {
    x: Math.round(from.x + (to.x - from.x) * t),
    y: Math.round(from.y + (to.y - from.y) * t),
  };
}

/**
 * Compute Euclidean distance between two screen points in pixels.
 */
export function calculateScreenDistance(from: ScreenPoint, to: ScreenPoint): number {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  return Math.sqrt(dx * dx + dy * dy);
}

/**
 * Compute orientation angle (Y rotation in radians) so the VRM faces the direction of travel.
 */
export function calculateFacingAngle(from: ScreenPoint, to: ScreenPoint): number {
  const dx = to.x - from.x;
  if (Math.abs(dx) < 5) return 0;
  return dx > 0 ? Math.PI / 2 : -Math.PI / 2;
}
