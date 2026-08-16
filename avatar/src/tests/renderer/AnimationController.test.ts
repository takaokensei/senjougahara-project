import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as THREE from 'three';
import { AnimationController } from '../../renderer/AnimationController.js';
import type { VrmAnimationLoader } from '../../renderer/AnimationController.js';
import type { VRM } from '@pixiv/three-vrm';

function makeAction() {
  const action: Record<string, unknown> = {
    loop: undefined,
    clampWhenFinished: false,
  };
  action.reset = vi.fn(() => action);
  action.play = vi.fn(() => action);
  action.fadeIn = vi.fn(() => action);
  action.fadeOut = vi.fn(() => action);
  return action;
}

function makeMixer() {
  const actions: Record<string, unknown>[] = [];
  return {
    actions,
    clipAction: vi.fn(() => {
      const action = makeAction();
      actions.push(action);
      return action;
    }),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    stopAllAction: vi.fn(),
    update: vi.fn(),
  };
}

function makeVrm(withHumanoid = true) {
  const leftUpperArm = { rotation: { z: 0 } };
  const rightUpperArm = { rotation: { z: 0 } };
  const humanoid = {
    getNormalizedBoneNode: vi.fn((name: string) =>
      name === 'leftUpperArm' ? leftUpperArm : name === 'rightUpperArm' ? rightUpperArm : null
    ),
  };
  return {
    vrm: { humanoid: withHumanoid ? humanoid : undefined } as unknown as VRM,
    leftUpperArm,
    rightUpperArm,
    humanoid,
  };
}

function animConfig(overrides: Record<string, unknown> = {}) {
  return {
    name: 'idle', file: 'idle.vrma', loop: true, fadeTime: 0.3,
    returnToIdle: false, category: 'idle', description: '',
    ...overrides,
  };
}

function stubConfigFetch(config: Record<string, unknown>) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ json: async () => config }));
}

const okLoader: VrmAnimationLoader = async () => new THREE.AnimationClip('clip', 1, []);

