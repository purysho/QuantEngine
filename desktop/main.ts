import { app, BrowserWindow, Menu, Tray, nativeImage, dialog, ipcMain, shell, safeStorage } from 'electron';
import fs from 'node:fs';
import { readFile, writeFile, mkdir, rename, unlink, appendFile } from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { randomUUID } from 'node:crypto';
import { ConfigStore, USER_SETTINGS, validatePatch } from './config.js';
import { Engine } from './engine.js';
import { Assistant } from './assistant.js';
import { WorkerTransport, type JsonRecord } from './transport.js';
import { MarketService } from './market/service.js';
import { demoFetch, demoSocket, demoPaperFetch, DEMO_KEYS } from './market/demo.js';
import { StrategyDesk } from './market/desk.js';
import { PaperBroker, type PaperFetch } from './market/paper.js';
import { SecretStore } from './market/secrets.js';
import { validSymbol, type Fetch } from './market/alpaca.js';
import type { SocketLike } from './market/stream.js';
import type { Dataset } from './engine.js';

app.setName('Quant Engine');
if (process.platform === 'win32') app.setAppUserModelId('org.quantengine.desktop');
const selfTest = process.argv.includes('--self-test');
// Offline synthetic market for the self-test and screenshots; the window labels it DEMO DATA.
const marketDemo = selfTest || process.argv.includes('--market-demo');
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
let assistant: Assistant;
let configStore: ConfigStore;
let lastSentReport: unknown;
let lastSentRuns: unknown;
let lastSentOptions: unknown;
let market: MarketService;
let desk: StrategyDesk;
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

function pushMarket() {
  if (window && !window.isDestroyed()) window.webContents.send('quant:market', market.snapshot());
}

function pushDesk() {
  if (window && !window.isDestroyed()) window.webContents.send('quant:desk', desk.snapshot());
}

/** Writes a file into the engine's sources folder for the worker (requests over 64 KB travel as files). */
async function stage(extension: 'csv' | 'json', content: string) {
  const folder = path.join(engine.config.dataRoot, 'sources');
  await mkdir(folder, { recursive: true });
  const file = path.join(folder, `staged-${randomUUID()}.${extension}`);
  await writeFile(file, content, 'utf8');
  return file;
}

function pricesCsv(symbols: string[], dates: string[], closes: number[][]) {
  return 'date,' + symbols.join(',') + '\n' + dates.map((date, i) => date + ',' + closes[i].map(v => String(v)).join(',')).join('\n') + '\n';
}

/** Alpaca daily closes → research dataset (stable id per symbol set, so updates replace it). */
async function marketDataset(symbols: string[], years: number, duringCycle: boolean): Promise<Dataset> {
  const { dates, closes } = await market.dailyCloses(symbols, years);
  const file = await stage('csv', pricesCsv(symbols, dates, closes));
  const id = 'alpaca-' + symbols.map(s => s.replace('/', '')).join('-').toLowerCase().slice(0, 60);
  const values = { path: file, dataset_id: id, name: symbols.join(', ') + ' (Alpaca daily)',
    metadata: { source: 'alpaca', symbols, years, units: 'Daily closes adjusted for splits and dividends (all US exchanges)',
      update_frequency: 'Checked hourly while the engine runs, after each US session closes',
      notice: 'Market data from Alpaca; not warranted as to completeness or accuracy.', citation: 'Alpaca Markets Data API' },
    source_url: 'https://data.alpaca.markets/v2/stocks/bars' };
  return duringCycle ? engine.ingestDuringCycle(values) : engine.dataCommand('ingest', values);
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
    market?.stop();
    await engine?.shutdown();
    tray?.destroy();
    exitAllowed = true;
    app.quit();
  })();
  return quitPromise;
}

