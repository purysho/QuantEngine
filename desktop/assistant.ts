// QuantEngine assistant: typed or dictated commands (e.g. via Handy) -> intents -> permissioned actions.
// Deterministic first: answers come from the latest real report; an optional local model only answers questions.
import type { EngineConfig } from './config.js';
import type { JsonRecord } from './transport.js';

export type Tier = 'read' | 'compute' | 'change' | 'refused';
export type Intent =
  | { kind: 'help' }
  | { kind: 'answer'; topic: 'var' | 'volatility' | 'backtest' | 'weights' | 'status' | 'option' | 'surface' | 'learning' }
  | { kind: 'learn' }
  | { kind: 'explain'; scope: 'options' | 'report'; key: string; label: string }
  | { kind: 'navigate'; page: string; chart?: string }
  | { kind: 'run-once' } | { kind: 'start' } | { kind: 'pause' }
  | { kind: 'price-option'; parameters: JsonRecord; assumed: string[] }
  | { kind: 'configure'; patch: Partial<EngineConfig>; label: string }
  | { kind: 'refresh-ecb' }
  | { kind: 'undo' }
  | { kind: 'refuse'; reason: string }
  | { kind: 'unknown' };

export const TIERS: Record<Intent['kind'], Tier> = {
  help: 'read', answer: 'read', navigate: 'read', unknown: 'read', 'run-once': 'compute', start: 'compute',
  pause: 'compute', 'price-option': 'compute', learn: 'compute', explain: 'read', configure: 'change', 'refresh-ecb': 'change', undo: 'change', refuse: 'refused',
};

const SMALL: Record<string, number> = { zero: 0, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9,
  ten: 10, eleven: 11, twelve: 12, thirteen: 13, fourteen: 14, fifteen: 15, sixteen: 16, seventeen: 17, eighteen: 18,
  nineteen: 19, twenty: 20, thirty: 30, forty: 40, fifty: 50, sixty: 60, seventy: 70, eighty: 80, ninety: 90, a: 1 };
const SCALE: Record<string, number> = { hundred: 100, thousand: 1_000, million: 1_000_000 };

/** Dictation output often spells numbers ("one hundred and five", "two point five"); turn them into digits. */
export function wordsToDigits(text: string): string {
  const tokens = text.split(/(\s+)/);
  const out: string[] = [];
  let i = 0;
  while (i < tokens.length) {
    const word = tokens[i].toLowerCase();
    if (!(word in SMALL || word in SCALE) || (word === 'a' && !(tokens[i + 2]?.toLowerCase() in SCALE))) {
      out.push(tokens[i]); i++; continue;
    }
    let total = 0, current = 0, j = i, last = i, decimals = '';
    while (j < tokens.length) {
      const w = tokens[j].toLowerCase();
      if (/^\s+$/.test(tokens[j])) { j++; continue; }
      if (w in SMALL && !(w === 'a' && j > i)) { current += SMALL[w]; last = j; j++; continue; }
      if (w in SCALE) { current = Math.max(current, 1) * SCALE[w]; if (SCALE[w] >= 1000) { total += current; current = 0; } last = j; j++; continue; }
      if (w === 'and' && j > i) { j++; continue; }
      if (w === 'point') {
        let k = j + 1; const digits: string[] = [];
        while (k < tokens.length) {
          const d = tokens[k].toLowerCase();
          if (/^\s+$/.test(tokens[k])) { k++; continue; }
          if (d in SMALL && SMALL[d] < 10 && d !== 'a') { digits.push(String(SMALL[d])); last = k; k++; continue; }
          break;
        }
        if (digits.length) { decimals = '.' + digits.join(''); j = k; }
        break;
      }
      break;
    }
    out.push(String(total + current) + decimals);
    i = last + 1;
  }
  return out.join('');
}

