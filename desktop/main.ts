import { app, BrowserWindow, Menu, Tray, nativeImage, dialog, ipcMain, shell } from 'electron';
import fs from 'node:fs';
import { readFile, writeFile, mkdir, rename, unlink } from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { randomUUID } from 'node:crypto';
import { ConfigStore, USER_SETTINGS, validatePatch } from './config.js';
import { Engine } from './engine.js';
import { WorkerTransport, type JsonRecord } from './transport.js';

app.setName('Quant Engine');
if (process.platform === 'win32') app.setAppUserModelId('org.quantengine.desktop');
const selfTest = process.argv.includes('--self-test');
const selfTestRoot = selfTest ? fs.mkdtempSync(path.join(os.tmpdir(), 'quant-desktop-test-')) : null;
app.setPath('userData', selfTestRoot ? path.join(selfTestRoot, 'settings') : path.join(app.getPath('appData'), 'QuantEngine'));
if (selfTestRoot) fs.mkdirSync(app.getPath('userData'), { recursive: true });
const gotLock = selfTest || app.requestSingleInstanceLock();
let window: BrowserWindow | null = null;
let tray: Tray | null = null;
let quitting = false;
let exitAllowed = false;
let quitPromise: Promise<void> | null = null;
let engine: Engine;
let configStore: ConfigStore;
let lastSentReport: unknown;
let lastSentRuns: unknown;
let lastSentOptions: unknown;
let settingsQueue: Promise<unknown> = Promise.resolve();
let settingsPending = 0;

function pythonPath() {
  if (app.isPackaged) {
    const executable = path.join(process.resourcesPath, 'quant-python', process.platform === 'win32' ? 'python.exe' : 'bin/python3');
    if (!fs.existsSync(executable)) throw new Error('The bundled numerical runtime is missing. Reinstall Quant Engine.');
    return executable;
  }
  return process.env.QUANT_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
}

function pushState() {
  if (window && !window.isDestroyed()) {
    const snapshot: JsonRecord = engine.snapshot();
    if (lastSentReport === snapshot.report) delete snapshot.report;
    else lastSentReport = snapshot.report;
    if (lastSentRuns === snapshot.runs) delete snapshot.runs;
    else lastSentRuns = snapshot.runs;
    if (lastSentOptions === snapshot.options) delete snapshot.options;
    else lastSentOptions = snapshot.options;
    window.webContents.send('quant:state', snapshot);
  }
  if (tray) {
    tray.setToolTip(`Quant Engine — ${engine.state.busy ? 'computing' : engine.state.phase}`);
    tray.setContextMenu(Menu.buildFromTemplate([
      { label: 'Open research monitor', click: showWindow },
      { label: engine.state.continuous ? 'Pause engine' : 'Start engine', enabled: !engine.state.busy || engine.state.continuous,
        click: () => { void dispatchCommand(engine.state.continuous ? 'pause' : 'start').catch(showError); } },
      { type: 'separator' }, { label: 'Quit Quant Engine', click: () => { void quit(); } },
    ]));
  }
}

function showError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error);
  engine.state.lastError = message;
  pushState();
}

function createWindow(hidden = false) {
  window = new BrowserWindow({
    width: 1440, height: 960, minWidth: 1080, minHeight: 740, show: false,
    backgroundColor: '#0b131d', title: 'Quant Engine', icon: path.join(app.getAppPath(), 'assets/app.png'),
    autoHideMenuBar: true,
    webPreferences: { preload: path.join(app.getAppPath(), 'dist/preload.cjs'),
      contextIsolation: true, sandbox: true, nodeIntegration: false, webSecurity: true },
  });
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  window.webContents.on('will-navigate', event => event.preventDefault());
  window.webContents.on('will-attach-webview', event => event.preventDefault());
  window.once('ready-to-show', () => { if (!hidden) window?.show(); });
  window.on('close', event => {
    if (exitAllowed) return;
    event.preventDefault();
    if (!quitting && !selfTest && tray) window?.hide();
    else void quit();
  });
  window.on('closed', () => { window = null; });
  lastSentReport = undefined;
  lastSentRuns = undefined;
  lastSentOptions = undefined;
  void window.loadFile(path.join(app.getAppPath(), 'app/index.html'));
  return window;
}

function showWindow() {
  if (!window || window.isDestroyed()) createWindow();
  window?.show();
  window?.focus();
}

function quit(): Promise<void> {
  if (quitPromise) return quitPromise;
  quitting = true;
  quitPromise = (async () => {
    await settingsQueue.catch(() => {});
    await engine?.shutdown();
    tray?.destroy();
    exitAllowed = true;
    app.quit();
  })();
  return quitPromise;
}

const OPTION_FIELDS = new Set(['spot', 'strike', 'time', 'rate', 'volatility', 'dividend', 'kind', 'steps', 'paths', 'seed', 'market_price']);

