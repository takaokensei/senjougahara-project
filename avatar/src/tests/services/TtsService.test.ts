import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('fs', () => ({
  writeFileSync: vi.fn(),
  unlinkSync: vi.fn(),
  existsSync: vi.fn().mockReturnValue(true),
}));

import { writeFileSync, unlinkSync, existsSync } from 'fs';
import { TtsService } from '../../services/TtsService.js';
import { ErrorType } from '../../types/index.js';
import type { AudioQuery, TtsConfig } from '../../types/index.js';
import type { VRMControlService } from '../../services/VRMControlService.js';

const BASE_CONFIG: TtsConfig = {
  baseUrl: 'http://localhost:10101',
  speakerId: 42,
  timeout: 1000,
  maxRetries: 3,
  retryDelay: 100,
  playbackStartOffsetMs: 0,
};

function makeQuery(vowels: string[] = ['a']): AudioQuery {
  return {
    accent_phrases: [{
      moras: vowels.map((vowel) => ({ text: 'x', vowel, vowel_length: 0, pitch: 0 })),
      accent: 1,
    }],
    speedScale: 1, pitchScale: 0, intonationScale: 1, volumeScale: 1,
    prePhonemeLength: 0.1, postPhonemeLength: 0.1,
    outputSamplingRate: 24000, outputStereo: false,
  };
}

/** 1 秒ぶんの WAV バッファ（24kHz モノラル 16bit） */
function makeAudioBuffer(seconds = 1): ArrayBuffer {
  return new ArrayBuffer(44 + 24000 * 2 * seconds);
}

/** audio_query → synthesis の順に応答する fetch モックを作る */
function stubHappyFetch(query: AudioQuery = makeQuery()) {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce({ ok: true, status: 200, json: async () => query })
    .mockResolvedValueOnce({ ok: true, status: 200, arrayBuffer: async () => makeAudioBuffer() });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

beforeEach(() => {
  vi.mocked(existsSync).mockReturnValue(true);
  vi.mocked(writeFileSync).mockReset();
  vi.mocked(unlinkSync).mockReset();
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('TtsService - リクエスト構築', () => {
  it('audio_query にテキストと話者 ID を URL エンコードして渡す', async () => {
    const fetchMock = stubHappyFetch();
    await new TtsService(BASE_CONFIG, undefined, vi.fn().mockResolvedValue(undefined)).speak('こんにちは');
    expect(fetchMock.mock.calls[0][0]).toBe(
      'http://localhost:10101/audio_query?text=%E3%81%93%E3%82%93%E3%81%AB%E3%81%A1%E3%81%AF&speaker=42'
    );
    expect(fetchMock.mock.calls[0][1].method).toBe('POST');
  });

  it('synthesis に audio_query の結果を JSON で渡す', async () => {
    const query = makeQuery(['a', 'i']);
    const fetchMock = stubHappyFetch(query);
    await new TtsService(BASE_CONFIG, undefined, vi.fn().mockResolvedValue(undefined)).speak('あい');
    expect(fetchMock.mock.calls[1][0]).toBe('http://localhost:10101/synthesis?speaker=42');
    expect(fetchMock.mock.calls[1][1].headers).toEqual({ 'Content-Type': 'application/json' });
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual(query);
  });

  it('50文字を超えるテキストは省略記号付きでログに出す', async () => {
    stubHappyFetch();
    const longText = 'あ'.repeat(60);
    await new TtsService(BASE_CONFIG, undefined, vi.fn().mockResolvedValue(undefined)).speak(longText);
    expect(console.error).toHaveBeenCalledWith(expect.stringContaining('...'));
  });

  it('audioPlayer 未指定時は既定の AudioPlayer が生成される（例外なく構築できる）', () => {
    expect(() => new TtsService(BASE_CONFIG)).not.toThrow();
  });
});

describe('TtsService - デフォルト設定', () => {
  it('maxRetries 未指定時は 3 回、retryDelay 未指定時は 1000ms 間隔（指数バックオフ）でリトライする', async () => {
    vi.useFakeTimers();
    try {
      const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 503 });
      vi.stubGlobal('fetch', fetchMock);
      const service = new TtsService(
        { baseUrl: 'http://localhost:10101', speakerId: 1 },
        undefined,
        vi.fn().mockResolvedValue(undefined)
      );

      const promise = service.speak('やあ');
      const assertion = expect(promise).rejects.toMatchObject({ type: ErrorType.API });

      await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
      await vi.advanceTimersByTimeAsync(1000); // retryDelay(1000) * 1 回目の待機
      await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
      await vi.advanceTimersByTimeAsync(2000); // retryDelay(1000) * 2 回目の待機
      await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));

      await assertion;
      // maxRetries(3) で打ち切られ、4 回目の呼び出しは発生しない
      expect(fetchMock).toHaveBeenCalledTimes(3);
    } finally {
      vi.useRealTimers();
    }
  });

  it('timeout 未指定時は 30000ms で AbortSignal が発火する', async () => {
    vi.useFakeTimers();
    try {
      let capturedSignal: AbortSignal | undefined;
      const fetchMock = vi.fn((_url: string, init: RequestInit) => {
        capturedSignal = init.signal as AbortSignal;
        return new Promise((_resolve, reject) => {
          init.signal!.addEventListener('abort', () => {
            const err = new Error('aborted');
            err.name = 'AbortError';
            reject(err);
          });
        });
      });
      vi.stubGlobal('fetch', fetchMock);
      // maxRetries は 1 に固定し、リトライ既定値（別テストで検証済み）と混ざらないよう timeout の既定値だけを検証する
      const service = new TtsService(
        { baseUrl: 'http://localhost:10101', speakerId: 1, maxRetries: 1 },
        undefined,
        vi.fn().mockResolvedValue(undefined)
      );

      const promise = service.speak('やあ');
      const assertion = expect(promise).rejects.toMatchObject({ type: ErrorType.TIMEOUT });

      expect(capturedSignal!.aborted).toBe(false);
      await vi.advanceTimersByTimeAsync(29999);
      expect(capturedSignal!.aborted).toBe(false);

      await vi.advanceTimersByTimeAsync(1);
      expect(capturedSignal!.aborted).toBe(true);

      await assertion;
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('TtsService - 二重実行防止', () => {
  it('処理中は processing が true になり、再入すると例外を投げる', async () => {
    let releasePlayback: () => void = () => {};
    const player = vi.fn(() => new Promise<void>((resolve) => { releasePlayback = resolve; }));
    stubHappyFetch();
    const service = new TtsService(BASE_CONFIG, undefined, player);

    const first = service.speak('やあ');
    await vi.waitFor(() => expect(service.processing).toBe(true));
    await expect(service.speak('もう一回')).rejects.toThrow(
      'Already speaking. Please wait for the current playback to finish.'
    );

    releasePlayback();
    await first;
    expect(service.processing).toBe(false);
  });

  it('失敗した場合も processing が false に戻る', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 400 }));
    const service = new TtsService(BASE_CONFIG, undefined, vi.fn().mockResolvedValue(undefined));
    await expect(service.speak('やあ')).rejects.toThrow();
    expect(service.processing).toBe(false);
  });
});