export function normalise(text: string): string {
  // Dictation inserts punctuation ("ninety five, spot one hundred,"); remove it before reading spoken numbers.
  const cleaned = String(text).slice(0, 500).toLowerCase().replace(/[“”"’`]/g, '').replace(/(\d),(\d{3})/g, '$1$2')
    .replace(/[,;:!?]+|\.(?!\d)/g, ' ; ');  // Punctuation ends a spoken number ("one hundred, six months").
  return wordsToDigits(cleaned).replace(/ ; /g, ' ').replace(/;/g, '').replace(/\s+/g, ' ').trim();
}

function number(text: string, pattern: RegExp): number | undefined {
  const match = text.match(pattern);
  return match ? Number(match[1]) : undefined;
}

const decimalOrPercent = (value: number | undefined, explicitPercent: boolean) =>
  value === undefined ? undefined : explicitPercent || value > 1.5 ? value / 100 : value;

function percentAfter(text: string, words: string): number | undefined {
  const match = text.match(new RegExp(`(?:${words})[a-z ]{0,20}?(?:of |at |is |to |=)?(-?\\d+(?:\\.\\d+)?)\\s*(%|percent|per cent)?`));
  return match ? decimalOrPercent(Number(match[1]), Boolean(match[2])) : undefined;
}

function expiryYears(text: string): number | undefined {
  if (/\bhalf (a )?year\b/.test(text)) return .5;
  const match = text.match(/(\d+(?:\.\d+)?)\s*(year|yr|month|mo|week|wk|day)s?\b/);
  if (!match) return undefined;
  const value = Number(match[1]);
  return ({ year: 1, yr: 1, month: 1 / 12, mo: 1 / 12, week: 7 / 365, wk: 7 / 365, day: 1 / 365 } as Record<string, number>)[match[2]] * value;
}

export function parseCommand(input: string): Intent {
  const text = normalise(input);
  if (!text) return { kind: 'unknown' };
  if (/\b(buy|sell|short|go long|place|submit|send)\b.*\b(order|shares?|stock|contracts?|position|it)\b|\b(trade|execute|broker(age)?)\b(?! cost)/.test(text)
      && !/\b(cost|costs|backtest)\b/.test(text)) {
    return { kind: 'refuse', reason: 'QuantEngine is research-only: it has no brokerage connection and cannot place or send orders.' };
  }
  if (/^(help|what can you do|commands|\?)/.test(text)) return { kind: 'help' };
  // Explanations of QuantEngine's own maths are answered from the report's step-by-step workings;
  // anything else goes to the optional local model (or a pointer to help), never to a canned number.
  if (/^(explain|why|teach me|tell me about|how does|how do|how is|what does .+ mean|describe|show (me )?the math|show (me )?the working)/.test(text)) {
    const topics: Array<[RegExp, 'options' | 'report', string, string]> = [
      [/black.?scholes|option price|d1|d2|call price|put price/, 'options', 'black_scholes', 'Black–Scholes'],
      [/binomial|tree|crr/, 'options', 'crr', 'the binomial tree'], [/monte carlo/, 'options', 'monte_carlo', 'Monte Carlo pricing'],
      [/vix|rule of 16|implied move/, 'options', 'implied_move', 'the VIX ÷ 16 rule'],
      [/student|fat tail|t distribution/, 'report', 'student_t', 'the Student-t risk model'],
      [/shortfall|empirical|tail/, 'report', 'empirical_tail_daily', 'empirical VaR and expected shortfall'],
      [/var|value at risk|risk/, 'report', 'gaussian_var', 'Gaussian VaR'],
      [/portfolio|weights?|minimum variance|allocation/, 'report', 'minimum_variance', 'the minimum-variance portfolio']];
    for (const [pattern, scope, key, label] of topics) if (pattern.test(text)) return { kind: 'explain', scope, key, label };
    return { kind: 'unknown' };
  }
  if (/^undo\b|undo (that|the last)/.test(text)) return { kind: 'undo' };
  if (/\b(price|value|quote)\b.*\b(call|put|option)s?\b|\b(call|put) option\b/.test(text)) {
    const assumed: string[] = [];
    const kind = /\bput\b/.test(text) ? 'put' : 'call';
    const spot = number(text, /(?:spot|underlying|stock(?: price)?|price of|at)\s*(?:of |is |at |=)?\$?(\d+(?:\.\d+)?)/) ?? (assumed.push('spot 100'), 100);
    const strike = number(text, /strike\s*(?:of |at |is |=|price )?\$?(\d+(?:\.\d+)?)/) ?? (assumed.push('strike = spot'), spot);
    const time = expiryYears(text) ?? (assumed.push('1 year to expiry'), 1);
    const volatility = percentAfter(text, 'vol|volatility|implied vol|iv|sigma') ?? (assumed.push('20% volatility'), .2);
    const rate = percentAfter(text, 'rate|interest|risk free|risk-free') ?? (assumed.push('5% rate'), .05);
    const dividend = percentAfter(text, 'dividend|yield') ?? 0;
    return { kind: 'price-option', parameters: { kind, spot, strike, time, volatility, rate, dividend }, assumed };
  }
  const nav: Array<[RegExp, string, string?]> = [
    [/\b(terminal|markets?|watchlist|quotes?|news)\b/, 'terminal'],
    [/\b(vol(atility)? surface|3d|surface)\b/, 'monitor', 'surface'], [/\boptions?\b/, 'options'], [/\bdatasets?|data\b/, 'datasets'],
    [/\b(evolution|lineage|graph|second mind|learning)\b/, 'evolution'], [/\b(runs?|history)\b/, 'runs'], [/\b(preferences|settings)\b/, 'preferences'], [/\b(monitor|overview|home|dashboard)\b/, 'monitor'],
    [/\bequity\b/, 'monitor', 'equity'], [/\bcorrelations?\b/, 'monitor', 'correlation'], [/\b(risk distribution|histogram)\b/, 'monitor', 'risk'],
  ];
  if (/^(show|open|go to|navigate to|switch to|take me to|display)\b/.test(text)) {
    for (const [pattern, page, chart] of nav) if (pattern.test(text)) return { kind: 'navigate', page, chart };
  }
  if (/\b(what|how much|show)\b.*\b(learn|learned|learnt|evolv|evolution)/.test(text)) return { kind: 'answer', topic: 'learning' };
  if (/\b(learn|evolve|train)\b/.test(text)) return { kind: 'learn' };
  if (/\b(run|calculate|compute)\b.*\b(once|now|analysis|research)\b|^run( it)?$/.test(text)) return { kind: 'run-once' };
  if (/\b(start|resume|begin)\b.*\b(engine|research|continuous)\b|^start$/.test(text)) return { kind: 'start' };
  if (/\b(pause|stop|halt)\b/.test(text)) return { kind: 'pause' };
  if (/\b(refresh|update|download)\b.*\becb\b/.test(text)) return { kind: 'refresh-ecb' };
  const setting: Array<[RegExp, keyof EngineConfig, string, (n: number, t: string) => number]> = [
    [/\b(paths|simulations?)\b/, 'paths', 'simulation paths', n => Math.round(n)],
    [/\bhorizon\b/, 'horizon', 'risk horizon (observations)', n => Math.round(n)],
    [/\blookback\b/, 'lookback', 'momentum lookback', n => Math.round(n)],
    [/\brebalanc/, 'rebalance', 'rebalance interval', n => Math.round(n)],
    [/\b(cost|costs|fees?)\b/, 'costBps', 'transaction cost (bps)', n => n],
    [/\bshrinkage\b/, 'shrinkage', 'covariance shrinkage', n => n > 1 ? n / 100 : n],
    [/\binterval\b/, 'intervalSeconds', 'cycle interval (seconds)', (n, t) => Math.round(/\bminutes?\b/.test(t) ? n * 60 : n)],
    [/\bseed\b/, 'seed', 'random seed', n => Math.round(n)],
  ];
  if (/\b(set|change|make|use)\b/.test(text)) {
    for (const [pattern, key, label, convert] of setting) {
      if (!pattern.test(text)) continue;
      const value = number(text, /\b(?:to|=|at|of)\s*(-?\d+(?:\.\d+)?)/) ?? number(text, /(-?\d+(?:\.\d+)?)/);
      if (value !== undefined) return { kind: 'configure', patch: { [key]: convert(value, text) } as Partial<EngineConfig>, label };
    }
  }
  const toggle = text.match(/\b(enable|disable|turn on|turn off|switch on|switch off)\b.*\blow[- ]?cpu\b|\blow[- ]?cpu\b.*\b(on|off)\b/);
  if (toggle) return { kind: 'configure', patch: { lowCpu: /\b(enable|turn on|switch on|on)\b/.test(text) && !/\b(disable|off)\b/.test(text) }, label: 'low CPU mode' };
  if (/\b(var|value at risk|expected shortfall|tail risk|shortfall|garch)\b/.test(text)) return { kind: 'answer', topic: 'var' };
  if (/\b(surface)\b/.test(text)) return { kind: 'answer', topic: 'surface' };
  if (/\b(volatility|vol|risky)\b/.test(text)) return { kind: 'answer', topic: 'volatility' };
  if (/\b(sharpe|backtest|momentum|strategy|return|performance|drawdown)\b/.test(text)) return { kind: 'answer', topic: 'backtest' };
  if (/\b(weights?|allocation|portfolio|holdings)\b/.test(text)) return { kind: 'answer', topic: 'weights' };
  if (/\b(option|greeks?|delta|implied)\b/.test(text)) return { kind: 'answer', topic: 'option' };
  if (/\b(status|doing|running|busy|state|progress)\b/.test(text)) return { kind: 'answer', topic: 'status' };
  return { kind: 'unknown' };
}

const pct = (value: unknown, digits = 2) => typeof value === 'number' && Number.isFinite(value) ? (value * 100).toFixed(digits) + '%' : 'n/a';
const fixed = (value: unknown, digits = 2) => typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : 'n/a';

export interface Snapshot { state: JsonRecord; config: JsonRecord; report: JsonRecord | null; options?: JsonRecord | null; datasets?: unknown[]; learning?: JsonRecord | null }

export function answer(topic: string, snapshot: Snapshot): string {
  const report = snapshot.report as Record<string, any> | null;
  if (topic === 'status') {
    const s = snapshot.state as Record<string, any>;
    return `Engine is ${s.busy ? 'computing (' + (s.stage || 'working') + ')' : s.continuous ? 'waiting for the next cycle' : 'paused'}. ` +
      `${s.completed ?? 0} completed reports.` + (s.nextRunAt ? ` Next cycle at ${s.nextRunAt}.` : '') + (s.lastError ? ` Last error: ${s.lastError}` : '');
  }
  if (topic === 'option') {
    const o = snapshot.options as Record<string, any> | null | undefined;
    if (!o) return 'No option has been priced yet. Try: "price a put, strike 95, spot 100, 6 months, vol 25%".';
    const p = o.parameters, bs = o.black_scholes;
    return `${String(p.kind).toUpperCase()} spot ${p.spot}, strike ${p.strike}, ${fixed(p.time)}y, vol ${pct(p.volatility, 1)}: Black–Scholes ${fixed(bs.price, 4)}, ` +
      `American tree ${fixed(o.trees.american, 4)}, delta ${fixed(bs.delta, 4)}, vega ${fixed(bs.vega_per_point, 4)} per vol point.`;
  }
  if (topic === 'learning') {
    const l = snapshot.learning as Record<string, any> | null | undefined;
    if (!l?.tasks) return 'Nothing learned yet. Say "learn now", or start the engine: each continuous cycle runs one bounded evolution step.';
    const line = (name: string, unit: string) => {
      const t = l.tasks[name]; if (!t) return '';
      const champion = t.champion ? Object.entries(t.champion).map(([k, v]) => `${k}=${v}`).join(', ') : 'none';
      return `${name}: champion ${champion}; out-of-sample ${fixed(t.mean_out_of_sample, 3)} vs baseline ${fixed(t.mean_baseline, 3)} ${unit} ` +
        `over ${t.blocks} blocks (guard kept the incumbent ${pct(t.guard_share, 0)} of the time).`;
    };
    return [line('risk', '(minus pinball loss x1e4, higher is better)'), line('alpha', '(R^2 %)'),
      `${(l.history || []).length} learning runs recorded; ${l.memories ?? 0} memories.`].filter(Boolean).join(' ');
  }
  if (!report) return 'There is no completed report yet. Say "run once" to calculate one.';
  const source = ` (run ${report.run?.id ?? 'unknown'}, ${report.provenance?.name ?? 'dataset'})`;
  if (topic === 'var') {
    const g = report.monte_carlo, b = report.bootstrap, t = report.student_t;
    return `${g.horizon}-observation 95% VaR: Gaussian ${pct(g.var95)}, block bootstrap ${pct(b.var95)}` + (t ? `, Student-t ${pct(t.var95)}` : '') +
      `. 95% expected shortfall: ${pct(g.es95)} / ${pct(b.es95)}` + (t ? ` / ${pct(t.es95)}` : '') +
      (t ? `. Fitted t degrees of freedom ${fixed(t.degrees_of_freedom, 1)}.` : '.') +
      (report.conditional_risk ? ` Tomorrow (GJR-GARCH FHS, best on 100 years of real data): 99% VaR ${pct(report.conditional_risk.var99)}, ` +
        `current volatility ${pct(report.conditional_risk.sigma_annualized, 1)} a year vs long-run ${pct(report.conditional_risk.long_run_sigma_annualized, 1)}.` : '') + source;
  }
  if (topic === 'volatility' || topic === 'surface') {
    const surface = report.volatility_surface;
    let recent = '';
    if (surface) {
      const i = surface.windows.indexOf(20) >= 0 ? surface.windows.indexOf(20) : 0;
      recent = ` Latest ${surface.windows[i]}-day realised volatility: ${pct(surface.values[i].at(-1))} (through ${surface.dates.at(-1)}).`;
    }
    return `Optimised portfolio annualised volatility: ${pct(report.annualized_volatility)}.` + recent + source;
  }
  if (topic === 'backtest') {
    const bt = report.backtest;
    return `Momentum strategy, next-close execution, ${bt.cost_bps} bps costs: total ${pct(bt.total_return)}, Sharpe ${fixed(bt.sharpe)}, ` +
      `max drawdown ${pct(bt.max_drawdown)}. Equal weight: ${pct(bt.baselines.equal_weight.total_return)}. Cash: 0%.` + source;
  }
  if (topic === 'weights') {
    return 'Minimum-variance weights: ' + Object.entries(report.weights as Record<string, number>).map(([k, v]) => `${k} ${pct(v, 1)}`).join(', ') + '.' + source;
  }
  return '';
}

export const HELP = [
  'Ask: "what is my VaR", "how volatile is the portfolio", "what is the Sharpe", "show the weights", "status".',
  'Navigate: "show the vol surface", "open options", "go to runs".',
  'Compute: "run once", "start the engine", "pause", "learn now", "price a put strike 95 spot 100 6 months vol 25%".',
  'Learning: "what have you learned", "show the evolution graph".',
  'Maths: "explain Black-Scholes", "explain my VaR", "explain expected shortfall", "show the maths for the portfolio".',
  'Change (asks to confirm, undoable): "set paths to 100000", "set horizon to 10", "enable low cpu", "refresh ECB rates".',
  'Voice: dictate into this box with Handy (offline, free) or Windows voice typing.',
].join('\n');

/** Build a compact, path-free context for an optional local model. */
export function modelContext(snapshot: Snapshot): JsonRecord {
  const r = snapshot.report as Record<string, any> | null;
  return {
    engine: { phase: (snapshot.state as any).phase, completed: (snapshot.state as any).completed },
    report: r ? { dataset: r.provenance?.name, kind: r.provenance?.kind, date_range: r.date_range, assets: r.assets,
      annualized_volatility: r.annualized_volatility, weights: r.weights,
      var95: { gaussian: r.monte_carlo?.var95, bootstrap: r.bootstrap?.var95, student_t: r.student_t?.var95 },
      backtest: { total_return: r.backtest?.total_return, sharpe: r.backtest?.sharpe, equal_weight: r.backtest?.baselines?.equal_weight?.total_return },
      methodology: r.methodology } : null,
  };
}

export function validateLocalEndpoint(endpoint: string): URL {
  const url = new URL(endpoint);
  if (!['http:', 'https:'].includes(url.protocol) || !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)) {
    throw new Error('The assistant model endpoint must be on this computer (localhost / 127.0.0.1).');
  }
  return url;
}

/** Ask an OpenAI-compatible local server (llama.cpp, Ollama, LM Studio). Answers only; it can never trigger actions. */
export async function askLocalModel(endpoint: string, model: string, question: string, context: JsonRecord,
                                    fetchImpl: typeof fetch = fetch, timeoutMs = 60_000): Promise<string> {
  const url = validateLocalEndpoint(endpoint);
  const base = url.href.replace(/\/+$/, '');
  const target = /\/chat\/completions$/.test(base) ? base : base.replace(/\/v1$/, '') + '/v1/chat/completions';
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetchImpl(target, {
      method: 'POST', signal: controller.signal, headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ model: model || 'local', temperature: .2, max_tokens: 400, messages: [
        { role: 'system', content: 'You are the QuantEngine research assistant. Answer only from the JSON context; if the answer is not in it, say so. ' +
          'You cannot run calculations, change settings or trade. Be concise.\nContext: ' + JSON.stringify(context).slice(0, 12_000) },
        { role: 'user', content: question.slice(0, 2_000) }] }),
    });
    if (!response.ok) throw new Error(`Local model returned HTTP ${response.status}.`);
    const body = await response.json() as { choices?: Array<{ message?: { content?: string } }> };
    const content = body.choices?.[0]?.message?.content;
    if (typeof content !== 'string' || !content.trim()) throw new Error('Local model returned no answer.');
    return content.trim().slice(0, 4_000);
  } finally { clearTimeout(timer); }
}

