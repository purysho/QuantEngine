import type { EngineConfig } from './config.js';
import type { JsonRecord, Transport, WorkerEvent } from './transport.js';

export interface Dataset {
  id: string; kind: string; rows: number; retrieved_at: string;
  name?: string; path?: string; sha256?: string; assets?: string[];
  observation_end?: string; metadata?: JsonRecord;
}
export interface EngineState {
  phase: 'paused' | 'running' | 'waiting' | 'error'; busy: boolean; continuous: boolean;
  stage: string; fraction: number; nextRunAt: string | null; activeRunId: string | null;
  lastError: string | null; lastRefreshError: string | null; completed: number;
  settingsPending: number;
}

export class Engine {
  state: EngineState;
  datasets: Dataset[] = [];
  runs: JsonRecord[] = [];
  lastReport: JsonRecord | null = null;
  lastReportPath: string | null = null;
  optionsReport: JsonRecord | null = null;
  learning: JsonRecord | null = null;
  learningError: string | null = null;
  runtime: JsonRecord = {};
  onChange: () => void = () => {};
  private timer: ReturnType<typeof setTimeout> | null = null;
  private active: Promise<void> | null = null;
  private cancelled = false;
  private pausing = false;
  private pausePromise: Promise<void> | null = null;
  private configQueue: Promise<unknown> = Promise.resolve();
  private dataActive: Promise<Dataset> | null = null;
  private optionsActive: Promise<JsonRecord> | null = null;
  private learnActive: Promise<void> | null = null;
  private initializationActive: Promise<void> | null = null;
  private shuttingDown = false;
  constructor(public config: EngineConfig, readonly transport: Transport,
              readonly persist: (config: EngineConfig) => Promise<void>) {
    this.state = { phase: 'paused', busy: false, continuous: false, stage: 'Ready to run', fraction: 0,
      nextRunAt: null, activeRunId: null, lastError: config.lastError, lastRefreshError: config.lastRefreshError, completed: 0, settingsPending: 0 };
  }

  snapshot() {
    return { state: { ...this.state }, config: { ...this.config }, datasets: this.datasets,
      runs: this.runs, report: this.lastReport, options: this.optionsReport, runtime: this.runtime,
      learning: this.learning, learningError: this.learningError };
  }
  private publish() { this.onChange(); }

  initialize(): Promise<void> {
    if (this.shuttingDown) return Promise.reject(new Error('Quant Engine is shutting down.'));
    const pending = this.initializeWork();
    this.initializationActive = pending;
    return pending.finally(() => { if (this.initializationActive === pending) this.initializationActive = null; });
  }

  private async initializeWork() {
    const result = await this.transport.request('inspect', { recover: true });
    this.datasets = result.datasets as Dataset[];
    this.runs = result.runs as JsonRecord[];
    this.runtime = result.runtime as JsonRecord;
    this.updateStats(result);
    if (!this.datasets.some(d => d.id === this.config.datasetId)) this.config.datasetId = 'sample';
    try { this.learning = (await this.transport.request('learning', {})).learning as JsonRecord; } catch { /* History is optional. */ }
    const latest = this.runs.find(run => run.status === 'completed');
    if (latest) {
      const saved = await this.transport.request('report', { run_id: latest.id });
      this.lastReport = saved.report as JsonRecord;
      this.lastReportPath = saved.report_path as string;
    }
    this.publish();
  }

  private updateStats(result: JsonRecord) {
    const stats = result.stats as { completed?: number } | undefined;
    this.state.completed = stats?.completed ?? this.runs.filter(run => run.status === 'completed').length;
  }

  configure(patch: Partial<EngineConfig>): Promise<void> {
    if (this.shuttingDown) return Promise.reject(new Error('Quant Engine is shutting down.'));
    if (this.pausing) return Promise.reject(new Error('Pause is still recovering research history.'));
    if (this.state.busy) return Promise.reject(new Error('Pause the active worker before changing research settings.'));
    this.state.settingsPending++;
    this.clearTimer();
    this.publish();
    const saved = this.configQueue.catch(() => {}).then(() => this.saveConfiguration(patch)).finally(() => {
      this.state.settingsPending--;
      if (!this.state.settingsPending && this.state.continuous) this.schedule();
      this.publish();
    });
    this.configQueue = saved;
    return saved;
  }