describe('TtsService - audio_query のエラー分類', () => {
  it('非 2xx は API エラーになる', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }));
    const service = new TtsService(BASE_CONFIG, undefined, vi.fn().mockResolvedValue(undefined));
    await expect(service.speak('やあ')).rejects.toMatchObject({
      type: ErrorType.API,
      message: 'API error (404): Failed to create audio query',
    });
  });

  it('AbortError はタイムアウトエラーになる', async () => {
    const abortError = new Error('aborted');
    abortError.name = 'AbortError';
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(abortError));
    const service = new TtsService(BASE_CONFIG, undefined, vi.fn().mockResolvedValue(undefined));
    await expect(service.speak('やあ')).rejects.toMatchObject({
      type: ErrorType.TIMEOUT,
      message: 'Timeout: no response within 1000ms',
    });
  });

  it('その他の例外はネットワークエラーになる', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('socket hang up')));
    const service = new TtsService(BASE_CONFIG, undefined, vi.fn().mockResolvedValue(undefined));
    await expect(service.speak('やあ')).rejects.toMatchObject({
      type: ErrorType.NETWORK,
      message: 'Network error: Error during audio query creation',
    });
  });
});

describe('TtsService - synthesis のエラー分類', () => {
  function stubQueryThen(rejectionOrResponse: unknown, isRejection: boolean) {
    const second = isRejection
      ? vi.fn().mockRejectedValueOnce(rejectionOrResponse)
      : vi.fn().mockResolvedValueOnce(rejectionOrResponse);
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => makeQuery() })
      .mockImplementationOnce(() => second());
    vi.stubGlobal('fetch', fetchMock);
  }

  it('非 2xx は API エラーになる', async () => {
    stubQueryThen({ ok: false, status: 500 }, false);
    const service = new TtsService({ ...BASE_CONFIG, maxRetries: 1 }, undefined, vi.fn().mockResolvedValue(undefined));
    await expect(service.speak('やあ')).rejects.toMatchObject({
      type: ErrorType.API,
      message: 'API error (500): Failed to synthesize audio',
    });
  });

  it('AbortError はタイムアウトエラーになる', async () => {
    const abortError = new Error('aborted');
    abortError.name = 'AbortError';
    stubQueryThen(abortError, true);
    const service = new TtsService({ ...BASE_CONFIG, maxRetries: 1 }, undefined, vi.fn().mockResolvedValue(undefined));
    await expect(service.speak('やあ')).rejects.toMatchObject({ type: ErrorType.TIMEOUT });
  });

  it('その他の例外はネットワークエラーになる', async () => {
    stubQueryThen(new Error('socket hang up'), true);
    const service = new TtsService({ ...BASE_CONFIG, maxRetries: 1 }, undefined, vi.fn().mockResolvedValue(undefined));
    await expect(service.speak('やあ')).rejects.toMatchObject({
      type: ErrorType.NETWORK,
      message: 'Network error: Error during audio synthesis',
    });
  });

  it('設定した timeout で実際に AbortSignal が発火し、タイムアウトエラーになる', async () => {
    vi.useFakeTimers();
    try {
      let capturedSignal: AbortSignal | undefined;
      const fetchMock = vi.fn()
        .mockResolvedValueOnce({ ok: true, status: 200, json: async () => makeQuery() })
        .mockImplementationOnce((_url: string, init: RequestInit) => {
          capturedSignal = init.signal as AbortSignal;
          return new Promise((_resolve, reject) => {
            init.signal!.addEventListener('abort', () => {
              const err = new Error('aborted');
              err.name = 'AbortError';
              reject(err);
            });
          });
        });
      vi.stubGlobal('fetch', fetchMock);
      const service = new TtsService({ ...BASE_CONFIG, maxRetries: 1 }, undefined, vi.fn().mockResolvedValue(undefined));

      const promise = service.speak('やあ');
      const assertion = expect(promise).rejects.toMatchObject({ type: ErrorType.TIMEOUT });

      await vi.waitFor(() => expect(capturedSignal).toBeDefined());
      expect(capturedSignal!.aborted).toBe(false);
      await vi.advanceTimersByTimeAsync(BASE_CONFIG.timeout!);
      expect(capturedSignal!.aborted).toBe(true);

      await assertion;
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('TtsService - リトライ', () => {
  it('再試行不可能なエラー（4xx）ではリトライしない', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 400 });
    vi.stubGlobal('fetch', fetchMock);
    const service = new TtsService(BASE_CONFIG, undefined, vi.fn().mockResolvedValue(undefined));
    await expect(service.speak('やあ')).rejects.toMatchObject({ type: ErrorType.API });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('再試行可能なエラー（5xx）は maxRetries 回まで試す', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 503 });
    vi.stubGlobal('fetch', fetchMock);
    const service = new TtsService({ ...BASE_CONFIG, retryDelay: 0 }, undefined, vi.fn().mockResolvedValue(undefined));
    await expect(service.speak('やあ')).rejects.toMatchObject({ type: ErrorType.API });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('リトライ間隔は retryDelay * 試行回数（指数バックオフ）', async () => {
    vi.useFakeTimers();
    try {
      const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 503 });
      vi.stubGlobal('fetch', fetchMock);
      const service = new TtsService(BASE_CONFIG, undefined, vi.fn().mockResolvedValue(undefined));

      const promise = service.speak('やあ');
      const assertion = expect(promise).rejects.toMatchObject({ type: ErrorType.API });

      await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
      await vi.advanceTimersByTimeAsync(100); // 1 回目の待機 = 100ms
      await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
      await vi.advanceTimersByTimeAsync(200); // 2 回目の待機 = 200ms
      await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));

      await assertion;
    } finally {
      vi.useRealTimers();
    }
  });

  it('リトライ後に成功すれば例外を投げない', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 503 })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => makeQuery() })
      .mockResolvedValueOnce({ ok: true, status: 200, arrayBuffer: async () => makeAudioBuffer() });
    vi.stubGlobal('fetch', fetchMock);
    const service = new TtsService({ ...BASE_CONFIG, retryDelay: 0 }, undefined, vi.fn().mockResolvedValue(undefined));
    await expect(service.speak('やあ')).resolves.toBeUndefined();
  });
});

