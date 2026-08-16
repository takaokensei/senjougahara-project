import { writeFileSync, unlinkSync, existsSync } from 'fs';
import { join } from 'path';
import { tmpdir } from 'os';
import { AudioQuery, TtsConfig } from '../types/index.js';
import {
  createNetworkError,
  createApiError,
  createTimeoutError,
  createPlaybackError,
  wrapError,
  TtsError,
} from '../utils/errors.js';
import { VRMControlService } from './VRMControlService.js';
import { calculateAudioDuration, extractLipSyncTimings } from '../utils/audio.js';
import type { LipSyncTiming } from '../utils/audio.js';
import { createDefaultAudioPlayer, getPlaybackStartOffset } from '../utils/audioPlayer.js';
import type { AudioPlayer } from '../utils/audioPlayer.js';

/**
 * TTS（音声合成）サービス
 * VOICEVOX互換API（AivisSpeech / VOICEVOX / COEIROINK 等）を使用して音声を合成・再生する
 */
export class TtsService {
  private readonly config: Required<TtsConfig>;
  private isProcessing = false; // 二重実行防止フラグ
  private vrmControl?: VRMControlService;
  private readonly audioPlayer: AudioPlayer;

  constructor(config: TtsConfig, vrmControl?: VRMControlService, audioPlayer?: AudioPlayer) {
    this.config = {
      baseUrl: config.baseUrl,
      speakerId: config.speakerId,
      timeout: config.timeout ?? 30000, // デフォルト30秒
      maxRetries: config.maxRetries ?? 3, // デフォルト3回
      retryDelay: config.retryDelay ?? 1000, // デフォルト1秒
      playbackStartOffsetMs: config.playbackStartOffsetMs ?? getPlaybackStartOffset(process.platform),
    };
    this.vrmControl = vrmControl;
    this.audioPlayer = audioPlayer ?? createDefaultAudioPlayer();
  }

  /**
   * テキストを音声で再生（公開API）
   */
  public async speak(text: string): Promise<void> {
    if (this.isProcessing) {
      throw new Error('Already speaking. Please wait for the current playback to finish.');
    }

    this.isProcessing = true;
    try {
      console.error(`[desktop-mascot-mcp] Speaking: ${text.substring(0, 50)}${text.length > 50 ? '...' : ''}`);
      await this.speakWithRetry(text);
    } finally {
      this.isProcessing = false;
    }
  }

  /**
   * リトライ機能付き音声再生
   */
  private async speakWithRetry(text: string): Promise<void> {
    let lastError: TtsError | null = null;

    for (let attempt = 1; attempt <= this.config.maxRetries; attempt++) {
      try {
        await this.speakInternal(text);
        return; // 成功したら終了
      } catch (error) {
        lastError = wrapError(error);

        // 再試行不可能なエラーの場合は即座に終了
        if (!lastError.canRetry()) {
          throw lastError;
        }

        // 最後の試行でない場合は待機してリトライ
        if (attempt < this.config.maxRetries) {
          const delay = this.config.retryDelay * attempt; // 指数バックオフ
          console.error(`[TtsService] ${lastError.toString()} - retrying in ${delay}ms (${attempt}/${this.config.maxRetries})`);
          await this.sleep(delay);
        }
      }
    }

    // すべての試行が失敗した場合
    throw lastError!;
  }

  /**
   * 音声再生の内部実装
   */
  private async speakInternal(text: string): Promise<void> {
    // Step 1: 音声クエリを作成
    const query = await this.createAudioQuery(text);

    // Step 2: 音声を合成
    const audioBuffer = await this.synthesizeAudio(query);

    // Step 3: 音声の長さを計算（WAVヘッダーから）
    const audioDuration = calculateAudioDuration(audioBuffer, query);

    // Step 4: リップシンクタイミングを抽出（音声の長さを使用）
    const lipSyncTimings = extractLipSyncTimings(query, audioDuration);

    // Step 5: 音声を再生（リップシンク付き）
    await this.playAudioWithLipSync(audioBuffer, lipSyncTimings);
  }

