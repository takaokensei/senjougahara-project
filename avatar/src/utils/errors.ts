import { ErrorType, TtsErrorData } from '../types/index.js';

/**
 * TTS専用エラークラス
 */
export class TtsError extends Error {
  public readonly type: ErrorType;
  public readonly retryable: boolean;
  public readonly originalError?: unknown;

  constructor(data: TtsErrorData) {
    super(data.message);
    this.name = 'TtsError';
    this.type = data.type;
    this.retryable = data.retryable;
    this.originalError = data.originalError;

    // スタックトレースを適切に設定
    Error.captureStackTrace(this, TtsError);
  }

  /**
   * エラーが再試行可能かどうかを判定
   */
  public canRetry(): boolean {
    return this.retryable;
  }

  /**
   * エラー情報を文字列化
   */
  public toString(): string {
    return `[${this.type}] ${this.message}${this.retryable ? ' (retryable)' : ''}`;
  }
}

/**
 * ネットワークエラーを作成
 */
export function createNetworkError(message: string, originalError?: unknown): TtsError {
  return new TtsError({
    type: ErrorType.NETWORK,
    message: `Network error: ${message}`,
    originalError,
    retryable: true,
  });
}

/**
 * APIエラーを作成
 */
export function createApiError(status: number, message: string): TtsError {
  const retryable = status >= 500 && status < 600; // 5xxエラーは再試行可能
  return new TtsError({
    type: ErrorType.API,
    message: `API error (${status}): ${message}`,
    retryable,
  });
}

/**
 * タイムアウトエラーを作成
 */
export function createTimeoutError(timeoutMs: number): TtsError {
  return new TtsError({
    type: ErrorType.TIMEOUT,
    message: `Timeout: no response within ${timeoutMs}ms`,
    retryable: true,
  });
}

/**
 * 再生エラーを作成
 */
export function createPlaybackError(message: string, originalError?: unknown): TtsError {
  return new TtsError({
    type: ErrorType.PLAYBACK,
    message: `Playback error: ${message}`,
    originalError,
    retryable: false,
  });
}

/**
 * 不明なエラーを作成
 */
export function createUnknownError(originalError: unknown): TtsError {
  const message = originalError instanceof Error ? originalError.message : String(originalError);
  return new TtsError({
    type: ErrorType.UNKNOWN,
    message: `Unknown error: ${message}`,
    originalError,
    retryable: false,
  });
}

/**
 * エラーから適切なTtsErrorを生成
 */
export function wrapError(error: unknown): TtsError {
  if (error instanceof TtsError) {
    return error;
  }

  if (error instanceof TypeError && error.message.includes('fetch')) {
    return createNetworkError('cannot connect to TTS API', error);
  }

  return createUnknownError(error);
}
