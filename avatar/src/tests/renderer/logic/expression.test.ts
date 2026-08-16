import { describe, it, expect } from 'vitest';
import {
  vowelToTargets,
  stepVowelValues,
  emotionValues,
  LERP_FACTOR,
} from '../../../renderer/logic/expression.js';

const ZERO = { aa: 0, ih: 0, ou: 0, ee: 0, oh: 0 };

describe('vowelToTargets', () => {
  it.each([
    ['a', 'aa'],
    ['i', 'ih'],
    ['u', 'ou'],
    ['e', 'ee'],
    ['o', 'oh'],
  ] as const)('母音 %s は %s だけを 1.0 にする', (vowel, key) => {
    expect(vowelToTargets(vowel)).toEqual({ ...ZERO, [key]: 1.0 });
  });

  it('null はすべて 0 にする', () => {
    expect(vowelToTargets(null)).toEqual(ZERO);
  });
});

describe('stepVowelValues', () => {
  it('factor 0 では現在値のまま', () => {
    const current = { ...ZERO, aa: 0.3 };
    expect(stepVowelValues(current, vowelToTargets('a'), 0)).toEqual(current);
  });

  it('factor 1 では目標値に一致する', () => {
    const target = vowelToTargets('i');
    expect(stepVowelValues(ZERO, target, 1)).toEqual(target);
  });

  it('factor 0.2 では 20% だけ近づく', () => {
    const result = stepVowelValues(ZERO, vowelToTargets('a'), 0.2);
    expect(result.aa).toBeCloseTo(0.2);
    expect(result.ih).toBe(0);
  });

  it('元のオブジェクトを書き換えない', () => {
    const current = { ...ZERO };
    stepVowelValues(current, vowelToTargets('a'), 0.5);
    expect(current).toEqual(ZERO);
  });

  it('繰り返し適用すると目標値へ収束する', () => {
    const target = vowelToTargets('o');
    let values = { ...ZERO };
    for (let i = 0; i < 100; i++) values = stepVowelValues(values, target, LERP_FACTOR);
    expect(values.oh).toBeCloseTo(1.0, 5);
  });
});

describe('emotionValues', () => {
  it('neutral はすべての感情を 0 にする', () => {
    expect(emotionValues('neutral')).toEqual([
      ['happy', 0], ['angry', 0], ['sad', 0], ['relaxed', 0], ['surprised', 0],
    ]);
  });

  it('happy は happy だけを 1.0 にする', () => {
    expect(emotionValues('happy')).toEqual([
      ['happy', 1.0], ['angry', 0], ['sad', 0], ['relaxed', 0], ['surprised', 0],
    ]);
  });

  it.each(['angry', 'sad', 'relaxed', 'surprised'] as const)('%s も同様に 1 つだけ 1.0', (emotion) => {
    const entries = emotionValues(emotion);
    expect(entries.filter(([, v]) => v === 1.0)).toEqual([[emotion, 1.0]]);
    expect(entries).toHaveLength(5);
  });
});