function makeVrmStub(overrides: { setVowelFails?: boolean } = {}) {
  return {
    setVowel: vi.fn((_vowel: 'a' | 'i' | 'u' | 'e' | 'o' | null) => overrides.setVowelFails
      ? Promise.reject(new Error('vrm down'))
      : Promise.resolve()),
  };
}

describe('TtsService - 一時ファイルの扱い', () => {
  it('合成した音声を一時ファイルへ書き出す', async () => {
    stubHappyFetch();
    await new TtsService(BASE_CONFIG, undefined, vi.fn().mockResolvedValue(undefined)).speak('やあ');
    expect(writeFileSync).toHaveBeenCalledTimes(1);
    const [path, buffer] = vi.mocked(writeFileSync).mock.calls[0];
    expect(String(path)).toContain('desktop-mascot_temp_audio.wav');
    expect(Buffer.isBuffer(buffer)).toBe(true);
  });

  it('再生成功時に一時ファイルを削除する', async () => {
    stubHappyFetch();
    await new TtsService(BASE_CONFIG, undefined, vi.fn().mockResolvedValue(undefined)).speak('やあ');
    expect(unlinkSync).toHaveBeenCalledTimes(1);
  });

  it('再生失敗時も一時ファイルを削除し、再生エラーを投げる', async () => {
    stubHappyFetch();
    const service = new TtsService(
      { ...BASE_CONFIG, maxRetries: 1 },
      undefined,
      vi.fn().mockRejectedValue(new Error('no audio device'))
    );
    await expect(service.speak('やあ')).rejects.toMatchObject({
      type: ErrorType.PLAYBACK,
      retryable: false,
    });
    expect(unlinkSync).toHaveBeenCalledTimes(1);
  });

  it('再生失敗が Error インスタンスでなくても再生エラーに変換する', async () => {
    stubHappyFetch();
    const service = new TtsService(
      { ...BASE_CONFIG, maxRetries: 1 },
      undefined,
      vi.fn().mockRejectedValue('no audio device')
    );
    await expect(service.speak('やあ')).rejects.toMatchObject({
      type: ErrorType.PLAYBACK,
      retryable: false,
    });
  });

  it('一時ファイルが存在しなければ削除しない', async () => {
    vi.mocked(existsSync).mockReturnValue(false);
    stubHappyFetch();
    await new TtsService(BASE_CONFIG, undefined, vi.fn().mockResolvedValue(undefined)).speak('やあ');
    expect(unlinkSync).not.toHaveBeenCalled();
  });

  it('削除に失敗しても例外を伝播させない', async () => {
    vi.mocked(unlinkSync).mockImplementation(() => { throw new Error('EBUSY'); });
    stubHappyFetch();
    await expect(
      new TtsService(BASE_CONFIG, undefined, vi.fn().mockResolvedValue(undefined)).speak('やあ')
    ).resolves.toBeUndefined();
  });
});

