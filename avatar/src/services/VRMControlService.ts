/**
 * VRMControlService - Electronウィンドウと通信してVRMを制御
 */
export class VRMControlService {
  private readonly baseUrl: string;

  constructor(port: number = 3939) {
    this.baseUrl = `http://localhost:${port}`;
  }

  /**
   * 共通HTTPリクエスト処理
   * VRMウィンドウが起動していない場合（ECONNREFUSED）は静かに失敗
   */
  private async makeRequest(endpoint: string, payload: unknown): Promise<void> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetch(`${this.baseUrl}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
    } catch (error) {
      if (error instanceof Error) {
        if (error.message.includes('ECONNREFUSED')) {
          console.error(`VRM window not running - skipping ${endpoint}`);
        } else if (error.name === 'AbortError') {
          console.error(`VRM request timed out - skipping ${endpoint}`);
        } else {
          console.error(`Failed to call ${endpoint}:`, error);
        }
      }
    } finally {
      clearTimeout(timeoutId);
    }
  }

  /**
   * 母音を設定
   */
  async setVowel(vowel: 'a' | 'i' | 'u' | 'e' | 'o' | null): Promise<void> {
    await this.makeRequest('/vrm/vowel', { vowel });
  }

  /**
   * 感情を設定
   */
  async setEmotion(emotion: 'neutral' | 'happy' | 'angry' | 'sad' | 'relaxed' | 'surprised'): Promise<void> {
    await this.makeRequest('/vrm/emotion', { emotion });
  }

  /**
   * 音声再生開始を通知
   */
  async notifySpeak(text: string, emotion?: string): Promise<void> {
    await this.makeRequest('/vrm/speak', { text, emotion });
  }

  /**
   * アニメーションを再生
   */
  async playAnimation(animation: string): Promise<void> {
    await this.makeRequest('/vrm/animation', { animation });
  }

  /**
   * VRMウィンドウの起動状態をチェック
   */
  async isVRMWindowRunning(): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl}/health`);
      return response.ok;
    } catch {
      return false;
    }
  }
}