export interface AssistantEngine {
  config: EngineConfig;
  snapshot(): Snapshot & JsonRecord;
  runOnce(): Promise<void>; start(): Promise<void>; pause(): Promise<void>;
  configure(patch: Partial<EngineConfig>): Promise<void>;
  calculateOptions(parameters: JsonRecord): Promise<JsonRecord>;
  learnNow(): Promise<void>;
  dataCommand(command: 'refresh'): Promise<unknown>;
}

export interface AssistantReply {
  reply: string; tier: Tier; intent: Intent['kind'];
  navigate?: { page: string; chart?: string }; options?: JsonRecord; confirm?: { token: string; summary: string };
  source?: 'engine' | 'local-model';
}

export class Assistant {
  private pending: { token: string; intent: Intent; expires: number } | null = null;
  private undo: Array<{ patch: Partial<EngineConfig>; label: string }> = [];
  constructor(readonly engine: AssistantEngine,
              readonly log: (entry: JsonRecord) => Promise<void> = async () => {},
              readonly model: () => { endpoint: string; model: string } | null = () => null,
              readonly fetchImpl: typeof fetch = fetch) {}

  async handle(text: string): Promise<AssistantReply> {
    if (typeof text !== 'string' || !text.trim()) throw new Error('Say or type a request.');
    const intent = parseCommand(text);
    const result = await this.execute(intent, text);
    await this.log({ at: new Date().toISOString(), text: text.slice(0, 500), intent: intent.kind, tier: result.tier,
      reply: result.reply.slice(0, 500), confirm: Boolean(result.confirm) }).catch(() => {});
    return result;
  }

