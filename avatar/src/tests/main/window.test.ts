import { describe, it, expect, vi, beforeEach } from 'vitest';

class FakeWindow {
  static instances: FakeWindow[] = [];
  static lastOptions: Record<string, unknown> = {};

  listeners = new Map<string, Array<(...args: unknown[]) => void>>();
  webContents = { on: vi.fn(), send: vi.fn() };
  loadFile = vi.fn();
  getPosition = vi.fn(() => [10, 20]);
  getSize = vi.fn(() => [800, 600]);
  setPosition = vi.fn();
  setSize = vi.fn();
  setBounds = vi.fn();
  setIgnoreMouseEvents = vi.fn();

  constructor(options: Record<string, unknown>) {
    FakeWindow.lastOptions = options;
    FakeWindow.instances.push(this);
  }

  on(event: string, cb: (...args: unknown[]) => void) {
    const list = this.listeners.get(event) ?? [];
    list.push(cb);
    this.listeners.set(event, list);
  }

  once(event: string, cb: (...args: unknown[]) => void) {
    const wrapper = (...args: unknown[]) => {
      const list = this.listeners.get(event) ?? [];
      const idx = list.indexOf(wrapper);
      if (idx !== -1) list.splice(idx, 1);
      cb(...args);
    };
    this.on(event, wrapper);
  }

  emit(event: string, ...args: unknown[]) {
    for (const cb of [...(this.listeners.get(event) ?? [])]) cb(...args);
  }

  // 実際の BrowserWindow.close() は非同期: 'closed' は後続のマイクロタスクで発火する
  close = vi.fn(() => {
    queueMicrotask(() => this.emit('closed'));
  });
}

function flushMicrotasks(): Promise<void> {
  return new Promise((resolve) => queueMicrotask(resolve));
}

vi.mock('electron', () => ({
  BrowserWindow: vi.fn(function (options: Record<string, unknown>) {
    return new FakeWindow(options);
  }),
}));

async function loadWindowModule() {
  vi.resetModules();
  FakeWindow.instances = [];
  FakeWindow.lastOptions = {};
  return import('../../main/window.js');
}

beforeEach(() => {
  vi.spyOn(console, 'log').mockImplementation(() => {});
});

describe('createWindow', () => {
  it('初期状態は Normal モード（透過・フレームなし・最前面）', async () => {
    const mod = await loadWindowModule();
    mod.createWindow();
    expect(FakeWindow.lastOptions).toMatchObject({
      transparent: true,
      frame: false,
      alwaysOnTop: true,
      skipTaskbar: true,
      backgroundColor: '#00000000',
    });
  });

  it('preload と contextIsolation を設定する', async () => {
    const mod = await loadWindowModule();
    mod.createWindow();
    expect(FakeWindow.lastOptions.webPreferences).toMatchObject({
      nodeIntegration: false,
      contextIsolation: true,
    });
  });

  it('VRM.html を読み込む', async () => {
    const mod = await loadWindowModule();
    mod.createWindow();
    expect(FakeWindow.instances[0].loadFile).toHaveBeenCalledWith(expect.stringContaining('VRM.html'));
  });

  it('getMainWindow が生成したウィンドウを返す', async () => {
    const mod = await loadWindowModule();
    mod.createWindow();
    expect(mod.getMainWindow()).toBe(FakeWindow.instances[0]);
  });

  it('closed イベントで参照が null になる', async () => {
    const mod = await loadWindowModule();
    mod.createWindow();
    FakeWindow.instances[0].emit('closed');
    expect(mod.getMainWindow()).toBeNull();
  });
});

