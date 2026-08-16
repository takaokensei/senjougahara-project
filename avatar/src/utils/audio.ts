import type { AudioQuery } from '../types/index.js';

export interface LipSyncTiming {
  vowel: 'a' | 'i' | 'u' | 'e' | 'o';
  startTime: number;
}

export function calculateAudioDuration(audioBuffer: Buffer, query: AudioQuery): number {
  const headerSize = 44;
  const dataSize = Math.max(0, audioBuffer.length - headerSize);
  const sampleRate = query.outputSamplingRate;
  const channels = query.outputStereo ? 2 : 1;
  const bytesPerSample = 2;
  return dataSize / (sampleRate * channels * bytesPerSample);
}

/**
 * AudioQueryから母音タイミング情報を抽出
 * 注: AivisSpeechではvowel_length/consonant_lengthが常に0なため、
 * 音声の総長さとモーラ数から均等分割で推定します
 */
export function extractLipSyncTimings(query: AudioQuery, audioDurationSeconds: number): LipSyncTiming[] {
  const timings: LipSyncTiming[] = [];
  const allMoras: { vowel: string }[] = [];

  for (const phrase of query.accent_phrases) {
    for (const mora of phrase.moras) {
      if (mora.vowel && mora.vowel.length > 0) {
        allMoras.push({ vowel: mora.vowel });
      }
    }
  }

  const moraCount = allMoras.length;
  if (moraCount === 0) return timings;

  const moraInterval = audioDurationSeconds / moraCount;

  for (let i = 0; i < allMoras.length; i++) {
    const vowel = allMoras[i].vowel.toLowerCase();
    if (vowel === 'a' || vowel === 'i' || vowel === 'u' || vowel === 'e' || vowel === 'o') {
      timings.push({ vowel: vowel as 'a' | 'i' | 'u' | 'e' | 'o', startTime: i * moraInterval });
    }
  }

  return timings;
}