  /**
   * 音声クエリを作成
   */
  private async createAudioQuery(text: string): Promise<AudioQuery> {
    const url = `${this.config.baseUrl}/audio_query?text=${encodeURIComponent(text)}&speaker=${this.config.speakerId}`;

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), this.config.timeout);

      const response = await fetch(url, {
        method: 'POST',
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw createApiError(response.status, `Failed to create audio query`);
      }

      return await response.json() as AudioQuery;
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        throw createTimeoutError(this.config.timeout);
      }
      if (error instanceof TtsError) {
        throw error;
      }
      throw createNetworkError('Error during audio query creation', error);
    }
  }

  /**
   * 音声を合成
   */
  private async synthesizeAudio(query: AudioQuery): Promise<Buffer> {
    const url = `${this.config.baseUrl}/synthesis?speaker=${this.config.speakerId}`;

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), this.config.timeout);

      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(query),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw createApiError(response.status, `Failed to synthesize audio`);
      }

      const arrayBuffer = await response.arrayBuffer();
      return Buffer.from(arrayBuffer);
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        throw createTimeoutError(this.config.timeout);
      }
      if (error instanceof TtsError) {
        throw error;
      }
      throw createNetworkError('Error during audio synthesis', error);
    }
  }

  /**
   * 音声を再生（リップシンク付き）
   */
  private async playAudioWithLipSync(audioBuffer: Buffer, lipSyncTimings: LipSyncTiming[]): Promise<void> {
    const tempFile = join(tmpdir(), 'desktop-mascot_temp_audio.wav');

    try {
      // 一時ファイルに保存
      writeFileSync(tempFile, audioBuffer);

      // 音声再生を開始（非同期）
      const playbackPromise = this.audioPlayer(tempFile).catch(error => {
        const errorMsg = error instanceof Error ? error.message : String(error);
        const detail = `file: ${tempFile}, detail: ${errorMsg}`;
        throw createPlaybackError(detail, error);
      });

      // リップシンク処理を開始
      const lipSyncPromise = this.performLipSync(lipSyncTimings);

      // 両方の完了を待機
      await Promise.all([playbackPromise, lipSyncPromise]);
    } finally {
      // 一時ファイルを削除
      if (existsSync(tempFile)) {
        try {
          unlinkSync(tempFile);
        } catch {
          // 削除失敗は無視
        }
      }
    }
  }

  /**
   * リップシンク処理を実行
   */
  private async performLipSync(timings: LipSyncTiming[]): Promise<void> {
    if (!this.vrmControl || timings.length === 0) {
      return;
    }

    // 音声再生開始までの遅延を考慮（コマンド起動時間はOSにより異なる）
    const PLAYBACK_START_OFFSET_MS = this.config.playbackStartOffsetMs;

    // 各母音のタイミングでsetVowelを呼び出すPromiseの配列を作成
    const lipSyncPromises = timings.map(timing => {
      return new Promise<void>(resolve => {
        const delayMs = (timing.startTime * 1000) + PLAYBACK_START_OFFSET_MS;
        setTimeout(async () => {
          try {
            await this.vrmControl!.setVowel(timing.vowel);
          } catch (error) {
            console.error(`[LipSync] Failed to set vowel ${timing.vowel}:`, error);
          }
          resolve();
        }, delayMs);
      });
    });

    // すべてのリップシンクコマンドの送信完了を待機
    await Promise.all(lipSyncPromises);

    // 最後に口を閉じる（母音をnullに）
    try {
      await this.vrmControl.setVowel(null);
    } catch (error) {
      console.error('[LipSync] Failed to close mouth:', error);
    }
  }

  /**
   * 指定時間待機
   */
  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  /**
   * 現在処理中かどうかを取得
   */
  public get processing(): boolean {
    return this.isProcessing;
  }
}
