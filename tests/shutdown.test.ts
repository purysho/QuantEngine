import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { createRequire } from 'node:module';
import path from 'node:path';
import os from 'node:os';
import vm from 'node:vm';
import { build } from 'esbuild';

// Exercise the actual Electron main lifecycle with its unavoidable native app
// dependency replaced by an event emitter implementing before-quit prevention.
test('every repeated native quit stays blocked until settings and owned worker shutdown finish', async () => {
  const compiled = await build({ entryPoints: ['desktop/main.ts'], bundle: true, write: false,
    platform: 'node', format: 'cjs', target: 'node22', external: ['electron'] });
  const order: string[] = [];
  class NativeApp extends EventEmitter {
    exits = 0;
    setName() {}
    setAppUserModelId() {}
    setPath() {}
    getPath() { return os.tmpdir(); }
    getAppPath() { return path.resolve('.'); }
    requestSingleInstanceLock() { return true; }
    whenReady() { return new Promise<void>(() => {}); }
    quit() {
      let prevented = false;
      this.emit('before-quit', { preventDefault() { prevented = true; } });
      if (!prevented) { this.exits++; order.push('exit'); }
    }
  }
  class NativeWindow extends EventEmitter {
    hidden = 0;
    closed = 0;
    webContents = Object.assign(new EventEmitter(), { setWindowOpenHandler() {} });
    loadFile() { return Promise.resolve(); }
    hide() { this.hidden++; }
    requestClose() {
      let prevented = false;
      this.emit('close', { preventDefault() { prevented = true; } });
      if (!prevented) this.closed++;
      return prevented;
    }
  }
  const native = new NativeApp();
  let finishSettings!: () => void, finishWorker!: () => void;
  const settingsBarrier = new Promise<void>(resolve => { finishSettings = resolve; });
  const workerBarrier = new Promise<void>(resolve => { finishWorker = resolve; });
  let shutdownCalls = 0;
  const fixtureEngine = { shutdown: async () => { shutdownCalls++; order.push('shutdown'); await workerBarrier; order.push('worker-closed'); } };
  const fixtureTray = { destroy: () => { order.push('tray-destroyed'); } };
  const nativeRequire = createRequire(path.resolve('package.json'));
  const sandbox = vm.createContext({
    require: (name: string) => name === 'electron' ? { app: native, BrowserWindow: NativeWindow } : nativeRequire(name),
    process: { argv: ['node', 'quant-engine'], platform: process.platform, env: process.env, execPath: process.execPath },
    Buffer, console, setTimeout, clearTimeout,
    settingsBarrier, fixtureEngine, fixtureTray,
  });
  vm.runInContext(compiled.outputFiles[0].text, sandbox);
  vm.runInContext('settingsQueue = settingsBarrier; engine = fixtureEngine; tray = fixtureTray;', sandbox);
  const browser = vm.runInContext('createWindow()', sandbox) as NativeWindow;
  assert.equal(browser.requestClose(), true);
  assert.equal(browser.hidden, 1, 'Ordinary close keeps the application in its tray');
  assert.equal(shutdownCalls, 0);

  native.quit();
  native.quit();
  assert.equal(browser.requestClose(), true, 'Window close cannot bypass an in-progress shutdown');
  assert.equal(native.exits, 0, 'A repeated before-quit must not bypass an accepted settings save');
  assert.equal(shutdownCalls, 0);
  finishSettings();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(shutdownCalls, 1);
  native.quit();
  native.quit();
  assert.equal(native.exits, 0, 'Every quit remains prevented while the owned worker is stopping');
  assert.equal(shutdownCalls, 1, 'Repeated requests share a single shutdown');
  finishWorker();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(native.exits, 1);
  assert.equal(browser.requestClose(), false, 'Window exit is permitted only after the owned worker closes');
  assert.equal(browser.closed, 1);
  assert.deepEqual(order, ['shutdown', 'worker-closed', 'tray-destroyed', 'exit']);
});
