import { describe, it, expect } from 'vitest';
import {
  validateVowel,
  validateEmotion,
  validateSpeakPayload,
  validateAnimationPayload,
} from '../../main/validation.js';

describe('validateVowel', () => {
  it.each(['a', 'i', 'u', 'e', 'o', null])('有効値 %s を受け入れる', (v) => {
    expect(validateVowel(v)).toBe(true);
  });

  it.each(['x', undefined, 123, ''])('無効値 %s を拒否する', (v) => {
    expect(validateVowel(v)).toBe(false);
  });
});

describe('validateEmotion', () => {
  it.each(['neutral', 'happy', 'angry', 'sad', 'relaxed', 'surprised'])('有効値 %s を受け入れる', (v) => {
    expect(validateEmotion(v)).toBe(true);
  });

  it.each(['fear', null, 123, ''])('無効値 %s を拒否する', (v) => {
    expect(validateEmotion(v)).toBe(false);
  });
});

describe('validateSpeakPayload', () => {
  it('{ text: string } を受け入れる', () => {
    expect(validateSpeakPayload({ text: 'hello' })).toBe(true);
  });

  it('{ text: string, emotion: string } を受け入れる', () => {
    expect(validateSpeakPayload({ text: 'hi', emotion: 'happy' })).toBe(true);
  });

  it('{ text: number } を拒否する', () => {
    expect(validateSpeakPayload({ text: 123 })).toBe(false);
  });

  it('{ text: string, emotion: number } を拒否する', () => {
    expect(validateSpeakPayload({ text: 'hi', emotion: 123 })).toBe(false);
  });

  it('空オブジェクト {} を拒否する', () => {
    expect(validateSpeakPayload({})).toBe(false);
  });

  it('null を拒否する', () => {
    expect(validateSpeakPayload(null)).toBe(false);
  });

  it('オブジェクト以外（文字列）を拒否する', () => {
    expect(validateSpeakPayload('hello')).toBe(false);
  });

  it('配列は text を持たないので拒否する', () => {
    expect(validateSpeakPayload([])).toBe(false);
  });
});

describe('validateAnimationPayload', () => {
  it('{ animation: string } を受け入れる', () => {
    expect(validateAnimationPayload({ animation: 'idle' })).toBe(true);
  });

  it('{ animation: null } を拒否する', () => {
    expect(validateAnimationPayload({ animation: null })).toBe(false);
  });

  it('空オブジェクト {} を拒否する', () => {
    expect(validateAnimationPayload({})).toBe(false);
  });

  it('{ animation: number } を拒否する', () => {
    expect(validateAnimationPayload({ animation: 5 })).toBe(false);
  });

  it('オブジェクト以外（文字列）を拒否する', () => {
    expect(validateAnimationPayload('idle')).toBe(false);
  });

  it('null を拒否する', () => {
    expect(validateAnimationPayload(null)).toBe(false);
  });
});