  private ask(intent: Intent, summary: string): AssistantReply {
    const token = Math.random().toString(36).slice(2) + Date.now().toString(36);
    this.pending = { token, intent, expires: Date.now() + 120_000 };
    return { reply: summary + ' Confirm to apply.', tier: TIERS[intent.kind], intent: intent.kind, confirm: { token, summary } };
  }

  async confirm(token: string, accept: boolean): Promise<AssistantReply> {
    const pending = this.pending;
    this.pending = null;
    if (!pending || pending.token !== token || pending.expires < Date.now()) throw new Error('That confirmation has expired. Ask again.');
    if (!accept) return { reply: 'Cancelled; nothing changed.', tier: 'read', intent: pending.intent.kind };
    const result = await this.apply(pending.intent);
    await this.log({ at: new Date().toISOString(), confirmed: pending.intent.kind, reply: result.reply.slice(0, 500) }).catch(() => {});
    return result;
  }

  private async apply(intent: Intent): Promise<AssistantReply> {
    if (intent.kind === 'configure') {
      const previous: Partial<EngineConfig> = {};
      for (const key of Object.keys(intent.patch) as Array<keyof EngineConfig>) (previous as any)[key] = this.engine.config[key];
      await this.engine.configure(intent.patch);
      this.undo.push({ patch: previous, label: intent.label });
      if (this.undo.length > 20) this.undo.shift();
      return { reply: `Updated ${intent.label}. Say "undo" to revert.`, tier: 'change', intent: 'configure' };
    }
    if (intent.kind === 'refresh-ecb') {
      await this.engine.dataCommand('refresh');
      return { reply: 'Saved a new official ECB reference-rate snapshot.', tier: 'change', intent: 'refresh-ecb' };
    }
    if (intent.kind === 'undo') {
      const last = this.undo.pop();
      if (!last) return { reply: 'Nothing to undo.', tier: 'read', intent: 'undo' };
      await this.engine.configure(last.patch);
      return { reply: `Reverted ${last.label}.`, tier: 'change', intent: 'undo' };
    }
    throw new Error('Unsupported confirmation.');
  }