  private async saveConfiguration(patch: Partial<EngineConfig>) {
    const previous = this.config;
    this.config = { ...this.config, ...patch };
    try { await this.persist(this.config); } catch (error) { this.config = previous; throw error; }
    this.publish();
  }

  async start(): Promise<void> {
    if (this.shuttingDown) throw new Error('Quant Engine is shutting down.');
    if (this.state.settingsPending) throw new Error('Settings are still being saved. Wait before starting research.');
    if (this.state.busy) throw new Error('A numerical worker is already active.');
    this.state.continuous = true;
    this.clearTimer();
    return this.execute();
  }

  async runOnce(): Promise<void> {
    if (this.shuttingDown) throw new Error('Quant Engine is shutting down.');
    if (this.state.settingsPending) throw new Error('Settings are still being saved. Wait before starting research.');
    if (this.state.busy) throw new Error('A numerical worker is already active.');
    this.clearTimer();
    return this.execute();
  }

  private clearTimer() {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.state.nextRunAt = null;
  }

  private schedule() {
    this.clearTimer();
    if (!this.state.continuous) return;
    this.state.phase = 'waiting';
    this.state.stage = 'Waiting for next research cycle';
    this.state.nextRunAt = new Date(Date.now() + this.config.intervalSeconds * 1000).toISOString();
    this.timer = setTimeout(() => { this.timer = null; void this.execute(); }, this.config.intervalSeconds * 1000);
    this.publish();
  }

  private execute(): Promise<void> {
    if (this.state.settingsPending) return Promise.reject(new Error('Settings are still being saved.'));
    if (this.state.busy) return Promise.reject(new Error('A numerical worker is already active.'));
    this.cancelled = false;
    this.state.busy = true;
    this.state.phase = 'running';
    this.state.stage = 'Starting numerical worker';
    this.state.fraction = 0;
    this.state.activeRunId = null;
    this.publish();
    this.active = this.job().finally(() => {
      this.state.busy = this.pausing;
      this.state.activeRunId = null;
      this.active = null;
      if (this.state.continuous && !this.cancelled) this.schedule();
      else if (!this.pausing) {
        this.state.phase = this.cancelled || !this.state.lastError ? 'paused' : 'error';
        this.state.stage = this.cancelled ? 'Paused; completed reports retained' : 'Ready to run';
        this.publish();
      }
    });
    return this.active;
  }

