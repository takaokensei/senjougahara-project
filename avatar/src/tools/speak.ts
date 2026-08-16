import { TtsService } from '../services/TtsService.js';
import { VRMControlService } from '../services/VRMControlService.js';

/**
 * speak tool定義
 */
export function createSpeakTool(service: TtsService, vrmControl?: VRMControlService) {
  return {
    name: 'speak',
    description: 'テキストを音声で読み上げます。VRMキャラクターの表情とアニメーションを制御します。',
    inputSchema: {
      type: 'object',
      properties: {
        text: {
          type: 'string',
          description: '読み上げるテキスト。日本語で自然な会話文を入力してください。',
        },
        emotion: {
          type: 'string',
          enum: ['neutral', 'happy', 'sad', 'angry', 'relaxed', 'surprised'],
          description: 'VRMの表情（省略時はneutral）。会話の感情に応じて指定してください。',
        },
        animation: {
          type: 'string',
          enum: ['wave', 'nod', 'shake', 'think', 'clap', 'angry', 'happy', 'surprised', 'shy', 'cheer'],
          description: '発話中に再生するアニメーション（省略可）。ジェスチャーまたは感情表現のアニメーションを選択してください。',
        },
      },
      required: ['text'],
    },
    handler: async (args: { text: string; emotion?: string; animation?: string }) => {
      const { text, emotion = 'neutral', animation } = args;

      // 入力検証
      if (!text || text.trim().length === 0) {
        return {
          content: [{ type: 'text', text: 'Error: text is empty.' }],
        };
      }

      const validEmotions = ['neutral', 'happy', 'sad', 'angry', 'relaxed', 'surprised'];
      const finalEmotion = validEmotions.includes(emotion) ? emotion : 'neutral';

      // character 可用性チェック（ECONNREFUSED は即時失敗するので低コスト）
      const characterAvailable = vrmControl ? await vrmControl.isVRMWindowRunning() : false;

      // VRM コマンド送信（未起動なら VRMControlService 内で静かに失敗）
      if (animation && vrmControl) await vrmControl.playAnimation(animation);
      if (vrmControl) await vrmControl.notifySpeak(text, finalEmotion);

      // TTS 実行
      let ttsAvailable = true;
      try {
        await service.speak(text);
      } catch (error) {
        console.error('[speak tool] TTS error:', error instanceof Error ? error.message : error);
        ttsAvailable = false;
      }

      // 表情リセット
      if (characterAvailable && finalEmotion !== 'neutral' && vrmControl) {
        await vrmControl.setEmotion('neutral');
      }

      // レスポンス組み立て
      const notes: string[] = [];
      if (!ttsAvailable) notes.push('tts unavailable');
      if (!characterAvailable) notes.push('character unavailable');

      return {
        content: [{
          type: 'text',
          text: notes.length > 0 ? `OK (${notes.join(', ')})` : 'OK',
        }],
      };
    },
  };
}
