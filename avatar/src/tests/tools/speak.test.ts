import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createSpeakTool } from '../../tools/speak.js';
import type { TtsService } from '../../services/TtsService.js';
import type { VRMControlService } from '../../services/VRMControlService.js';

function makeStubs(options: { characterAvailable?: boolean; ttsFails?: boolean } = {}) {
  const { characterAvailable = true, ttsFails = false } = options;
  const tts = {
    speak: vi.fn(ttsFails ? () => Promise.reject(new Error('tts down')) : () => Promise.resolve()),
  };
  const vrm = {
    isVRMWindowRunning: vi.fn().mockResolvedValue(characterAvailable),
    playAnimation: vi.fn().mockResolvedValue(undefined),
    notifySpeak: vi.fn().mockResolvedValue(undefined),
    setEmotion: vi.fn().mockResolvedValue(undefined),
  };
  return { tts, vrm };
}

function makeTool(options: Parameters<typeof makeStubs>[0] = {}) {
  const { tts, vrm } = makeStubs(options);
  const tool = createSpeakTool(tts as unknown as TtsService, vrm as unknown as VRMControlService);
  return { tool, tts, vrm };
}

function textOf(result: { content: Array<{ type: string; text: string }> }) {
  return result.content[0].text;
}

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

describe('speak tool - 定義', () => {
  it('name と required が仕様どおり', () => {
    const { tool } = makeTool();
    expect(tool.name).toBe('speak');
    expect(tool.inputSchema.required).toEqual(['text']);
  });

  it('emotion と animation の enum が仕様どおり', () => {
    const { tool } = makeTool();
    expect(tool.inputSchema.properties.emotion.enum).toEqual(
      ['neutral', 'happy', 'sad', 'angry', 'relaxed', 'surprised']
    );
    expect(tool.inputSchema.properties.animation.enum).toEqual(
      ['wave', 'nod', 'shake', 'think', 'clap', 'angry', 'happy', 'surprised', 'shy', 'cheer']
    );
  });
});

describe('speak tool - 入力検証', () => {
  it('空文字ではエラーを返し TTS も VRM も呼ばない', async () => {
    const { tool, tts, vrm } = makeTool();
    const result = await tool.handler({ text: '' });
    expect(textOf(result)).toBe('Error: text is empty.');
    expect(tts.speak).not.toHaveBeenCalled();
    expect(vrm.notifySpeak).not.toHaveBeenCalled();
  });

  it('空白のみでもエラーを返す', async () => {
    const { tool } = makeTool();
    expect(textOf(await tool.handler({ text: '   ' }))).toBe('Error: text is empty.');
  });
});

describe('speak tool - 正常系', () => {
  it('成功時は OK を返す', async () => {
    const { tool, tts } = makeTool();
    expect(textOf(await tool.handler({ text: 'こんにちは' }))).toBe('OK');
    expect(tts.speak).toHaveBeenCalledWith('こんにちは');
  });

  it('emotion 省略時は neutral で notifySpeak する', async () => {
    const { tool, vrm } = makeTool();
    await tool.handler({ text: 'やあ' });
    expect(vrm.notifySpeak).toHaveBeenCalledWith('やあ', 'neutral');
  });

  it('不正な emotion は neutral にフォールバックする', async () => {
    const { tool, vrm } = makeTool();
    await tool.handler({ text: 'やあ', emotion: 'excited' });
    expect(vrm.notifySpeak).toHaveBeenCalledWith('やあ', 'neutral');
  });

  it('animation 指定時のみ playAnimation を呼ぶ', async () => {
    const withAnim = makeTool();
    await withAnim.tool.handler({ text: 'やあ', animation: 'wave' });
    expect(withAnim.vrm.playAnimation).toHaveBeenCalledWith('wave');

    const withoutAnim = makeTool();
    await withoutAnim.tool.handler({ text: 'やあ' });
    expect(withoutAnim.vrm.playAnimation).not.toHaveBeenCalled();
  });
});

describe('speak tool - 表情リセット', () => {
  it('character 利用可能 かつ neutral 以外ならリセットする', async () => {
    const { tool, vrm } = makeTool({ characterAvailable: true });
    await tool.handler({ text: 'やあ', emotion: 'happy' });
    expect(vrm.setEmotion).toHaveBeenCalledWith('neutral');
  });

  it('neutral のときはリセットしない', async () => {
    const { tool, vrm } = makeTool({ characterAvailable: true });
    await tool.handler({ text: 'やあ', emotion: 'neutral' });
    expect(vrm.setEmotion).not.toHaveBeenCalled();
  });

  it('character 未起動のときはリセットしない', async () => {
    const { tool, vrm } = makeTool({ characterAvailable: false });
    await tool.handler({ text: 'やあ', emotion: 'happy' });
    expect(vrm.setEmotion).not.toHaveBeenCalled();
  });
});

describe('speak tool - graceful degradation', () => {
  it('TTS 失敗時は OK (tts unavailable)', async () => {
    const { tool } = makeTool({ ttsFails: true, characterAvailable: true });
    expect(textOf(await tool.handler({ text: 'やあ' }))).toBe('OK (tts unavailable)');
  });

  it('character 未起動時は OK (character unavailable)', async () => {
    const { tool } = makeTool({ characterAvailable: false });
    expect(textOf(await tool.handler({ text: 'やあ' }))).toBe('OK (character unavailable)');
  });

  it('両方不可なら両方を列挙する', async () => {
    const { tool } = makeTool({ ttsFails: true, characterAvailable: false });
    expect(textOf(await tool.handler({ text: 'やあ' }))).toBe('OK (tts unavailable, character unavailable)');
  });

  it('vrmControl 未指定でも落ちず character unavailable になる', async () => {
    const { tts } = makeStubs();
    const tool = createSpeakTool(tts as unknown as TtsService);
    expect(textOf(await tool.handler({ text: 'やあ' }))).toBe('OK (character unavailable)');
    expect(tts.speak).toHaveBeenCalledWith('やあ');
  });

  it('TTS が Error 以外を throw しても落ちない', async () => {
    const { tts, vrm } = makeStubs();
    tts.speak = vi.fn().mockRejectedValue('boom');
    const tool = createSpeakTool(tts as unknown as TtsService, vrm as unknown as VRMControlService);
    expect(textOf(await tool.handler({ text: 'やあ' }))).toBe('OK (tts unavailable)');
  });
});