  private async job() {
    try {
      let dataset = this.datasets.find(d => d.id === this.config.datasetId);
      if (!dataset) throw new Error('Select an available dataset.');
      const today = new Date().toISOString().slice(0, 10);
      if (dataset.kind === 'ecb' && this.config.autoRefreshEcb && this.state.continuous
          && dataset.retrieved_at.slice(0, 10) !== today && this.config.lastEcbAttemptDate !== today) {
        this.state.stage = 'Refreshing official ECB reference rates';
        this.config.lastEcbAttemptDate = today;
        await this.persist(this.config);
        if (this.cancelled) return;
        this.publish();
        try {
          const refreshed = await this.transport.request('refresh', {});
          this.datasets = refreshed.datasets as Dataset[];
          dataset = refreshed.dataset as Dataset;
          this.state.lastRefreshError = null;
          this.config.lastRefreshError = null;
        } catch (error) {
          if (this.cancelled) return;
          this.state.lastRefreshError = `ECB refresh failed; using the saved snapshot. ${String((error as Error).message)}`;
          this.config.lastRefreshError = this.state.lastRefreshError;
        }
      }
      if (this.cancelled) return;
      const lookbacks = [...new Set([this.config.lookback, 20, 40, 60])].filter(value => value < dataset.rows - 3);
      if (!lookbacks.length) throw new Error('The lookback leaves too few observations. Use a shorter lookback or a longer dataset.');
      const lookback = this.config.rotateVariants ? lookbacks[this.config.runSequence % lookbacks.length] : this.config.lookback;
      const parameters = { paths: this.config.paths, horizon: this.config.horizon,
        seed: (this.config.seed + this.config.runSequence) % 2 ** 32, lookback,
        rebalance: this.config.rebalance, cost_bps: this.config.costBps, shrinkage: this.config.shrinkage };
      const result = await this.transport.request('analyse', { dataset_id: this.config.datasetId, parameters }, event => this.workerEvent(event));
      if (this.cancelled) return;
      this.lastReport = result.report as JsonRecord;
      this.lastReportPath = result.report_path as string;
      this.runs = result.runs as JsonRecord[];
      this.updateStats(result);
      this.config.runSequence++;
      this.state.lastError = null;
      this.config.lastError = null;
      await this.persist(this.config);
      // Continuous mode keeps learning: one bounded evolution run after each completed analysis.
      if (this.state.continuous && this.config.learnContinuously && !this.cancelled) await this.learnStep();
    } catch (error) {
      if (this.cancelled) return;
      this.state.lastError = String((error as Error).message);
      this.config.lastError = this.state.lastError;
      await this.persist(this.config).catch(() => {});
      // Record failed history while retaining the complete result in memory.
      try {
        const result = await this.transport.request('history', { recover: true });
        this.runs = result.runs as JsonRecord[];
        this.updateStats(result);
      } catch { /* Keep the original numerical/storage error. */ }
    }
  }

  private async learnStep() {
    this.state.stage = 'Evolving models (learning)';
    this.state.fraction = 0;
    this.publish();
    try {
      const result = await this.transport.request('learn', { dataset_id: this.config.datasetId,
        budget_seconds: this.config.learnBudgetSeconds }, event => this.workerEvent(event));
      if (this.cancelled) return;
      this.learning = result.learning as JsonRecord;
      this.learningError = null;
    } catch (error) {
      // Learning never fails research: the completed report stands; the reason is shown separately.
      if (!this.cancelled) this.learningError = String((error as Error).message);
    }
  }

  /** Run one learning step now, in the shared worker slot (same rules as option calculations). */
  learnNow(): Promise<void> {
    if (this.shuttingDown) return Promise.reject(new Error('Quant Engine is shutting down.'));
    if (this.pausing) return Promise.reject(new Error('Pause is still recovering research history.'));
    if (this.state.settingsPending) return Promise.reject(new Error('Settings are still being saved.'));
    if (this.state.busy) return Promise.reject(new Error('A numerical worker is already active. Wait or pause before learning.'));
    this.clearTimer();
    this.cancelled = false;
    this.state.busy = true;
    const pending = this.learnStep().finally(() => {
      if (this.learnActive === pending) this.learnActive = null;
      this.state.busy = this.pausing;
      if (this.pausing) return;
      if (this.state.continuous && !this.cancelled) this.schedule();
      else { this.state.stage = 'Ready to run'; this.publish(); }
    });
    this.learnActive = pending;
    return pending;
  }

  private workerEvent(event: WorkerEvent) {
    if (this.cancelled) return;
    if (event.type === 'started') this.state.activeRunId = event.run_id || null;
    if (event.type === 'progress') { this.state.stage = event.stage || 'Computing'; this.state.fraction = event.fraction || 0; }
    this.publish();
  }

  pause(): Promise<void> {
    if (this.pausePromise) return this.pausePromise;
    this.pausePromise = this.pauseWork().finally(() => { this.pausePromise = null; });
    return this.pausePromise;
  }

