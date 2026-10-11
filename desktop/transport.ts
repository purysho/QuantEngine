import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { setPriority, constants } from 'node:os';

export type JsonRecord = Record<string, unknown>;
export interface WorkerEvent { type: string; stage?: string; fraction?: number; run_id?: string; }
export interface Transport {
  request(command: string, values: JsonRecord, event?: (value: WorkerEvent) => void): Promise<JsonRecord>;
  cancel(): Promise<void>;
}

export class WorkerTransport implements Transport {
  child: ChildProcessWithoutNullStreams | null = null;
  private closed: Promise<void> | null = null;
  constructor(readonly python: string, readonly worker: string, readonly root: () => string,
              readonly lowCpu: () => boolean) {}

  request(command: string, values: JsonRecord = {}, event?: (value: WorkerEvent) => void): Promise<JsonRecord> {
    if (this.child) return Promise.reject(new Error('A numerical worker is already active.'));
    return new Promise((resolve, reject) => {
      const child = spawn(this.python, ['-X', 'utf8', '-u', this.worker], {
        shell: false, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'],
        env: { ...process.env, PYTHONUTF8: '1', PYTHONUNBUFFERED: '1',
          QUANT_LOW_CPU: this.lowCpu() ? '1' : '0',
          OMP_NUM_THREADS: this.lowCpu() ? '1' : '2', OPENBLAS_NUM_THREADS: this.lowCpu() ? '1' : '2',
          MKL_NUM_THREADS: this.lowCpu() ? '1' : '2', NUMEXPR_NUM_THREADS: this.lowCpu() ? '1' : '2' },
      });
      this.child = child;
      // Node's decoder retains partial UTF-8 sequences across pipe chunks.
      child.stdout.setEncoding('utf8');
      child.stderr.setEncoding('utf8');
      if (this.lowCpu() && child.pid) {
        try { setPriority(child.pid, constants.priority.PRIORITY_BELOW_NORMAL); } catch { /* OS may deny priority changes. */ }
      }
      let closed!: () => void;
      this.closed = new Promise<void>(r => { closed = r; });
      let pending = '', stderr = '', totalBytes = 0;
      let result: JsonRecord | undefined;
      let failure: Error | undefined;
      const timer = setTimeout(() => { failure = new Error('Numerical worker exceeded the 10-minute job limit.'); child.kill(); }, 600_000);
      const consume = (line: string) => {
        if (!line.trim()) return;
        try {
          const message = JSON.parse(line) as JsonRecord;
          if (message.type === 'result') {
            if (message.ok === true && message.result && typeof message.result === 'object') result = message.result as JsonRecord;
            else failure = new Error(String(message.error || 'Numerical worker failed.'));
          } else event?.(message as unknown as WorkerEvent);
        } catch { failure = new Error('Numerical worker returned malformed output.'); child.kill(); }
      };
      child.stdout.on('data', (chunk: string) => {
        totalBytes += Buffer.byteLength(chunk, 'utf8');
        if (totalBytes > 128 * 1024 * 1024) { failure = new Error('Worker report exceeded 128 MB.'); child.kill(); return; }
        pending += chunk;
        const lines = pending.split('\n');
        pending = lines.pop() || '';
        for (const line of lines) consume(line);
      });
      child.stderr.on('data', (chunk: string) => { stderr = (stderr + chunk).slice(-16_384); });
      child.on('error', error => { failure = new Error(`Python runtime could not start: ${error.message}`); });
      child.on('close', code => {
        clearTimeout(timer);
        if (pending) consume(pending);
        if (this.child === child) this.child = null;
        closed();
        this.closed = null;
        if (failure) reject(failure);
        else if (code !== 0 || !result) reject(new Error(stderr.trim() || 'Numerical worker stopped before returning a complete result.'));
        else resolve(result);
      });
      child.stdin.on('error', () => {});
      child.stdin.end(JSON.stringify({ command, root: this.root(), ...values }) + '\n');
    });
  }

  async cancel(): Promise<void> {
    const child = this.child, closed = this.closed;
    if (!child) return;
    child.kill();
    await closed;
  }
}
