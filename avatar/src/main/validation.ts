export function validateVowel(v: unknown): v is 'a' | 'i' | 'u' | 'e' | 'o' | null {
  const validVowels: unknown[] = ['a', 'i', 'u', 'e', 'o', null];
  return validVowels.includes(v);
}

export function validateEmotion(v: unknown): v is 'neutral' | 'happy' | 'angry' | 'sad' | 'relaxed' | 'surprised' {
  const validEmotions = ['neutral', 'happy', 'angry', 'sad', 'relaxed', 'surprised'];
  return typeof v === 'string' && validEmotions.includes(v);
}

export function validateSpeakPayload(data: unknown): data is { text: string; emotion?: string } {
  if (typeof data !== 'object' || data === null) return false;
  const d = data as Record<string, unknown>;
  if (typeof d.text !== 'string') return false;
  if (d.emotion !== undefined && typeof d.emotion !== 'string') return false;
  return true;
}

export function validateAnimationPayload(data: unknown): data is { animation: string } {
  return typeof data === 'object' && data !== null && typeof (data as Record<string, unknown>).animation === 'string';
}