  private async execute(intent: Intent, text: string): Promise<AssistantReply> {
    const tier = TIERS[intent.kind];
    const snapshot = this.engine.snapshot();
    switch (intent.kind) {
      case 'help': return { reply: HELP, tier, intent: intent.kind };
      case 'refuse': return { reply: intent.reason, tier, intent: intent.kind };
      case 'explain': {
        const source = (intent.scope === 'options' ? snapshot.options : snapshot.report) as Record<string, any> | null | undefined;
        const steps = source?.explanation?.[intent.key] as Array<Record<string, string>> | undefined;
        if (!steps?.length) {
          return { reply: `No ${intent.scope === 'options' ? 'option calculation' : 'report'} to explain yet. ` +
            (intent.scope === 'options' ? 'Price an option first, e.g. "price a call strike 100 vol 20%".' : 'Say "run once" first.'), tier, intent: intent.kind };
        }
        const text = steps.map((s, i) => `${i + 1}. ${s.title}: ${s.formula}` + (s.substitution ? ` = ${s.substitution}` : '') + (s.result !== '' ? ` = ${s.result}` : '') +
          (s.note ? ` (${s.note})` : '')).join('\n');
        return { reply: `How ${intent.label} was calculated:\n${text}`, tier, intent: intent.kind, source: 'engine',
          navigate: { page: intent.scope === 'options' ? 'options' : 'monitor' } };
      }
      case 'answer': return { reply: answer(intent.topic, snapshot), tier, intent: intent.kind, source: 'engine' };
      case 'navigate': return { reply: `Opening ${intent.chart === 'surface' ? 'the 3D volatility surface' : intent.page}.`, tier, intent: intent.kind,
        navigate: { page: intent.page, chart: intent.chart } };
      case 'run-once': await this.engine.runOnce(); return { reply: 'Calculated a new report. ' + answer('var', this.engine.snapshot()), tier, intent: intent.kind };
      case 'start': await this.engine.start(); return { reply: 'Continuous research started.', tier, intent: intent.kind };
      case 'pause': await this.engine.pause(); return { reply: 'Paused. Completed reports are kept.', tier, intent: intent.kind };
      case 'learn': await this.engine.learnNow(); return { reply: 'Ran one evolution step. ' + answer('learning', this.engine.snapshot()), tier, intent: intent.kind,
        navigate: { page: 'evolution' } };
      case 'price-option': {
        const report = await this.engine.calculateOptions({ ...intent.parameters, paths: 100_000 }) as Record<string, any>;
        const bs = report.black_scholes;
        return { reply: `${String(intent.parameters.kind).toUpperCase()}: Black–Scholes ${fixed(bs.price, 4)}, American ${fixed(report.trees.american, 4)}, ` +
          `delta ${fixed(bs.delta, 3)}.` + (intent.assumed.length ? ` Assumed ${intent.assumed.join(', ')}.` : ''),
          tier, intent: intent.kind, navigate: { page: 'options' }, options: intent.parameters };
      }
      case 'configure': {
        const [key, value] = Object.entries(intent.patch)[0];
        const current = (this.engine.config as unknown as JsonRecord)[key];
        return this.ask(intent, `Change ${intent.label} from ${String(current)} to ${String(value)}?`);
      }
      case 'refresh-ecb': return this.ask(intent, 'Download a new ECB reference-rate snapshot (internet)?');
      case 'undo': {
        const last = this.undo.at(-1);
        return last ? this.ask(intent, `Revert ${last.label}?`) : { reply: 'Nothing to undo.', tier: 'read', intent: 'undo' };
      }
      default: {
        const model = this.model();
        if (model?.endpoint) {
          try {
            const reply = await askLocalModel(model.endpoint, model.model, text, modelContext(snapshot), this.fetchImpl);
            return { reply, tier: 'read', intent: 'unknown', source: 'local-model' };
          } catch (error) {
            return { reply: `I did not recognise that, and the local model failed: ${(error as Error).message} Say "help" for commands.`, tier: 'read', intent: 'unknown' };
          }
        }
        return { reply: 'I did not recognise that. Say "help" for commands, or connect a local model in Preferences for free-form questions.', tier: 'read', intent: 'unknown' };
      }
    }
  }
}
