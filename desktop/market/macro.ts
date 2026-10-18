// Free macro dashboard from FRED (no key): volatility, rates, the dollar and oil.
import type { Fetch } from './alpaca.js';

export const MACRO_SERIES: Array<{ id: string; label: string; unit: string; decimals: number }> = [
  { id: 'VIXCLS', label: 'VIX', unit: 'index', decimals: 2 },
  { id: 'DGS2', label: 'US 2-year yield', unit: '%', decimals: 2 },
  { id: 'DGS10', label: 'US 10-year yield', unit: '%', decimals: 2 },
  { id: 'T10Y2Y', label: '10y − 2y spread', unit: 'pp', decimals: 2 },
  { id: 'DFF', label: 'Fed funds rate', unit: '%', decimals: 2 },
  { id: 'DTWEXBGS', label: 'Broad US dollar', unit: 'index', decimals: 2 },
  { id: 'DCOILBRENTEU', label: 'Brent crude', unit: '$/bbl', decimals: 2 },
];

export interface MacroPoint { id: string; label: string; unit: string; decimals: number; date: string | null;
  value: number | null; previous: number | null; change: number | null; history: Array<[string, number]> }

/** Parses one FRED graph CSV (observation_date,ID); blanks and '.' are missing values. */
export function parseSeries(csv: string, id: string): Array<[string, number]> {
  const lines = csv.replace(/^\uFEFF/, '').trim().split(/\r?\n/);
  const header = lines[0]?.split(',').map(cell => cell.trim()) ?? [];
  if (!/^(observation_date|DATE)$/i.test(header[0] ?? '') || header[1] !== id) throw new Error(`FRED returned an unexpected file for ${id}.`);
  const history: Array<[string, number]> = [];
  for (const line of lines.slice(1)) {
    const [date, raw = ''] = line.split(',');
    const value = raw.trim() && raw.trim() !== '.' ? Number(raw) : NaN;
    if (Number.isFinite(value) && /^\d{4}-\d{2}-\d{2}$/.test(date)) history.push([date, value]);
  }
  return history;
}

export function macroPoint(series: typeof MACRO_SERIES[number], history: Array<[string, number]>): MacroPoint {
  const last = history.at(-1), prior = history.at(-2);
  return { ...series, date: last?.[0] ?? null, value: last?.[1] ?? null, previous: prior?.[1] ?? null,
    change: last && prior ? last[1] - prior[1] : null, history: history.slice(-260) };
}

/** One request per series: FRED answers a mixed-frequency multi-series request with a zip file. */
export async function fetchMacro(fetcher: Fetch, now = new Date()): Promise<MacroPoint[]> {
  const start = new Date(now.getTime() - 400 * 86_400_000).toISOString().slice(0, 10);
  return Promise.all(MACRO_SERIES.map(async series => {
    try {
      const response = await fetcher(`https://fred.stlouisfed.org/graph/fredgraph.csv?id=${series.id}&cosd=${start}`, { method: 'GET',
        headers: { Accept: 'text/csv', 'User-Agent': 'QuantEngine/0.3 (+https://github.com/purysho/QuantEngine)' }, signal: AbortSignal.timeout(30_000) });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return macroPoint(series, parseSeries(await response.text(), series.id));
    } catch { return macroPoint(series, []); }
  }));
}
