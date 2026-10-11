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
  configure: (values: unknown) => call('configure', values),
  chooseRoot: () => call('choose-root'),
  importCSV: () => call('import-csv'),
  refreshECB: () => call('refresh-ecb'),
  openRun: (id: string) => call('open-run', id),
  exportReport: () => call('export-report'),
  openDataFolder: () => call('open-data-folder'),
  onState: (callback: (state: unknown) => void) => {
    if (typeof callback !== 'function') throw new Error('A state callback is required.');
    const listener = (_event: unknown, state: unknown) => callback(state);
    ipcRenderer.on('quant:state', listener);
    return () => ipcRenderer.removeListener('quant:state', listener);
  },
}));