beforeEach(() => {
  vi.spyOn(console, 'log').mockImplementation(() => {});
  vi.spyOn(console, 'warn').mockImplementation(() => {});
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('loadAll', () => {
  it('設定ファイルのアニメーションを読み込む', async () => {
    stubConfigFetch({ animations: [animConfig(), animConfig({ name: 'wave', file: 'wave.vrma', loop: false })] });
    const mixer = makeMixer();
    const loader = vi.fn(okLoader);
    const controller = new AnimationController(makeVrm().vrm, mixer as never, loader);

    await controller.loadAll('./assets/animations/animations.json');

    expect(loader).toHaveBeenCalledTimes(2);
    expect(loader).toHaveBeenCalledWith('idle.vrma', expect.anything());
  });

  it('loop:true は LoopRepeat、loop:false は LoopOnce を設定する', async () => {
    stubConfigFetch({ animations: [animConfig(), animConfig({ name: 'wave', file: 'wave.vrma', loop: false })] });
    const mixer = makeMixer();
    await new AnimationController(makeVrm().vrm, mixer as never, okLoader).loadAll('x.json');

    expect(mixer.actions[0].loop).toBe(THREE.LoopRepeat);
    expect(mixer.actions[1].loop).toBe(THREE.LoopOnce);
  });

  it('loop:false かつ returnToIdle:true のときだけ finished リスナーを登録する', async () => {
    stubConfigFetch({ animations: [
      animConfig({ name: 'wave', file: 'wave.vrma', loop: false, returnToIdle: true }),
      animConfig({ name: 'nod', file: 'nod.vrma', loop: false, returnToIdle: false }),
    ] });
    const mixer = makeMixer();
    await new AnimationController(makeVrm().vrm, mixer as never, okLoader).loadAll('x.json');

    expect(mixer.addEventListener).toHaveBeenCalledTimes(1);
  });

  it('finished リスナーは該当アクションのときだけ idle に戻す', async () => {
    stubConfigFetch({ animations: [
      animConfig(),
      animConfig({ name: 'wave', file: 'wave.vrma', loop: false, returnToIdle: true }),
    ] });
    const mixer = makeMixer();
    const controller = new AnimationController(makeVrm().vrm, mixer as never, okLoader);
    await controller.loadAll('x.json');
    controller.play('wave');

    const listener = mixer.addEventListener.mock.calls[0][1] as (e: unknown) => void;

    listener({ action: mixer.actions[0] }); // 別アクション → 無視
    expect(mixer.actions[0].fadeIn).not.toHaveBeenCalled();

    listener({ action: mixer.actions[1] }); // 該当アクション → idle へ
    expect(mixer.actions[0].fadeIn).toHaveBeenCalled();
  });

  it('クリップが見つからないアニメーションはスキップする', async () => {
    stubConfigFetch({ animations: [animConfig()] });
    const mixer = makeMixer();
    const controller = new AnimationController(makeVrm().vrm, mixer as never, async () => null);
    await controller.loadAll('x.json');

    expect(mixer.clipAction).not.toHaveBeenCalled();
  });

  it('個別の読み込み失敗は握りつぶして続行する', async () => {
    stubConfigFetch({ animations: [
      animConfig({ name: 'broken', file: 'broken.vrma' }),
      animConfig({ name: 'idle', file: 'idle.vrma' }),
    ] });
    const mixer = makeMixer();
    const loader = vi.fn(async (file: string) => {
      if (file === 'broken.vrma') throw new Error('parse error');
      return new THREE.AnimationClip('clip', 1, []);
    });
    const controller = new AnimationController(makeVrm().vrm, mixer as never, loader);

    await expect(controller.loadAll('x.json')).resolves.toBeUndefined();
    expect(mixer.clipAction).toHaveBeenCalledTimes(1);
  });

  it('idleVariation 設定を読み取る', async () => {
    vi.useFakeTimers();
    try {
      stubConfigFetch({
        animations: [animConfig()],
        config: { idleVariation: { enabled: true, delayMin: 1000, delayMax: 1000, animations: ['look'] } },
      });
      const mixer = makeMixer();
      const controller = new AnimationController(makeVrm().vrm, mixer as never, okLoader, () => 0);
      await controller.loadAll('x.json');
      controller.applyInitialState();

      expect(vi.getTimerCount()).toBe(1);
      controller.dispose();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('applyInitialState', () => {
  it('idle があれば再生する', async () => {
    stubConfigFetch({ animations: [animConfig()] });
    const mixer = makeMixer();
    const controller = new AnimationController(makeVrm().vrm, mixer as never, okLoader);
    await controller.loadAll('x.json');
    controller.applyInitialState();

    expect(mixer.actions[0].play).toHaveBeenCalled();
  });

  it('idle が無ければ両腕を下ろすデフォルトポーズを適用する', () => {
    const { vrm, leftUpperArm, rightUpperArm } = makeVrm();
    new AnimationController(vrm, makeMixer() as never, okLoader).applyInitialState();

    expect(leftUpperArm.rotation.z).toBeCloseTo(Math.PI / 3);
    expect(rightUpperArm.rotation.z).toBeCloseTo(-Math.PI / 3);
  });

  it('humanoid が無ければ何もしない', () => {
    const { vrm } = makeVrm(false);
    expect(() => new AnimationController(vrm, makeMixer() as never, okLoader).applyInitialState()).not.toThrow();
  });

  it('ボーンが見つからなくても落ちない', () => {
    const { vrm, humanoid } = makeVrm();
    humanoid.getNormalizedBoneNode.mockReturnValue(null);
    expect(() => new AnimationController(vrm, makeMixer() as never, okLoader).applyInitialState()).not.toThrow();
  });
});

describe('play', () => {
  async function loadedController(random: () => number = Math.random) {
    stubConfigFetch({ animations: [
      animConfig(),
      animConfig({ name: 'wave', file: 'wave.vrma', loop: false, fadeTime: 0.5 }),
    ] });
    const mixer = makeMixer();
    const controller = new AnimationController(makeVrm().vrm, mixer as never, okLoader, random);
    await controller.loadAll('x.json');
    return { controller, mixer };
  }

  it('存在しないアニメーションは警告のみで何もしない', async () => {
    const { controller, mixer } = await loadedController();
    controller.play('unknown');
    expect(mixer.actions[0].play).not.toHaveBeenCalled();
  });

  it('初回はクロスフェードせず reset().play() する', async () => {
    const { controller, mixer } = await loadedController();
    controller.play('idle');
    expect(mixer.actions[0].reset).toHaveBeenCalled();
    expect(mixer.actions[0].play).toHaveBeenCalled();
    expect(mixer.actions[0].fadeIn).not.toHaveBeenCalled();
  });

  it('同じアニメーションの再指定は何もしない', async () => {
    const { controller, mixer } = await loadedController();
    controller.play('idle');
    const callsBefore = (mixer.actions[0].play as ReturnType<typeof vi.fn>).mock.calls.length;
    controller.play('idle');
    expect((mixer.actions[0].play as ReturnType<typeof vi.fn>).mock.calls).toHaveLength(callsBefore);
  });

  it('別のアニメーションへは fadeTime でクロスフェードする', async () => {
    const { controller, mixer } = await loadedController();
    controller.play('idle');
    controller.play('wave');
    expect(mixer.actions[1].fadeIn).toHaveBeenCalledWith(0.5);
    expect(mixer.actions[0].fadeOut).toHaveBeenCalledWith(0.5);
  });

  it('idle クリップが無い場合でも play("idle") で現在のアクションをフェードアウトしてデフォルトポーズへ戻る', async () => {
    stubConfigFetch({ animations: [
      animConfig({ name: 'wave', file: 'wave.vrma', loop: false }),
    ] });
    const mixer = makeMixer();
    const { vrm } = makeVrm();
    const controller = new AnimationController(vrm, mixer as never, okLoader);
    await controller.loadAll('x.json');

    controller.play('wave');
    expect(mixer.actions[0].play).toHaveBeenCalled();

    // Now return to idle (which has no vrma clip)
    controller.play('idle');
    expect(mixer.actions[0].fadeOut).toHaveBeenCalledWith(0.5);
  });
});

describe('アイドルバリエーション', () => {
  async function idleController(random: () => number) {
    stubConfigFetch({
      animations: [animConfig(), animConfig({ name: 'look', file: 'look.vrma', loop: false })],
      config: { idleVariation: { enabled: true, delayMin: 1000, delayMax: 1000, animations: ['look'] } },
    });
    const mixer = makeMixer();
    const controller = new AnimationController(makeVrm().vrm, mixer as never, okLoader, random);
    await controller.loadAll('x.json');
    return { controller, mixer };
  }

  it('遅延後に idle からバリエーションへ切り替える', async () => {
    vi.useFakeTimers();
    try {
      const { controller, mixer } = await idleController(() => 0);
      controller.applyInitialState();
      await vi.advanceTimersByTimeAsync(1000);
      expect(mixer.actions[1].fadeIn).toHaveBeenCalled();
      controller.dispose();
    } finally {
      vi.useRealTimers();
    }
  });

  it('idle 以外を再生中なら発火しない', async () => {
    vi.useFakeTimers();
    try {
      const { controller, mixer } = await idleController(() => 0);
      controller.applyInitialState();
      controller.play('look');
      (mixer.actions[1].fadeIn as ReturnType<typeof vi.fn>).mockClear();
      await vi.advanceTimersByTimeAsync(5000);
      expect(mixer.actions[1].fadeIn).not.toHaveBeenCalled();
      controller.dispose();
    } finally {
      vi.useRealTimers();
    }
  });

  it('enabled:false ではタイマーを張らない', async () => {
    vi.useFakeTimers();
    try {
      stubConfigFetch({
        animations: [animConfig()],
        config: { idleVariation: { enabled: false, animations: ['look'] } },
      });
      const controller = new AnimationController(makeVrm().vrm, makeMixer() as never, okLoader, () => 0);
      await controller.loadAll('x.json');
      controller.applyInitialState();
      expect(vi.getTimerCount()).toBe(0);
    } finally {
      vi.useRealTimers();
    }
  });

  it('animations が空ならタイマーを張らない', async () => {
    vi.useFakeTimers();
    try {
      stubConfigFetch({ animations: [animConfig()], config: { idleVariation: { enabled: true, animations: [] } } });
      const controller = new AnimationController(makeVrm().vrm, makeMixer() as never, okLoader, () => 0);
      await controller.loadAll('x.json');
      controller.applyInitialState();
      expect(vi.getTimerCount()).toBe(0);
    } finally {
      vi.useRealTimers();
    }
  });

  it('resetIdleTimer は既存タイマーを張り直す（多重登録しない）', async () => {
    vi.useFakeTimers();
    try {
      const { controller } = await idleController(() => 0);
      controller.applyInitialState();
      controller.resetIdleTimer();
      controller.resetIdleTimer();
      expect(vi.getTimerCount()).toBe(1);
      controller.dispose();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('update と dispose', () => {
  it('update は mixer に delta を渡す', () => {
    const mixer = makeMixer();
    new AnimationController(makeVrm().vrm, mixer as never, okLoader).update(0.016);
    expect(mixer.update).toHaveBeenCalledWith(0.016);
  });

  it('dispose はリスナーを解除し全アクションを止める', async () => {
    stubConfigFetch({ animations: [animConfig({ loop: false, returnToIdle: true })] });
    const mixer = makeMixer();
    const controller = new AnimationController(makeVrm().vrm, mixer as never, okLoader);
    await controller.loadAll('x.json');

    controller.dispose();
    expect(mixer.removeEventListener).toHaveBeenCalledTimes(1);
    expect(mixer.stopAllAction).toHaveBeenCalled();
  });

  it('dispose はアイドルタイマーを解除する', async () => {
    vi.useFakeTimers();
    try {
      stubConfigFetch({
        animations: [animConfig()],
        config: { idleVariation: { enabled: true, delayMin: 1000, delayMax: 1000, animations: ['look'] } },
      });
      const controller = new AnimationController(makeVrm().vrm, makeMixer() as never, okLoader, () => 0);
      await controller.loadAll('x.json');
      controller.applyInitialState();
      expect(vi.getTimerCount()).toBe(1);

      controller.dispose();
      expect(vi.getTimerCount()).toBe(0);
    } finally {
      vi.useRealTimers();
    }
  });

  it('タイマー未設定でも dispose は落ちない', () => {
    const controller = new AnimationController(makeVrm().vrm, makeMixer() as never, okLoader);
    expect(() => controller.dispose()).not.toThrow();
  });
});

describe('defaultVrmAnimationLoader', () => {
  it('vrmAnimations が空なら null を返す', async () => {
    const loadAsync = vi.fn().mockResolvedValue({ userData: { vrmAnimations: [] } });
    vi.doMock('three/examples/jsm/loaders/GLTFLoader.js', () => ({
      GLTFLoader: vi.fn(function GLTFLoader(this: Record<string, unknown>) {
        this.register = vi.fn((cb: (parser: unknown) => unknown) => cb({}));
        this.loadAsync = loadAsync;
      }),
    }));
    vi.doMock('@pixiv/three-vrm-animation', () => ({
      VRMAnimationLoaderPlugin: vi.fn(),
      createVRMAnimationClip: vi.fn(() => new THREE.AnimationClip('clip', 1, [])),
    }));
    vi.resetModules();

    try {
      const { defaultVrmAnimationLoader } = await import('../../renderer/AnimationController.js');
      await expect(defaultVrmAnimationLoader('idle.vrma', makeVrm().vrm)).resolves.toBeNull();
      expect(loadAsync).toHaveBeenCalledWith('./assets/animations/idle.vrma');
    } finally {
      vi.doUnmock('three/examples/jsm/loaders/GLTFLoader.js');
      vi.doUnmock('@pixiv/three-vrm-animation');
    }
  });

  it('vrmAnimations が undefined なら null を返す', async () => {
    const loadAsync = vi.fn().mockResolvedValue({ userData: {} });
    vi.doMock('three/examples/jsm/loaders/GLTFLoader.js', () => ({
      GLTFLoader: vi.fn(function GLTFLoader(this: Record<string, unknown>) {
        this.register = vi.fn((cb: (parser: unknown) => unknown) => cb({}));
        this.loadAsync = loadAsync;
      }),
    }));
    vi.doMock('@pixiv/three-vrm-animation', () => ({
      VRMAnimationLoaderPlugin: vi.fn(),
      createVRMAnimationClip: vi.fn(() => new THREE.AnimationClip('clip', 1, [])),
    }));
    vi.resetModules();

    try {
      const { defaultVrmAnimationLoader } = await import('../../renderer/AnimationController.js');
      await expect(defaultVrmAnimationLoader('idle.vrma', makeVrm().vrm)).resolves.toBeNull();
      expect(loadAsync).toHaveBeenCalledWith('./assets/animations/idle.vrma');
    } finally {
      vi.doUnmock('three/examples/jsm/loaders/GLTFLoader.js');
      vi.doUnmock('@pixiv/three-vrm-animation');
    }
  });

  it('vrmAnimations があれば AnimationClip を返す', async () => {
    const clip = new THREE.AnimationClip('clip', 1, []);
    const loadAsync = vi.fn().mockResolvedValue({ userData: { vrmAnimations: [{}] } });
    vi.doMock('three/examples/jsm/loaders/GLTFLoader.js', () => ({
      GLTFLoader: vi.fn(function GLTFLoader(this: Record<string, unknown>) {
        this.register = vi.fn((cb: (parser: unknown) => unknown) => cb({}));
        this.loadAsync = loadAsync;
      }),
    }));
    vi.doMock('@pixiv/three-vrm-animation', () => ({
      VRMAnimationLoaderPlugin: vi.fn(),
      createVRMAnimationClip: vi.fn(() => clip),
    }));
    vi.resetModules();

    try {
      const { defaultVrmAnimationLoader } = await import('../../renderer/AnimationController.js');
      await expect(defaultVrmAnimationLoader('idle.vrma', makeVrm().vrm)).resolves.toBe(clip);
      expect(loadAsync).toHaveBeenCalledWith('./assets/animations/idle.vrma');
    } finally {
      vi.doUnmock('three/examples/jsm/loaders/GLTFLoader.js');
      vi.doUnmock('@pixiv/three-vrm-animation');
    }
  });
});
