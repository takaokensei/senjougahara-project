import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { VRMControlService } from '../../services/VRMControlService.js';

function okResponse() {
  return { ok: true, status: 200, statusText: 'OK' } as Response;
}

describe('VRMControlService - リクエスト送信', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn().mockResolvedValue(okResponse());
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('デフォルトポート 3939 を使う', async () => {
    await new VRMControlService().setVowel('a');
    expect(fetchMock.mock.calls[0][0]).toBe('http://localhost:3939/vrm/vowel');
  });

  it('コンストラクタでポートを変更できる', async () => {
    await new VRMControlService(4000).setVowel('a');
    expect(fetchMock.mock.calls[0][0]).toBe('http://localhost:4000/vrm/vowel');
  });

  it('setVowel が POST と JSON ヘッダーで送る', async () => {
    await new VRMControlService().setVowel('i');
    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe('POST');
    expect(init.headers).toEqual({ 'Content-Type': 'application/json' });
    expect(JSON.parse(init.body)).toEqual({ vowel: 'i' });
  });

  it('setVowel(null) も送信する', async () => {
    await new VRMControlService().setVowel(null);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ vowel: null });
  });

  it('setEmotion が /vrm/emotion に送る', async () => {
    await new VRMControlService().setEmotion('happy');
    expect(fetchMock.mock.calls[0][0]).toBe('http://localhost:3939/vrm/emotion');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ emotion: 'happy' });
  });

  it('notifySpeak が /vrm/speak に text と emotion を送る', async () => {
    await new VRMControlService().notifySpeak('こんにちは', 'sad');
    expect(fetchMock.mock.calls[0][0]).toBe('http://localhost:3939/vrm/speak');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ text: 'こんにちは', emotion: 'sad' });
  });

  it('notifySpeak は emotion 省略時に text だけ送る', async () => {
    await new VRMControlService().notifySpeak('やあ');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ text: 'やあ' });
  });

  it('playAnimation が /vrm/animation に送る', async () => {
    await new VRMControlService().playAnimation('wave');
    expect(fetchMock.mock.calls[0][0]).toBe('http://localhost:3939/vrm/animation');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ animation: 'wave' });
  });
});

describe('VRMControlService - graceful degradation', () => {
  let errorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('非 2xx 応答でも例外を投げない', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500, statusText: 'Server Error' }));
    await expect(new VRMControlService().setVowel('a')).resolves.toBeUndefined();
    expect(errorSpy.mock.calls[0][0]).toContain('Failed to call /vrm/vowel');
  });

  it('ECONNREFUSED では未起動として静かに失敗する', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('connect ECONNREFUSED 127.0.0.1:3939')));
    await new VRMControlService().setVowel('a');
    expect(errorSpy).toHaveBeenCalledWith('VRM window not running - skipping /vrm/vowel');
  });

  it('AbortError ではタイムアウトとして静かに失敗する', async () => {
    const abortError = new Error('aborted');
    abortError.name = 'AbortError';
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(abortError));
    await new VRMControlService().setEmotion('happy');
    expect(errorSpy).toHaveBeenCalledWith('VRM request timed out - skipping /vrm/emotion');
  });

  it('Error でない値が throw されても落ちない', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue('boom'));
    await expect(new VRMControlService().playAnimation('wave')).resolves.toBeUndefined();
    expect(errorSpy).not.toHaveBeenCalled();
  });
});

describe('VRMControlService - タイムアウト', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('5 秒経過で AbortSignal が発火する', async () => {
    let capturedSignal: AbortSignal | undefined;
    vi.stubGlobal('fetch', vi.fn((_url: string, init: RequestInit) => {
      capturedSignal = init.signal as AbortSignal;
      return new Promise((_resolve, reject) => {
        init.signal!.addEventListener('abort', () => {
          const err = new Error('aborted');
          err.name = 'AbortError';
          reject(err);
        });
      });
    }));

    const promise = new VRMControlService().setVowel('a');
    expect(capturedSignal!.aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(5000);
    await promise;
    expect(capturedSignal!.aborted).toBe(true);
  });
});

describe('VRMControlService.isVRMWindowRunning', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('/health が 200 なら true', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true }));
    await expect(new VRMControlService().isVRMWindowRunning()).resolves.toBe(true);
  });

  it('/health が非 2xx なら false', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
    await expect(new VRMControlService().isVRMWindowRunning()).resolves.toBe(false);
  });

  it('fetch が失敗したら false', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('ECONNREFUSED')));
    await expect(new VRMControlService().isVRMWindowRunning()).resolves.toBe(false);
  });
});
