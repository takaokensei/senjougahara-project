import { describe, it, expect } from 'vitest';
import {
  parseIdleVariationConfig,
  pickIdleDelay,
  pickIdleAnimation,
  DEFAULT_IDLE_VARIATION,
} from '../../../renderer/logic/idleVariation.js';

describe('parseIdleVariationConfig', () => {
  it('完全な設定をそのまま読み取る', () => {
    expect(parseIdleVariationConfig({
      enabled: false, delayMin: 1000, delayMax: 2000, animations: ['look', 'stretch'],
    })).toEqual({ enabled: false, delayMin: 1000, delayMax: 2000, animations: ['look', 'stretch'] });
  });

  it('undefined ではデフォルト値を返す', () => {
    expect(parseIdleVariationConfig(undefined)).toEqual(DEFAULT_IDLE_VARIATION);
  });

  it('null ではデフォルト値を返す', () => {
    expect(parseIdleVariationConfig(null)).toEqual(DEFAULT_IDLE_VARIATION);
  });

  it('オブジェクト以外ではデフォルト値を返す', () => {
    expect(parseIdleVariationConfig('idle')).toEqual(DEFAULT_IDLE_VARIATION);
  });

  it('デフォルト値は enabled=true / 10000-20000ms / 空配列', () => {
    expect(DEFAULT_IDLE_VARIATION).toEqual({
      enabled: true, delayMin: 10000, delayMax: 20000, animations: [],
    });
  });

  it.each([
    ['enabled', { delayMin: 1, delayMax: 2, animations: [] }, 'enabled', true],
    ['delayMin', { enabled: true, delayMax: 2, animations: [] }, 'delayMin', 10000],
    ['delayMax', { enabled: true, delayMin: 1, animations: [] }, 'delayMax', 20000],
  ] as const)('%s が欠けていればデフォルトを補う', (_label, raw, key, expected) => {
    expect(parseIdleVariationConfig(raw)[key]).toBe(expected);
  });

  it('animations が欠けていれば空配列にする', () => {
    expect(parseIdleVariationConfig({ enabled: true }).animations).toEqual([]);
  });

  it('enabled が false のときは false のまま（?? でデフォルトに戻さない）', () => {
    expect(parseIdleVariationConfig({ enabled: false }).enabled).toBe(false);
  });
});

describe('pickIdleDelay', () => {
  const config = { enabled: true, delayMin: 1000, delayMax: 3000, animations: [] };

  it('rand=0 では delayMin', () => {
    expect(pickIdleDelay(config, 0)).toBe(1000);
  });

  it('rand=1 では delayMax', () => {
    expect(pickIdleDelay(config, 1)).toBe(3000);
  });

  it('rand=0.5 では中間値', () => {
    expect(pickIdleDelay(config, 0.5)).toBe(2000);
  });
});

describe('pickIdleAnimation', () => {
  it('空配列では null', () => {
    expect(pickIdleAnimation([], 0.5)).toBeNull();
  });

  it('rand から添字を決める', () => {
    expect(pickIdleAnimation(['a', 'b', 'c'], 0)).toBe('a');
    expect(pickIdleAnimation(['a', 'b', 'c'], 0.5)).toBe('b');
    expect(pickIdleAnimation(['a', 'b', 'c'], 0.99)).toBe('c');
  });
});