/** Shape check only; the numerical worker performs the authoritative range validation. */
function validateOptions(values: unknown): JsonRecord {
  if (!values || typeof values !== 'object' || Array.isArray(values)) throw new Error('Option inputs must be an object.');
  const result: JsonRecord = {};
  for (const [key, value] of Object.entries(values as JsonRecord)) {
    if (!OPTION_FIELDS.has(key)) throw new Error(`Unknown option input: ${key}`);
    if (key === 'kind') { if (value !== 'call' && value !== 'put') throw new Error('Option type must be call or put.'); }
    else if (key === 'market_price' && value === null) continue;
    else if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error(`Option input ${key} must be a finite number.`);
    result[key] = value;
  }
  return result;
}

function checkedRun(id: unknown) {
  if (typeof id !== 'string' || !/^[a-zA-Z0-9_-]{1,80}$/.test(id)) throw new Error('Invalid run identifier.');
  const run = engine.runs.find(value => value.id === id && value.status === 'completed');
  if (!run || typeof run.report_path !== 'string') throw new Error('Completed report not found in the visible history.');
  if (path.dirname(path.resolve(run.report_path)) !== path.resolve(engine.config.dataRoot, 'reports')) {
    throw new Error('The report is outside this engine’s storage folder.');
  }
  return run;
}

async function command(method: string, values?: unknown): Promise<unknown> {
  if (method === 'state') return engine.snapshot();
  if (method === 'start') { await engine.start(); return engine.snapshot(); }
  if (method === 'pause') { await engine.pause(); return engine.snapshot(); }
  if (method === 'run-once') { await engine.runOnce(); return engine.snapshot(); }
  if (method === 'calculate-options') { await engine.calculateOptions(validateOptions(values)); return engine.snapshot(); }
  if (method === 'configure') {
    const patch = validatePatch(values);
    for (const key of Object.keys(patch)) if (!USER_SETTINGS.has(key)) throw new Error(`This setting is managed by the desktop: ${key}`);
    if (patch.datasetId && !engine.datasets.some(dataset => dataset.id === patch.datasetId)) throw new Error('Choose an available dataset.');
    await engine.configure(patch);
    if (process.platform === 'win32' && patch.startAtLogin !== undefined) {
      app.setLoginItemSettings({ openAtLogin: patch.startAtLogin, path: process.execPath, args: ['--background'] });
    }
    return engine.snapshot();
  }
  if (method === 'choose-root') {
    if (engine.state.busy || engine.state.continuous) throw new Error('Pause the engine before choosing a storage folder.');
    const selected = await dialog.showOpenDialog(window!, { title: 'Choose Quant Engine storage folder',
      defaultPath: engine.config.dataRoot, properties: ['openDirectory', 'createDirectory'] });
    if (selected.canceled || !selected.filePaths[0]) return null;
    const previous = { dataRoot: engine.config.dataRoot, datasetId: engine.config.datasetId };
    try {
      await engine.configure({ dataRoot: selected.filePaths[0], datasetId: 'sample' });
      engine.lastReport = null; engine.lastReportPath = null;
      await engine.initialize();
    } catch (error) { await engine.configure(previous); await engine.initialize().catch(() => {}); throw error; }
    return engine.snapshot();
  }
  if (method === 'import-csv') {
    if (engine.state.busy || engine.state.continuous) throw new Error('Pause the engine before importing a dataset.');
    const selected = await dialog.showOpenDialog(window!, { title: 'Import chronological wide-format prices',
      filters: [{ name: 'Price CSV', extensions: ['csv'] }], properties: ['openFile'] });
    if (selected.canceled || !selected.filePaths[0]) return null;
    await engine.dataCommand('import', { path: selected.filePaths[0] });
    return engine.snapshot();
  }
  if (method === 'refresh-ecb') { await engine.dataCommand('refresh'); return engine.snapshot(); }
  if (method === 'open-run') {
    const run = checkedRun(values);
    const report = JSON.parse(await readFile(run.report_path as string, 'utf8')) as JsonRecord;
    engine.lastReport = report;
    engine.lastReportPath = run.report_path as string;
    pushState();
    return engine.snapshot();
  }
  if (method === 'export-report') {
    if (!engine.lastReport || !engine.lastReportPath) throw new Error('Run an analysis or open a completed report first.');
    const report = engine.lastReport;
    const run = report.run as { id: string };
    const selected = await dialog.showSaveDialog(window!, { title: 'Export completed research report',
      defaultPath: path.join(app.getPath('documents'), `quant-${run.id}.json`),
      filters: [{ name: 'Complete reproducible report', extensions: ['json'] }, { name: 'Equity curves', extensions: ['csv'] }] });
    if (selected.canceled || !selected.filePath) return null;
    let content: string;
    if (path.extname(selected.filePath).toLowerCase() === '.csv') {
      const curve = report.curve as Array<{ date: string; strategy: number; gross: number; equal_weight: number; cash: number }>;
      content = 'date,strategy_net,strategy_gross,equal_weight_net,cash\n' +
        curve.map(point => [point.date, point.strategy, point.gross, point.equal_weight, point.cash].join(',')).join('\n') + '\n';
    } else content = JSON.stringify(report, null, 2) + '\n';
    const temporary = selected.filePath + '.' + randomUUID() + '.tmp';
    try { await writeFile(temporary, content, 'utf8'); await rename(temporary, selected.filePath); }
    finally { await unlink(temporary).catch(() => {}); }
    return { path: selected.filePath };
  }
  if (method === 'open-data-folder') { await mkdir(engine.config.dataRoot, { recursive: true }); await shell.openPath(engine.config.dataRoot); return null; }
  throw new Error('Unsupported desktop command.');
}