describe('before-input-event によるモード切替', () => {
  function inputHandler(win: FakeWindow) {
    return win.webContents.on.mock.calls.find((c) => c[0] === 'before-input-event')![1] as
      (event: { preventDefault: () => void }, input: Record<string, unknown>) => void;
  }

  it('Ctrl+, の keyDown でモードを切り替える', async () => {
    const mod = await loadWindowModule();
    mod.createWindow();
    const event = { preventDefault: vi.fn() };
    inputHandler(FakeWindow.instances[0])(event, { type: 'keyDown', key: ',', control: true });
    expect(event.preventDefault).toHaveBeenCalled();
    await flushMicrotasks();
    expect(FakeWindow.instances).toHaveLength(2);
  });

  it('Ctrl なしの , では切り替えない', async () => {
    const mod = await loadWindowModule();
    mod.createWindow();
    const event = { preventDefault: vi.fn() };
    inputHandler(FakeWindow.instances[0])(event, { type: 'keyDown', key: ',', control: false });
    expect(event.preventDefault).not.toHaveBeenCalled();
    expect(FakeWindow.instances).toHaveLength(1);
  });

  it('keyUp では切り替えない', async () => {
    const mod = await loadWindowModule();
    mod.createWindow();
    const event = { preventDefault: vi.fn() };
    inputHandler(FakeWindow.instances[0])(event, { type: 'keyUp', key: ',', control: true });
    expect(FakeWindow.instances).toHaveLength(1);
  });

  it('別のキーでは切り替えない', async () => {
    const mod = await loadWindowModule();
    mod.createWindow();
    const event = { preventDefault: vi.fn() };
    inputHandler(FakeWindow.instances[0])(event, { type: 'keyDown', key: 'a', control: true });
    expect(FakeWindow.instances).toHaveLength(1);
  });

  it('Ctrl+Alt+I força mouse events de emergência', async () => {
    const mod = await loadWindowModule();
    mod.createWindow();
    const win = FakeWindow.instances[0];
    const event = { preventDefault: vi.fn() };
    inputHandler(win)(event, { type: 'keyDown', key: 'i', control: true, alt: true });
    expect(event.preventDefault).toHaveBeenCalled();
    expect(win.setIgnoreMouseEvents).toHaveBeenCalledWith(false);
  });

  it('Ctrl+Home envia evento locomotion:reset-to-center para o renderer', async () => {
    const mod = await loadWindowModule();
    mod.createWindow();
    const win = FakeWindow.instances[0];
    const event = { preventDefault: vi.fn() };
    inputHandler(win)(event, { type: 'keyDown', key: 'Home', control: true });
    expect(event.preventDefault).toHaveBeenCalled();
    expect(win.webContents.send).toHaveBeenCalledWith('locomotion:reset-to-center');
  });

  it('Ctrl+0 envia evento preset:bottom-left-waist-up para o renderer', async () => {
    const mod = await loadWindowModule();
    mod.createWindow();
    const win = FakeWindow.instances[0];
    const event = { preventDefault: vi.fn() };
    inputHandler(win)(event, { type: 'keyDown', key: '0', control: true });
    expect(event.preventDefault).toHaveBeenCalled();
    expect(win.webContents.send).toHaveBeenCalledWith('preset:bottom-left-waist-up');
  });
});

describe('updateCharacterBounds', () => {
  it('aceita minX, maxX, minY, maxY diretamente', async () => {
    const mod = await loadWindowModule();
    expect(() => mod.updateCharacterBounds({ minX: 100, maxX: 400, minY: 200, maxY: 600 })).not.toThrow();
  });

  it('aceita x, y, width, height', async () => {
    const mod = await loadWindowModule();
    expect(() => mod.updateCharacterBounds({ x: 300, y: 400, width: 200, height: 400 })).not.toThrow();
  });
});

describe('toggleWindowMode', () => {
  it('ウィンドウが無いときは何もしない', async () => {
    const mod = await loadWindowModule();
    expect(() => mod.toggleWindowMode()).not.toThrow();
    expect(FakeWindow.instances).toHaveLength(0);
  });

  it('Settings モードでは不透過・フレームあり・最前面解除で作り直す', async () => {
    const mod = await loadWindowModule();
    mod.createWindow();
    mod.toggleWindowMode();
    await flushMicrotasks();
    expect(FakeWindow.lastOptions).toMatchObject({
      transparent: false,
      frame: true,
      alwaysOnTop: false,
      skipTaskbar: false,
      backgroundColor: '#222222',
    });
  });

  it('切替前の位置とサイズを新しいウィンドウへ引き継ぐ', async () => {
    const mod = await loadWindowModule();
    mod.createWindow();
    mod.toggleWindowMode();
    await flushMicrotasks();
    const created = FakeWindow.instances[1];
    expect(created.setPosition).toHaveBeenCalledWith(10, 20);
    expect(created.setSize).toHaveBeenCalledWith(800, 600);
  });

  it('close() 直後は isRecreating が true、closed 発火後に false へ戻る', async () => {
    const mod = await loadWindowModule();
    mod.createWindow();
    expect(mod.isRecreating()).toBe(false);
    mod.toggleWindowMode();
    expect(mod.isRecreating()).toBe(true);
    await flushMicrotasks();
    expect(mod.isRecreating()).toBe(false);
  });

  it('2 回切り替えると Normal モードに戻る', async () => {
    const mod = await loadWindowModule();
    mod.createWindow();
    mod.toggleWindowMode();
    await flushMicrotasks();
    mod.toggleWindowMode();
    await flushMicrotasks();
    expect(FakeWindow.lastOptions).toMatchObject({ transparent: true, frame: false });
  });
});
