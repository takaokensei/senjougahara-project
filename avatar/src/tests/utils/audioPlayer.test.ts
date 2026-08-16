import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const execFileMock = vi.fn();
vi.mock('child_process', () => ({
  execFile: (...args: unknown[]) => execFileMock(...args),
}));

import {
  buildPlayCommand,
  getPlaybackStartOffset,
  createDefaultAudioPlayer,
} from '../../utils/audioPlayer.js';

describe('buildPlayCommand', () => {
  it('win32 では PowerShell の SoundPlayer を使う', () => {
    expect(buildPlayCommand('win32', 'C:\\tmp\\a.wav')).toEqual({
      command: 'powershell',
      args: [
        '-NoProfile',
        '-NonInteractive',
        '-Command',
        "(New-Object Media.SoundPlayer 'C:\\tmp\\a.wav').PlaySync()",
      ],
    });
  });

  it('win32 ではシングルクォートを 2 個に重ねてエスケープする', () => {
    const { args } = buildPlayCommand('win32', "C:\\it's\\a.wav");
    expect(args[3]).toBe("(New-Object Media.SoundPlayer 'C:\\it''s\\a.wav').PlaySync()");
  });

  it('darwin では afplay を使う', () => {
    expect(buildPlayCommand('darwin', '/tmp/a.wav')).toEqual({
      command: 'afplay',
      args: ['/tmp/a.wav'],
    });
  });

  it('linux では aplay を使う', () => {
    expect(buildPlayCommand('linux', '/tmp/a.wav')).toEqual({
      command: 'aplay',
      args: ['/tmp/a.wav'],
    });
  });

  it('未知のプラットフォームは linux と同じ扱いにする', () => {
    expect(buildPlayCommand('freebsd', '/tmp/a.wav').command).toBe('aplay');
  });
});

describe('getPlaybackStartOffset', () => {
  it('win32 は PowerShell の起動が重いため 150ms', () => {
    expect(getPlaybackStartOffset('win32')).toBe(150);
  });

  it.each<NodeJS.Platform>(['darwin', 'linux'])('%s は 50ms', (platform) => {
    expect(getPlaybackStartOffset(platform)).toBe(50);
  });
});

describe('createDefaultAudioPlayer', () => {
  beforeEach(() => {
    execFileMock.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('プラットフォームに応じたコマンドを execFile に渡す', async () => {
    execFileMock.mockImplementation((_cmd, _args, cb) => cb(null));
    await createDefaultAudioPlayer('darwin')('/tmp/a.wav');
    expect(execFileMock).toHaveBeenCalledWith('afplay', ['/tmp/a.wav'], expect.any(Function));
  });

  it('execFile が成功したら resolve する', async () => {
    execFileMock.mockImplementation((_cmd, _args, cb) => cb(null));
    await expect(createDefaultAudioPlayer('linux')('/tmp/a.wav')).resolves.toBeUndefined();
  });

  it('execFile が失敗したら reject する', async () => {
    execFileMock.mockImplementation((_cmd, _args, cb) => cb(new Error('no audio device')));
    await expect(createDefaultAudioPlayer('linux')('/tmp/a.wav')).rejects.toThrow('no audio device');
  });

  it('プラットフォーム省略時は process.platform を使う', async () => {
    execFileMock.mockImplementation((_cmd, _args, cb) => cb(null));
    await createDefaultAudioPlayer()('/tmp/a.wav');
    const expected = buildPlayCommand(process.platform, '/tmp/a.wav');
    expect(execFileMock).toHaveBeenCalledWith(expected.command, expected.args, expect.any(Function));
  });
});