function dispatchCommand(method: string, values?: unknown): Promise<unknown> {
  if (quitting && !['state', 'pause'].includes(method)) return Promise.reject(new Error('Quant Engine is shutting down.'));
  if (method === 'configure' || method === 'choose-root') {
    settingsPending++;
    const pending = settingsQueue.catch(() => {}).then(() => command(method, values)).finally(() => { settingsPending--; });
    settingsQueue = pending;
    return pending;
  }
  if (settingsPending && ['start', 'run-once', 'import-csv', 'refresh-ecb', 'calculate-options'].includes(method)) {
    return Promise.reject(new Error('Settings or storage are still being saved. Wait before starting another operation.'));
  }
  return command(method, values);
}

async function nativeSelfTest() {
  const ready = await window!.webContents.executeJavaScript(`(async () => {
    const state = await window.quant.getState();
    return { bridge: typeof window.quant.runOnce === 'function', rows: state.datasets[0].rows,
      title: document.title, nodeUnavailable: typeof require === 'undefined' };
  })()`);
  if (!ready.bridge || ready.rows < 40 || !ready.nodeUnavailable || ready.title !== 'Quant Engine') throw new Error('Renderer/preload health check failed.');
  await engine.runOnce();
  if (!engine.lastReport || engine.state.lastError) throw new Error(engine.state.lastError || 'Self-test numerical report is missing.');
  // Exercise the sandboxed bridge end to end with a published reference contract (Hull: 4.7594).
  const option = await window!.webContents.executeJavaScript(`window.quant.calculateOptions({ spot: 42, strike: 40, time: 0.5,
    rate: 0.1, volatility: 0.2, paths: 20000 }).then(state => state.options.black_scholes.price)`);
  if (Math.abs(option - 4.7594) > 1e-4) throw new Error(`Self-test option price ${option} differs from the reference.`);
  console.log('QUANT_SELF_TEST_OK ' + JSON.stringify({ ...ready, option, completed: engine.state.completed,
    runtime: engine.runtime, report: engine.lastReportPath }));
  await quit();
}

if (!gotLock) app.quit();
else {
  app.on('second-instance', showWindow);
  app.on('activate', showWindow);
  app.on('window-all-closed', () => { if (!tray) void quit(); });
  app.on('before-quit', event => {
    if (exitAllowed) return;
    event.preventDefault();
    void quit();
  });
  void app.whenReady().then(async () => {
    const defaultRoot = selfTestRoot ? path.join(selfTestRoot, 'data') :
      process.platform === 'win32' ? 'D:\\Quant-Engine' : path.join(app.getPath('documents'), 'Quant-Engine');
    configStore = new ConfigStore(path.join(app.getPath('userData'), 'settings.json'), defaultRoot);
    const config = await configStore.load();
    if (selfTest) { config.paths = 5000; config.resumeOnLaunch = false; config.startAtLogin = false; }
    let python = '';
    try { python = pythonPath(); } catch (error) { config.lastError = (error as Error).message; }
    const transport = new WorkerTransport(python, path.join(app.getAppPath(), 'workers/quant_worker.py'),
      () => engine.config.dataRoot, () => engine.config.lowCpu);
    engine = new Engine(config, transport, async next => { await configStore.update(next); });
    engine.onChange = pushState;
    try { await engine.initialize(); } catch (error) { showError(error); engine.state.phase = 'error'; }
    if (!selfTest) {
      const image = nativeImage.createFromPath(path.join(app.getAppPath(), 'assets/app.png'));
      if (!image.isEmpty()) {
        tray = new Tray(image.resize({ width: 24, height: 24 }));
        tray.on('double-click', showWindow);
      }
    }
    Menu.setApplicationMenu(null);
    ipcMain.handle('quant:command', async (event, method: unknown, values: unknown) => {
      try {
        if (!window || event.sender.id !== window.webContents.id || event.senderFrame !== window.webContents.mainFrame) {
          throw new Error('Desktop commands require the trusted main application window.');
        }
        if (typeof method !== 'string') throw new Error('Invalid desktop command.');
        return { ok: true, value: await dispatchCommand(method, values) };
      } catch (error) { return { ok: false, error: error instanceof Error ? error.message : String(error) }; }
    });
    const browserWindow = createWindow(selfTest || process.argv.includes('--background'));
    browserWindow.webContents.once('did-finish-load', () => {
      pushState();
      if (selfTest) void nativeSelfTest().catch(async error => { console.error('QUANT_SELF_TEST_FAILED', error); await engine.pause(); quitting = true; app.exit(1); });
    });
    if (!selfTest && config.resumeOnLaunch) void engine.start().catch(showError);
    pushState();
  }).catch(error => { console.error('Quant Engine startup failed:', error); quitting = true; app.exit(1); });
}
