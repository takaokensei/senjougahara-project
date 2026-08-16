export type EmotionType = 'neutral' | 'happy' | 'angry' | 'sad' | 'relaxed' | 'surprised';
export type VowelType = 'a' | 'i' | 'u' | 'e' | 'o';
export type VowelValues = { aa: number; ih: number; ou: number; ee: number; oh: number };

export const VOWEL_KEYS = ['aa', 'ih', 'ou', 'ee', 'oh'] as const;

const EMOTION_EXPRESSIONS: Exclude<EmotionType, 'neutral'>[] = [
  'happy', 'angry', 'sad', 'relaxed', 'surprised',
];

/** リップシンクの補間速度（0.1=遅い、0.5=速い） */
export const LERP_FACTOR = 0.2;

/**
 * 母音に対応するブレンドシェイプの目標値を返す
 */
export function vowelToTargets(vowel: VowelType | null): VowelValues {
  return {
    aa: vowel === 'a' ? 1.0 : 0,
    ih: vowel === 'i' ? 1.0 : 0,
    ou: vowel === 'u' ? 1.0 : 0,
    ee: vowel === 'e' ? 1.0 : 0,
    oh: vowel === 'o' ? 1.0 : 0,
  };
}

/**
 * 現在値を目標値へ 1 ステップぶん線形補間する（新しいオブジェクトを返す）
 */
export function stepVowelValues(current: VowelValues, target: VowelValues, factor: number): VowelValues {
  const next = {} as VowelValues;
  for (const key of VOWEL_KEYS) {
    next[key] = current[key] + (target[key] - current[key]) * factor;
  }
  return next;
}

/**
 * 感情ごとの表情値を返す（選択された感情だけ 1.0、他は 0）
 */
export function emotionValues(emotion: EmotionType): Array<[Exclude<EmotionType, 'neutral'>, number]> {
  return EMOTION_EXPRESSIONS.map((expr) => [expr, expr === emotion ? 1.0 : 0]);
}
