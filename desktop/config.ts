import { readFile, mkdir, writeFile, rename, unlink } from 'node:fs/promises';
import path from 'node:path';
import { randomUUID } from 'node:crypto';

export interface EngineConfig {
  version: number;
  dataRoot: string;
  datasetId: string;
  paths: number;
  horizon: number;
  seed: number;
  lookback: number;
  rebalance: number;
  costBps: number;
  shrinkage: number;
  intervalSeconds: number;
  lowCpu: boolean;
  rotateVariants: boolean;
  autoRefreshEcb: boolean;
  startAtLogin: boolean;
  resumeOnLaunch: boolean;
  runSequence: number;
  lastError: string | null;
  lastRefreshError: string | null;
  lastEcbAttemptDate: string | null;
}

export function defaultConfig(dataRoot: string): EngineConfig {
  return { version: 1, dataRoot, datasetId: 'sample', paths: 50_000, horizon: 20, seed: 17,
    lookback: 20, rebalance: 5, costBps: 10, shrinkage: .1, intervalSeconds: 60,
    lowCpu: false, rotateVariants: true, autoRefreshEcb: true, startAtLogin: false,
    resumeOnLaunch: false, runSequence: 0, lastError: null, lastRefreshError: null, lastEcbAttemptDate: null };
}

export const USER_SETTINGS = new Set(['datasetId', 'paths', 'horizon', 'seed', 'lookback',
  'rebalance', 'costBps', 'shrinkage', 'intervalSeconds', 'lowCpu', 'rotateVariants',
  'autoRefreshEcb', 'startAtLogin', 'resumeOnLaunch']);

export function validatePatch(patch: unknown): Partial<EngineConfig> {
  if (!patch || typeof patch !== 'object' || Array.isArray(patch)) throw new Error('Settings must be an object.');
  const values = patch as Record<string, unknown>;
  const numeric: Record<string, [number, number, boolean]> = {
    version: [1, 1, true], paths: [1000, 1_000_000, true], horizon: [1, 252, true], seed: [0, 2 ** 32 - 1, true],
    lookback: [5, 2520, true], rebalance: [1, 63, true], costBps: [0, 500, false], shrinkage: [0, 1, false],
    intervalSeconds: [5, 86400, true], runSequence: [0, Number.MAX_SAFE_INTEGER - 1, true],
  };
  for (const [key, value] of Object.entries(values)) {
    if (numeric[key]) {
      const [low, high, integral] = numeric[key];
      if (typeof value !== 'number' || !Number.isFinite(value) || value < low || value > high || (integral && !Number.isInteger(value))) {
        throw new Error(`${key} must be ${integral ? 'an integer' : 'a number'} from ${low} to ${high}.`);
      }
    } else if (['lowCpu', 'rotateVariants', 'autoRefreshEcb', 'startAtLogin', 'resumeOnLaunch'].includes(key)) {
      if (typeof value !== 'boolean') throw new Error(`${key} must be true or false.`);
    } else if (key === 'dataRoot') {
      if (typeof value !== 'string' || value.length > 4096 || !(path.isAbsolute(value) || /^[A-Za-z]:[\\/]/.test(value))) {
        throw new Error('Storage folder must be an absolute local path.');
      }
    } else if (key === 'datasetId') {
      if (typeof value !== 'string' || !/^[a-zA-Z0-9_-]{1,80}$/.test(value)) throw new Error('Invalid dataset identifier.');
    } else if (key === 'lastEcbAttemptDate') {
      if (value !== null && (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value))) throw new Error('Invalid saved ECB attempt date.');
    } else if (key === 'lastError' || key === 'lastRefreshError') {
      if (value !== null && (typeof value !== 'string' || value.length > 4000)) throw new Error('Invalid saved error.');
    } else throw new Error(`Unknown setting: ${key}`);
  }
  return values as Partial<EngineConfig>;
}

export class ConfigStore {
  value: EngineConfig;
  private queue: Promise<unknown> = Promise.resolve();
  constructor(readonly file: string, defaultRoot: string) { this.value = defaultConfig(defaultRoot); }

  async load(): Promise<EngineConfig> {
    try {
      const values = validatePatch(JSON.parse(await readFile(this.file, 'utf8')));
      this.value = { ...this.value, ...values };
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') {
        this.value.lastError = 'Saved settings could not be read. Default settings are active; startup remains paused.';
      }
    }
    return this.value;
  }

  update(patch: Partial<EngineConfig>): Promise<EngineConfig> {
    let validated: Partial<EngineConfig>;
    try { validated = validatePatch(patch); } catch (error) { return Promise.reject(error); }
    const saved = this.queue.catch(() => {}).then(() => this.write(validated));
    this.queue = saved;
    return saved;
  }

  private async write(patch: Partial<EngineConfig>): Promise<EngineConfig> {
    const next = { ...this.value, ...patch };
    await mkdir(path.dirname(this.file), { recursive: true });
    const temporary = this.file + '.' + randomUUID() + '.tmp';
    try {
      await writeFile(temporary, JSON.stringify(next, null, 2) + '\n', { mode: 0o600 });
      await rename(temporary, this.file);
      this.value = next;
      return next;
    } finally { await unlink(temporary).catch(() => {}); }
  }
}
