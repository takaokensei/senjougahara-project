/**
 * TTS (Text-to-Speech) API型定義
 */

/**
 * 音声合成クエリのレスポンス型
 */
export interface AudioQuery {
  accent_phrases: AccentPhrase[];
  speedScale: number;
  pitchScale: number;
  intonationScale: number;
  volumeScale: number;
  prePhonemeLength: number;
  postPhonemeLength: number;
  outputSamplingRate: number;
  outputStereo: boolean;
  kana?: string;
}

/**
 * アクセント句の型
 */
export interface AccentPhrase {
  moras: Mora[];
  accent: number;
  pause_mora?: Mora;
  is_interrogative?: boolean;
}

/**
 * モーラ（音素の単位）の型
 */
export interface Mora {
  text: string;
  consonant?: string;
  consonant_length?: number;
  vowel: string;
  vowel_length: number;
  pitch: number;
}

/**
 * TTS設定
 */
export interface TtsConfig {
  /** TTS APIのベースURL */
  baseUrl: string;
  /** 話者ID (例: 1431611904 = Anneli) */
  speakerId: number;
  /** タイムアウト時間（ミリ秒） */
  timeout?: number;
  /** リトライ回数 */
  maxRetries?: number;
  /** リトライ間隔（ミリ秒） */
  retryDelay?: number;
  /** リップシンク開始オフセット（ミリ秒）。省略時は OS から決定 */
  playbackStartOffsetMs?: number;
}

/**
 * エラーの種類
 */
export enum ErrorType {
  /** ネットワークエラー（TTSエンジンに到達できない） */
  NETWORK = 'NETWORK',
  /** APIエラー（TTSエンジンがエラーを返した） */
  API = 'API',
  /** タイムアウト */
  TIMEOUT = 'TIMEOUT',
  /** 再生エラー */
  PLAYBACK = 'PLAYBACK',
  /** その他のエラー */
  UNKNOWN = 'UNKNOWN',
}

/**
 * カスタムエラーの基底型
 */
export interface TtsErrorData {
  type: ErrorType;
  message: string;
  originalError?: unknown;
  retryable: boolean;
}
