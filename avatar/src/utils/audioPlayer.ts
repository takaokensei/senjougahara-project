import { execFile } from 'child_process';

export type PlayCommand = { command: string; args: string[] };
export type AudioPlayer = (filePath: string) => Promise<void>;

/**
 * OS ごとの音声再生コマンドを構築する（シェルを経由しない execFile 用）
 */
export function buildPlayCommand(platform: NodeJS.Platform, filePath: string): PlayCommand {
  if (platform === 'win32') {
    const escaped = filePath.replace(/'/g, "''");
    return {
      command: 'powershell',
      args: [
        '-NoProfile',
        '-NonInteractive',
        '-Command',
        `(New-Object Media.SoundPlayer '${escaped}').PlaySync()`,
      ],
    };
  }
  if (platform === 'darwin') {
    return { command: 'afplay', args: [filePath] };
  }
  return { command: 'aplay', args: [filePath] };
}

/**
 * 再生開始オフセット（ミリ秒）
 * PowerShell は起動が重いため Windows のみ大きめの値を返す
 */
export function getPlaybackStartOffset(platform: NodeJS.Platform): number {
  return platform === 'win32' ? 150 : 50;
}

/**
 * 実際に OS のコマンドを呼ぶ再生関数を生成する
 */
export function createDefaultAudioPlayer(platform: NodeJS.Platform = process.platform): AudioPlayer {
  return (filePath: string) =>
    new Promise<void>((resolve, reject) => {
      const { command, args } = buildPlayCommand(platform, filePath);
      execFile(command, args, (error) => {
        if (error) reject(error);
        else resolve();
      });
    });
}
