export interface IdleVariationConfig {
  enabled: boolean;
  delayMin: number;
  delayMax: number;
  animations: string[];
}

export const DEFAULT_IDLE_VARIATION: IdleVariationConfig = {
  enabled: true,
  delayMin: 10000,
  delayMax: 20000,
  animations: [],
};

/**
 * animations.json の config.idleVariation を読み取る（欠損はデフォルトで補う）
 */
export function parseIdleVariationConfig(raw: unknown): IdleVariationConfig {
  if (typeof raw !== 'object' || raw === null) {
    return { ...DEFAULT_IDLE_VARIATION };
  }
  const c = raw as Partial<IdleVariationConfig>;
  return {
    enabled: c.enabled ?? DEFAULT_IDLE_VARIATION.enabled,
    delayMin: c.delayMin ?? DEFAULT_IDLE_VARIATION.delayMin,
    delayMax: c.delayMax ?? DEFAULT_IDLE_VARIATION.delayMax,
    animations: c.animations ?? [],
  };
}

/**
 * 次のアイドルバリエーションまでの待機時間（ミリ秒）
 */
export function pickIdleDelay(config: IdleVariationConfig, rand: number): number {
  return config.delayMin + rand * (config.delayMax - config.delayMin);
}

/**
 * 再生するアイドルバリエーションを選ぶ
 */
export function pickIdleAnimation(animations: string[], rand: number): string | null {
  if (animations.length === 0) return null;
  return animations[Math.floor(rand * animations.length)];
}