const DATA_SOURCES = new Set(['ecb', 'us-industries', 'us-indices']);
const CHART_RANGES = new Set(['1D', '5D', '1M', '6M', '1Y', '5Y', 'MAX']);
const OPTION_FIELDS = new Set(['spot', 'strike', 'time', 'rate', 'volatility', 'dividend', 'kind', 'steps', 'paths', 'seed', 'market_price', 'surface_rho', 'surface_eta']);

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
  if (method === 'ask') {
    if (typeof values !== 'string' || values.length > 500) throw new Error('Requests are limited to 500 characters.');
    return { ...(await assistant.handle(values)), snapshot: engine.snapshot() };
  }
  if (method === 'ask-confirm') {
    const { token, accept } = (values ?? {}) as { token?: unknown; accept?: unknown };
    if (typeof token !== 'string' || typeof accept !== 'boolean') throw new Error('Invalid confirmation.');
    return { ...(await assistant.confirm(token, accept)), snapshot: engine.snapshot() };
  }
  if (method === 'learn-now') { await engine.learnNow(); return engine.snapshot(); }
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
  if (method === 'refresh-ecb') { await engine.dataCommand('refresh', { source: 'ecb' }); return engine.snapshot(); }
  if (method === 'refresh-source') {
    if (typeof values !== 'string' || !DATA_SOURCES.has(values)) throw new Error('Unknown data source.');
    await engine.dataCommand('refresh', { source: values });
    return engine.snapshot();
  }
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
  if (method === 'market-state') return market.snapshot();
  if (method === 'market-keys') {
    const { keyId, secret, feed } = (values ?? {}) as JsonRecord;
    await market.setCredentials({ keyId, secret }, feed);
    return market.snapshot();
  }
  if (method === 'market-clear-keys') { await market.clearCredentials(); return market.snapshot(); }
  if (method === 'market-watchlist') { await market.setWatchlist(values); return market.snapshot(); }
  if (method === 'market-chart') {
    const { symbol, range } = (values ?? {}) as JsonRecord;
    if (!CHART_RANGES.has(String(range))) throw new Error('Unknown chart range.');
    return market.chart(symbol, range);
  }
  if (method === 'market-describe') return market.describe(values);
  if (method === 'market-news') return market.news(values);
  if (method === 'market-movers') return market.movers();
  if (method === 'market-search') {
    if (typeof values !== 'string' || values.length > 40) throw new Error('Search text is limited to 40 characters.');
    return market.search(values);
  }
  if (method === 'market-surface') {
    const chain = await market.optionChain(values);
    const dff = market.macro.find(point => point.id === 'DFF')?.value;
    const file = await stage('json', JSON.stringify(chain));
    await engine.fitMarketSurface(file, typeof dff === 'number' ? dff / 100 : 0.04);
    return engine.snapshot();
  }
  if (method === 'market-dataset') {
    const { symbols, years } = (values ?? {}) as JsonRecord;
    if (!Array.isArray(symbols) || symbols.length < 1 || symbols.length > 20 || !symbols.every(validSymbol)) throw new Error('Choose 1–20 valid symbols.');
    if (typeof years !== 'number' || !Number.isInteger(years) || years < 1 || years > 10) throw new Error('Choose 1–10 years of history.');
    if (engine.state.busy || engine.state.continuous) throw new Error('Pause the engine before creating a dataset.');
    await marketDataset(symbols as string[], years, false);
    return engine.snapshot();
  }
  if (method === 'desk-state') return desk.snapshot();
  if (method === 'desk-lab') { await desk.runLab(); return desk.snapshot(); }
  if (method === 'desk-configure') { await desk.configure(values); return desk.snapshot(); }
  if (method === 'desk-refresh') { await desk.refresh(); return desk.snapshot(); }
  if (method === 'desk-propose') { await desk.propose(); return desk.snapshot(); }
  if (method === 'desk-submit') { await desk.submit(values); return desk.snapshot(); }
  if (method === 'desk-kill') {
    if (typeof values !== 'boolean') throw new Error('Kill switch must be on or off.');
    await desk.kill(values);
    return desk.snapshot();
  }
  if (method === 'open-link') {
    // News links open in the user's browser; only https web pages are allowed.
    if (typeof values !== 'string' || values.length > 2000 || !/^https:\/\/[^\s]+$/.test(values)) throw new Error('Only https links can be opened.');
    await shell.openExternal(values);
    return null;
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
  if (settingsPending && ['start', 'run-once', 'import-csv', 'refresh-ecb', 'refresh-source', 'calculate-options', 'learn-now', 'market-dataset', 'market-surface', 'desk-lab', 'desk-propose', 'desk-submit'].includes(method)) {
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
  const asked = await window!.webContents.executeJavaScript(`window.quant.ask('what is my VaR?').then(result => result.reply)`);
  if (!/95% VaR: Gaussian \d/.test(asked)) throw new Error(`Self-test assistant answer was unexpected: ${asked}`);
  const refused = await window!.webContents.executeJavaScript(`window.quant.ask('buy 100 shares now').then(result => result.tier)`);
  if (refused !== 'refused') throw new Error('Self-test assistant did not refuse a trading request.');
  await engine.learnNow();
  const learned = engine.learning as { tasks?: Record<string, { graph: { nodes: unknown[] } }> } | null;
  if (!learned?.tasks?.risk?.graph.nodes.length) throw new Error(`Self-test learning step failed: ${engine.learningError}`);
  // Terminal on the offline demo market: chart, description, market surface (worker) and a market dataset (staging + ingest).
  const terminal = await window!.webContents.executeJavaScript(`(async () => {
    const m = window.quant.market;
    const chart = await m.chart('SPY', '6M');
    const des = await m.describe('AAPL');
    const surfaced = await m.surface('SPY');
    const made = await m.dataset(['SPY', 'QQQ'], 2);
    return { bars: chart.bars.length, vol20: des.vol20, expiries: surfaced.marketSurface.expiries.length,
      datasetRows: made.datasets.find(d => d.id === 'alpaca-spy-qqq')?.rows ?? 0,
      shown: !document.getElementById('page-terminal').classList.contains('hidden'), demo: (await m.state()).demo };
  })()`);
  if (terminal.bars < 100 || !(terminal.vol20 > 0) || terminal.expiries < 2 || terminal.datasetRows < 400 || !terminal.shown || !terminal.demo) {
    throw new Error('Self-test terminal check failed: ' + JSON.stringify(terminal));
  }
  // Stage 3 loop on the demo paper account: enable, compute orders, two-step approval, submit, reconcile.
  const paper = await window!.webContents.executeJavaScript(`(async () => {
    const d = window.quant.desk;
    const base = await d.state();
    await d.configure({ ...base.settings, enabled: true, strategy: 'sectors' });
    const proposed = await d.propose();
    const submitted = await d.submit(proposed.proposal.id);
    const again = await d.refresh();
    return { orders: proposed.proposal.orders.length, positions: submitted.positions.length,
      reconciled: again.journal.some(e => e.type === 'reconcile' && e.ok === true) };
  })()`);
  if (paper.orders < 1 || paper.positions < 1 || !paper.reconciled) throw new Error('Self-test paper loop failed: ' + JSON.stringify(paper));
  console.log('QUANT_SELF_TEST_OK ' + JSON.stringify({ ...ready, option, assistant: asked.slice(0, 80), learnedModels: learned.tasks.risk.graph.nodes.length, completed: engine.state.completed, terminal, paper,
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
    if (selfTest) { config.paths = 5000; config.resumeOnLaunch = false; config.startAtLogin = false; config.learnBudgetSeconds = 8; }
    let python = '';
    try { python = pythonPath(); } catch (error) { config.lastError = (error as Error).message; }
    const transport = new WorkerTransport(python, path.join(app.getAppPath(), 'workers/quant_worker.py'),
      () => engine.config.dataRoot, () => engine.config.lowCpu);
    engine = new Engine(config, transport, async next => { await configStore.update(next); });
    engine.onChange = pushState;
    // Every assistant request and outcome is appended to a local, human-readable action log.
    assistant = new Assistant(engine, async entry => {
      await mkdir(engine.config.dataRoot, { recursive: true });
      await appendFile(path.join(engine.config.dataRoot, 'assistant-log.jsonl'), JSON.stringify(entry) + '\n', 'utf8');
    }, () => engine.config.assistantEndpoint ? { endpoint: engine.config.assistantEndpoint, model: engine.config.assistantModel } : null);
    try { await engine.initialize(); } catch (error) { showError(error); engine.state.phase = 'error'; }
    // Market data: keys are encrypted by Windows (DPAPI) and stay in this process.
    market = marketDemo
      ? new MarketService(path.join(app.getPath('userData'), 'demo-market'), new SecretStore(path.join(app.getPath('userData'), 'demo-market', 'keys.json'), safeStorage), demoFetch(), demoSocket())
      : new MarketService(app.getPath('userData'), new SecretStore(path.join(app.getPath('userData'), 'alpaca-keys.json'), safeStorage),
        globalThis.fetch as unknown as Fetch, url => new WebSocket(url) as unknown as SocketLike);
    market.onChange = pushMarket;
    await market.load();
    if (marketDemo) market.useDemo(DEMO_KEYS);
    // Paper trading: only Alpaca's paper host is reachable (see market/paper.ts); demo mode uses an in-memory account.
    const paperFetch = (marketDemo ? demoPaperFetch() : globalThis.fetch) as unknown as PaperFetch;
    desk = new StrategyDesk(path.join(app.getPath('userData'), marketDemo ? 'demo-market/paper.json' : 'paper.json'),
      new PaperBroker(() => market.credentials, paperFetch), market, {
        dataRoot: () => engine.config.dataRoot,
        runTask: (stage, command, values) => engine.runTask(stage, command, values),
        stage,
        riskFreeAnnual: () => { const dff = market.macro.find(point => point.id === 'DFF')?.value; return typeof dff === 'number' ? dff / 100 : 0.04; },
      });
    desk.onChange = pushDesk;
    await desk.load();
    engine.refreshExternal = async dataset => {
      const meta = dataset.metadata as { symbols?: unknown; years?: unknown } | undefined;
      if (!market.credentials || !Array.isArray(meta?.symbols) || !meta.symbols.every(validSymbol) || typeof meta.years !== 'number') return null;
      return marketDataset(meta.symbols as string[], meta.years, true);
    };
    void market.start();
    void desk.loadSavedLab().then(() => { pushDesk(); if (market.credentials && desk.settings.enabled) void desk.refresh(); });
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
      pushMarket();
      pushDesk();
      if (selfTest) void nativeSelfTest().catch(async error => { console.error('QUANT_SELF_TEST_FAILED', error); await engine.pause(); quitting = true; app.exit(1); });
    });
    if (!selfTest && config.resumeOnLaunch) void engine.start().catch(showError);
    pushState();
  }).catch(error => { console.error('Quant Engine startup failed:', error); quitting = true; app.exit(1); });
}
