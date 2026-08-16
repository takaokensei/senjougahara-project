import { VRM } from '@pixiv/three-vrm';
import {
  vowelToTargets,
  stepVowelValues,
  emotionValues,
  VOWEL_KEYS,
  LERP_FACTOR,
} from './logic/expression.js';
import type { EmotionType, VowelType, VowelValues } from './logic/expression.js';

/**
 * 感情表情・リップシンクの管理
 */
export class ExpressionController {
  private targetVowelValues: VowelValues = vowelToTargets(null);
  private currentVowelValues: VowelValues = vowelToTargets(null);

  constructor(private vrm: VRM) {}

  /**
   * 感情表情を設定（他の感情はリセット）
   */
  setEmotion(emotion: EmotionType): void {
    const em = this.vrm.expressionManager;
    if (!em) return;

    for (const [expr, value] of emotionValues(emotion)) {
      em.setValue(expr, value);
    }
  }

  /**
   * リップシンク用の目標母音を設定（実際の補間は update() で行う）
   */
  setVowel(vowel: VowelType | null): void {
    this.targetVowelValues = vowelToTargets(vowel);
  }

  /**
   * フレームごとのLerp補間処理（レンダリングループから呼び出す）
   */
  update(): void {
    const em = this.vrm.expressionManager;
    if (!em) return;

    this.currentVowelValues = stepVowelValues(this.currentVowelValues, this.targetVowelValues, LERP_FACTOR);

    for (const key of VOWEL_KEYS) {
      em.setValue(key, this.currentVowelValues[key]);
    }
  }
}