  private async pauseWork(): Promise<void> {
    const wasBusy = this.state.busy;
    const active = this.active, dataActive = this.dataActive, initializationActive = this.initializationActive,
      optionsActive = this.optionsActive, learnActive = this.learnActive;
    this.pausing = true;
    this.state.continuous = false;
    this.cancelled = true;
    this.clearTimer();
    if (wasBusy) {
      this.state.stage = 'Stopping worker and recovering history';
      this.publish();
      await this.transport.cancel();
      await Promise.allSettled([active, dataActive, initializationActive, optionsActive, learnActive, this.configQueue]);
      // Keep the scheduler lock until the owned child has closed and SQLite history is recovered.
      this.state.busy = true;
      if (this.datasets.length) {
        try {
          const recovered = await this.transport.request('history', { recover: true });
          this.runs = recovered.runs as JsonRecord[];
          this.updateStats(recovered);
        } catch { /* Pausing still succeeds when storage itself is unavailable. */ }
      }
    }
    else await this.configQueue.catch(() => {});
    this.pausing = false;
    this.state.phase = 'paused';
    this.state.stage = 'Paused';
    this.state.busy = false;
    this.publish();
  }

  async shutdown(): Promise<void> {
    this.shuttingDown = true;
    await this.pause();
    await Promise.allSettled([this.configQueue, this.dataActive, this.initializationActive, this.optionsActive, this.learnActive]);
  }

  /** Price a hypothetical option contract in the shared worker slot; never alters research history. */
  calculateOptions(parameters: JsonRecord): Promise<JsonRecord> {
    if (this.shuttingDown) return Promise.reject(new Error('Quant Engine is shutting down.'));
    if (this.pausing) return Promise.reject(new Error('Pause is still recovering research history.'));
    if (this.state.settingsPending) return Promise.reject(new Error('Settings are still being saved. Wait before calculating options.'));
    if (this.state.busy) return Promise.reject(new Error('A numerical worker is already active. Wait or pause before calculating options.'));
    // A waiting continuous cycle is postponed until the option calculation releases the worker.
    this.clearTimer();
    this.cancelled = false;
    this.state.busy = true;
    this.state.stage = 'Calculating option prices';
    this.state.fraction = 0;
    this.publish();
    const pending = this.transport.request('options', { parameters }, event => this.workerEvent(event)).then(result => {
      if (this.cancelled) throw new Error('Option calculation cancelled.');
      this.optionsReport = result.report as JsonRecord;
      return this.optionsReport;
    }, error => {
      throw this.cancelled ? new Error('Option calculation cancelled.') : error;
    }).finally(() => {
      if (this.optionsActive === pending) this.optionsActive = null;
      this.state.busy = this.pausing;
      if (this.pausing) return;
      if (this.state.continuous && !this.cancelled) this.schedule();
      else { this.state.stage = 'Ready to run'; this.publish(); }
    });
    this.optionsActive = pending;
    return pending;
  }

  dataCommand(command: 'import' | 'refresh', values: JsonRecord = {}): Promise<Dataset> {
    if (this.shuttingDown) return Promise.reject(new Error('Quant Engine is shutting down.'));
    if (this.state.settingsPending) return Promise.reject(new Error('Settings are still being saved. Wait before changing datasets.'));
    if (this.state.busy || this.state.continuous) return Promise.reject(new Error('Pause the engine before changing datasets.'));
    this.state.busy = true;
    this.cancelled = false;
    this.state.stage = command === 'import' ? 'Validating and copying CSV' : 'Refreshing official ECB reference rates';
    this.publish();
    const pending = this.dataJob(command, values);
    this.dataActive = pending;
    return pending.finally(() => { if (this.dataActive === pending) this.dataActive = null; });
  }

  private async dataJob(command: 'import' | 'refresh', values: JsonRecord): Promise<Dataset> {
    try {
      const result = await this.transport.request(command, values);
      this.datasets = result.datasets as Dataset[];
      const dataset = result.dataset as Dataset;
      this.config.datasetId = dataset.id;
      if (command === 'refresh') { this.config.lastRefreshError = null; this.state.lastRefreshError = null; }
      await this.persist(this.config);
      return dataset;
    } catch (error) {
      if (this.cancelled) throw new Error('Dataset operation cancelled. The saved snapshots were retained.');
      this.state.lastError = String((error as Error).message);
      this.config.lastError = this.state.lastError;
      await this.persist(this.config).catch(() => {});
      throw error;
    } finally { this.state.busy = this.pausing; if (!this.pausing) { this.state.stage = 'Ready to run'; this.publish(); } }
  }
}
