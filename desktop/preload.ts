import { contextBridge, ipcRenderer } from 'electron';

async function call(method: string, values?: unknown) {
  const response = await ipcRenderer.invoke('quant:command', method, values);
  if (!response.ok) throw new Error(response.error || 'Desktop operation failed.');
  return response.value;
}

contextBridge.exposeInMainWorld('quant', Object.freeze({
  getState: () => call('state'),
  start: () => call('start'),
  pause: () => call('pause'),
  runOnce: () => call('run-once'),
  calculateOptions: (values: unknown) => call('calculate-options', values),
  ask: (text: string) => call('ask', text),
  learnNow: () => call('learn-now'),
  confirmAsk: (token: string, accept: boolean) => call('ask-confirm', { token, accept }),
  configure: (values: unknown) => call('configure', values),
  chooseRoot: () => call('choose-root'),
  importCSV: () => call('import-csv'),
  refreshECB: () => call('refresh-ecb'),
  refreshSource: (source: string) => call('refresh-source', source),
  openRun: (id: string) => call('open-run', id),
  exportReport: () => call('export-report'),
  openDataFolder: () => call('open-data-folder'),
  desk: Object.freeze({
    state: () => call('desk-state'),
    runLab: () => call('desk-lab'),
    configure: (settings: unknown) => call('desk-configure', settings),
    refresh: () => call('desk-refresh'),
    daily: () => call('desk-daily'),
    exportProgress: () => call('desk-export'),
    propose: () => call('desk-propose'),
    submit: (proposalId: string) => call('desk-submit', proposalId),
    kill: (on: boolean) => call('desk-kill', on),
    onUpdate: (callback: (state: unknown) => void) => {
      if (typeof callback !== 'function') throw new Error('A desk callback is required.');
      const listener = (_event: unknown, state: unknown) => callback(state);
      ipcRenderer.on('quant:desk', listener);
      return () => ipcRenderer.removeListener('quant:desk', listener);
    },
  }),
  market: Object.freeze({
    state: () => call('market-state'),
    setKeys: (keyId: string, secret: string, feed: string) => call('market-keys', { keyId, secret, feed }),
    clearKeys: () => call('market-clear-keys'),
    setWatchlist: (symbols: string[]) => call('market-watchlist', symbols),
    chart: (symbol: string, range: string) => call('market-chart', { symbol, range }),
    describe: (symbol: string) => call('market-describe', symbol),
    news: (symbol?: string) => call('market-news', symbol ?? null),
    movers: () => call('market-movers'),
    search: (text: string) => call('market-search', text),
    surface: (symbol: string) => call('market-surface', symbol),
    dataset: (symbols: string[], years: number) => call('market-dataset', { symbols, years }),
    openLink: (url: string) => call('open-link', url),
    onUpdate: (callback: (state: unknown) => void) => {
      if (typeof callback !== 'function') throw new Error('A market callback is required.');
      const listener = (_event: unknown, state: unknown) => callback(state);
      ipcRenderer.on('quant:market', listener);
      return () => ipcRenderer.removeListener('quant:market', listener);
    },
  }),
  onState: (callback: (state: unknown) => void) => {
    if (typeof callback !== 'function') throw new Error('A state callback is required.');
    const listener = (_event: unknown, state: unknown) => callback(state);
    ipcRenderer.on('quant:state', listener);
    return () => ipcRenderer.removeListener('quant:state', listener);
  },
}));