describe('TtsService - リップシンク', () => {
  it('vrmControl 未指定なら setVowel を呼ばない（例外も出ない）', async () => {
    stubHappyFetch();
    await expect(
      new TtsService(BASE_CONFIG, undefined, vi.fn().mockResolvedValue(undefined)).speak('やあ')
    ).resolves.toBeUndefined();
  });

  it('母音のタイミングごとに setVowel を呼び、最後に null で口を閉じる', async () => {
    vi.useFakeTimers();
    try {
      stubHappyFetch(makeQuery(['a', 'i']));
      const vrm = makeVrmStub();
      const service = new TtsService(BASE_CONFIG, vrm as unknown as VRMControlService, vi.fn().mockResolvedValue(undefined));

      const promise = service.speak('あい');
      await vi.advanceTimersByTimeAsync(1000);
      await promise;

      expect(vrm.setVowel.mock.calls.map((c) => c[0])).toEqual(['a', 'i', null]);
    } finally {
      vi.useRealTimers();
    }
  });

  it('playbackStartOffsetMs ぶん遅らせて最初の母音を送る', async () => {
    vi.useFakeTimers();
    try {
      stubHappyFetch(makeQuery(['a']));
      const vrm = makeVrmStub();
      const service = new TtsService(
        { ...BASE_CONFIG, playbackStartOffsetMs: 150 },
        vrm as unknown as VRMControlService,
        vi.fn().mockResolvedValue(undefined)
      );

      const promise = service.speak('あ');
      await vi.advanceTimersByTimeAsync(100);
      expect(vrm.setVowel).not.toHaveBeenCalled();
      await vi.advanceTimersByTimeAsync(100);
      expect(vrm.setVowel).toHaveBeenCalledWith('a');

      await vi.advanceTimersByTimeAsync(1000);
      await promise;
    } finally {
      vi.useRealTimers();
    }
  });

  it('母音が 1 つも無ければ setVowel を一切呼ばない', async () => {
    stubHappyFetch(makeQuery([]));
    const vrm = makeVrmStub();
    await new TtsService(BASE_CONFIG, vrm as unknown as VRMControlService, vi.fn().mockResolvedValue(undefined)).speak('。');
    expect(vrm.setVowel).not.toHaveBeenCalled();
  });

  it('setVowel が失敗してもリップシンクを継続し、発話は成功する', async () => {
    vi.useFakeTimers();
    try {
      stubHappyFetch(makeQuery(['a', 'i']));
      const vrm = makeVrmStub({ setVowelFails: true });
      const service = new TtsService(BASE_CONFIG, vrm as unknown as VRMControlService, vi.fn().mockResolvedValue(undefined));

      const promise = service.speak('あい');
      await vi.advanceTimersByTimeAsync(1000);
      await expect(promise).resolves.toBeUndefined();
      expect(vrm.setVowel).toHaveBeenCalledTimes(3);
    } finally {
      vi.useRealTimers();
    }
  });
});
