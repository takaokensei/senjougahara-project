import { describe, it, expect, vi } from 'vitest';
import { ExpressionController } from '../../renderer/ExpressionController.js';
import type { VRM } from '@pixiv/three-vrm';

function makeVrm(withManager = true) {
  const setValue = vi.fn();
  const vrm = { expressionManager: withManager ? { setValue } : undefined } as unknown as VRM;
  return { vrm, setValue };
}

describe('ExpressionController.setEmotion', () => {
  it('選択した感情を 1.0、他を 0 にする', () => {
    const { vrm, setValue } = makeVrm();
    new ExpressionController(vrm).setEmotion('happy');
    expect(setValue.mock.calls).toEqual([
      ['happy', 1.0], ['angry', 0], ['sad', 0], ['relaxed', 0], ['surprised', 0],
    ]);
  });

  it('neutral はすべてを 0 にする', () => {
    const { vrm, setValue } = makeVrm();
    new ExpressionController(vrm).setEmotion('neutral');
    expect(setValue.mock.calls.every(([, v]) => v === 0)).toBe(true);
  });

  it('expressionManager が無ければ何もしない', () => {
    const { vrm, setValue } = makeVrm(false);
    expect(() => new ExpressionController(vrm).setEmotion('happy')).not.toThrow();
    expect(setValue).not.toHaveBeenCalled();
  });
});

describe('ExpressionController.update', () => {
  it('setVowel した母音へ徐々に近づく', () => {
    const { vrm, setValue } = makeVrm();
    const controller = new ExpressionController(vrm);
    controller.setVowel('a');

    controller.update();
    const firstAa = setValue.mock.calls.find(([k]) => k === 'aa')![1];
    expect(firstAa).toBeCloseTo(0.2);

    setValue.mockClear();
    controller.update();
    const secondAa = setValue.mock.calls.find(([k]) => k === 'aa')![1];
    expect(secondAa).toBeGreaterThan(firstAa);
  });

  it('5 つの母音ブレンドシェイプすべてに値を書き込む', () => {
    const { vrm, setValue } = makeVrm();
    new ExpressionController(vrm).update();
    expect(setValue.mock.calls.map(([k]) => k)).toEqual(['aa', 'ih', 'ou', 'ee', 'oh']);
  });

  it('setVowel(null) で 0 に戻っていく', () => {
    const { vrm, setValue } = makeVrm();
    const controller = new ExpressionController(vrm);
    controller.setVowel('a');
    for (let i = 0; i < 100; i++) controller.update();

    controller.setVowel(null);
    setValue.mockClear();
    for (let i = 0; i < 100; i++) controller.update();
    expect(setValue.mock.calls.at(-5)![1]).toBeCloseTo(0, 5);
  });

  it('expressionManager が無ければ何もしない', () => {
    const { vrm, setValue } = makeVrm(false);
    expect(() => new ExpressionController(vrm).update()).not.toThrow();
    expect(setValue).not.toHaveBeenCalled();
  });
});
