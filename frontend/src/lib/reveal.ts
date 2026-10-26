/**
 * Turn an uploaded file into (1) the data the parser extracted and (2) the calculations the app's
 * existing engines can run on it. No finance formula lives here: every result comes from an API
 * engine (/api/finance/statements, /ratios, /variance, /forecast). This module only chooses which
 * inputs to send, and formats what comes back with the app's formatters.
 */
import { api } from './api';
import { fmtNum, fmtPctPoints, fmtRatio, isNum } from './format';

export type Stmt = 'income' | 'balance' | 'cashflow';
export interface Series { id: string; label: string; orientation: 'row' | 'column'; values: number[]; refs: string[]; period_labels: string[]; calculated_values?: number }
export interface SheetData {
  name: string; n_rows: number; n_cols: number; header_row: number | null;
  columns: { index: number; letter: string; name: string; dtype: string; number_format?: string }[];
  series?: Series[]; warnings: string[];
}
export interface Mapping { item: string; item_label: string; source_label: string; value: number; source: string; period: string; prior_value: number | null; prior_source: string | null; prior_period: string | null }
export interface SuggestedStatement { sheet: string; statement: Stmt; periods: string[]; reordered: boolean; lines: { label: string; key: string | null; values: (number | null)[]; source: string | null }[] }
export interface VarianceSuggestion { sheet: string; budget_column: string; actual_column: string; lines: { name: string; kind: 'revenue' | 'expense'; budget: number; actual: number; source: string }[]; note: string }
export interface Recommendation { module: string; route: string; reason: string; confidence: string }
export interface ScreenerLine { label: string; statement: Stmt; key: string | null; values: (number | null)[]; source?: string | null }
export interface ScreenerImport { company: string | null; periods: string[]; units: string; lines: ScreenerLine[]; approximations: Record<string, ScreenerLine>; notes: string[] }

/** One input line for the engines. `refs` are cell references per period when the parser knows them. */
export interface InLine {
  label: string; statement: Stmt; key: string | null; values: (number | null)[]; refs: (string | null)[] | null;
  sheet: string | null; source: string | null; kind: 'reported' | 'derived' | 'approximation';
}
export interface EngineInput { periods: string[]; lines: InLine[] }

export interface CalcRow { metric: string; formula: string; substituted: string; result: string; unit: string; source: string; note?: string }
export interface Block {
  id: string; title: string; route: string | null; status: 'ok' | 'gap' | 'skipped' | 'error';
  rows: CalcRow[]; message?: string; more?: number;
}

export const MAX_ROWS = 12;
// Balance-sheet items the ratio engine averages when an opening (prior) value is supplied.
const AVERAGEABLE = new Set(['receivables', 'inventory', 'total_assets', 'accounts_payable', 'total_equity', 'total_debt']);

// ---------------------------------------------------------------- mapping certainty

const norm = (s: string) => s.toLowerCase().replace(/&/g, ' and ').replace(/[^a-z0-9 ]/g, ' ').replace(/\s+/g, ' ').trim().replace(/^total /, '');

/** A label that is the engine item's own name (e.g. "Revenue", "Total assets") is reported as-is; one
 * matched through a synonym (e.g. "Total income" → Revenue) is a suggestion the user must confirm. */
export function isExactMatch(sourceLabel: string, ...itemLabels: string[]): boolean {
  const a = norm(sourceLabel);
  return itemLabels.some((l) => [l, l.replace(/\(.*?\)/g, ''), ...(l.match(/\(([^)]+)\)/g) ?? []).map((x) => x.slice(1, -1))]
    .map(norm).filter(Boolean).includes(a));
}

export type Decision = 'confirmed' | 'rejected';
export interface MapRow {
  key: string; itemLabel: string; sourceLabel: string; value: number | null; prior: number | null; period: string | null;
  cell: string | null; sheet: string | null; certainty: 'reported' | 'suggested';
}

/** Mapping rows: the parser's statement_mapping (ratio items) plus statement-only items such as gross profit. */
export function mapRows(statementMapping: Mapping[], statements: SuggestedStatement[], itemLabels: Record<string, string>, sheets: SheetData[] = []): MapRow[] {
  const out: MapRow[] = [];
  for (const m of statementMapping) {
    const [, sheet, cell] = m.source.split(' › ');
    out.push({ key: m.item, itemLabel: m.item_label, sourceLabel: m.source_label, value: m.value, prior: m.prior_value, period: m.period,
      cell: cell ?? null, sheet: sheet ?? null,
      certainty: isExactMatch(m.source_label, m.item_label, itemLabels[m.item] ?? '') ? 'reported' : 'suggested' });
  }
  for (const s of statements) {
    for (const l of s.lines) {
      if (!l.key || out.some((r) => r.key === l.key)) continue;
      const i = lastIndex(l.values);
      const refs = refsFor(sheets, s.sheet, l.label, s.periods);
      out.push({ key: l.key, itemLabel: itemLabels[l.key] ?? l.key, sourceLabel: l.label, value: i >= 0 ? l.values[i] : null,
        prior: i > 0 ? l.values[i - 1] : null, period: i >= 0 ? s.periods[i] : null, cell: i >= 0 ? refs?.[i] ?? null : null, sheet: s.sheet,
        certainty: isExactMatch(l.label, itemLabels[l.key] ?? '') ? 'reported' : 'suggested' });
    }
  }
  return out;
}

export function accepted(row: MapRow | undefined, decisions: Record<string, Decision>): boolean {
  if (!row) return false;
  const d = decisions[row.key];
  return d === 'confirmed' || (d !== 'rejected' && row.certainty === 'reported');
}

// ---------------------------------------------------------------- engine inputs

const lastIndex = (vs: (number | null)[]) => { for (let i = vs.length - 1; i >= 0; i--) if (isNum(vs[i])) return i; return -1; };

/** Cell references per period for a statement line, looked up in the parser's row series. */
function refsFor(sheets: SheetData[], sheet: string, label: string, periods: string[]): (string | null)[] | null {
  const s = sheets.find((x) => x.name === sheet)?.series?.find((x) => x.orientation === 'row' && x.label === label.trim());
  if (!s) return null;
  return periods.map((p) => { const i = s.period_labels.indexOf(p); return i >= 0 ? s.refs[i] : null; });
}

/** Engine input from the parser's statement suggestions. Keys of rejected or unconfirmed mappings are dropped. */
export function inputFromUpload(statements: SuggestedStatement[], sheets: SheetData[], rows: MapRow[], decisions: Record<string, Decision>): EngineInput {
  const periods: string[] = [];
  statements.forEach((s) => s.periods.forEach((p) => { if (!periods.includes(p)) periods.push(p); }));
  const used = new Set<string>();
  const lines: InLine[] = statements.flatMap((s) => s.lines.map((l) => {
    const ok = l.key && !used.has(l.key) && accepted(rows.find((r) => r.key === l.key), decisions);
    const key = ok ? l.key : null;
    if (key) used.add(key);
    const own = refsFor(sheets, s.sheet, l.label, s.periods);
    return { label: l.label, statement: s.statement, key, kind: 'reported' as const, sheet: s.sheet, source: l.source,
      values: periods.map((p) => { const i = s.periods.indexOf(p); return i >= 0 ? l.values[i] : null; }),
      refs: own ? periods.map((p) => { const i = s.periods.indexOf(p); return i >= 0 ? own[i] : null; }) : null };
  }));
  return trimPeriods({ periods, lines });
}

/** Engine input from a Screener import: reported and derived lines, plus only the approximations the user opted into. */
export function inputFromScreener(sc: ScreenerImport, optIn: Set<string>): EngineInput {
  const kindOf = (l: ScreenerLine): InLine['kind'] => (l.source === 'derived' ? 'derived' : l.source === 'approximation' ? 'approximation' : 'reported');
  const lines = [...sc.lines, ...Object.entries(sc.approximations).filter(([k]) => optIn.has(k)).map(([, l]) => l)]
    .map((l) => ({ label: l.label, statement: l.statement, key: l.key, values: l.values, refs: null, sheet: 'Data Sheet',
      source: l.source ?? null, kind: kindOf(l) }));
  return trimPeriods({ periods: sc.periods, lines });
}

/** Engine input from statement data saved on the Financial Statements page (company dashboard). */
export function inputFromStatements(d: { periods: string[]; lines: { label: string; statement: string; key: string | null; values: (number | null)[]; source?: string | null }[] }): EngineInput {
  return trimPeriods({ periods: d.periods, lines: d.lines.map((l) => ({
    label: l.label, statement: l.statement as Stmt, key: l.key, values: l.values, refs: null, sheet: null, source: l.source ?? null,
    kind: l.source === 'derived' || /\(derived/i.test(l.label) ? 'derived' : l.source === 'approximation' || /\(approx/i.test(l.label) ? 'approximation' : 'reported',
  })) });
}

/** The statements endpoint accepts up to 20 periods; the latest 20 are kept. */
function trimPeriods(e: EngineInput): EngineInput {
  if (e.periods.length <= 20) return e;
  const k = e.periods.length - 20;
  return { periods: e.periods.slice(k), lines: e.lines.map((l) => ({ ...l, values: l.values.slice(k), refs: l.refs?.slice(k) ?? null })) };
}

// ---------------------------------------------------------------- formatting

const num = (v: number | null | undefined) => (isNum(v) ? fmtNum(v, Math.abs(v) >= 1000 || Number.isInteger(v) ? 0 : 2) : '—');
const pct = (v: number | null | undefined) => fmtPctPoints(v, 1);

function cellSource(l: InLine | undefined, ...idx: number[]): string {
  if (!l) return '—';
  const refs = idx.map((i) => l.refs?.[i]).filter(Boolean);
  if (l.kind === 'derived') return `Derived · ${l.source && l.source !== 'derived' ? l.source : l.label}`;
  if (refs.length) return `${l.sheet ?? ''} · ${refs.join(' / ')}`.replace(/^ · /, '');
  return l.source ?? l.label;
}

// ---------------------------------------------------------------- statements engine

interface StatementReport {
  periods: string[];
  lines: { label: string; key: string | null; values: (number | null)[]; changes: ({ absolute: number | null; pct: number | null; note: string | null } | null)[]; common_size: (number | null)[] }[];
  metrics: Record<string, (number | null)[]>;
  checks: { name: string; period: string; status: 'pass' | 'fail' | 'insufficient'; difference: number | null; detail: string }[];
}

const HORIZONTAL = ['revenue', 'gross_profit', 'operating_income', 'net_income', 'total_assets', 'total_equity', 'operating_cash_flow'];
const COMMON_INCOME = ['cogs', 'operating_expenses', 'sga', 'employee_cost', 'interest_expense', 'income_tax'];
const COMMON_BALANCE = ['receivables', 'inventory', 'current_assets', 'total_debt', 'total_equity'];

async function runStatements(inp: EngineInput, signal?: AbortSignal): Promise<{ report: StatementReport | null; error?: string }> {
  try {
    const report = await api.post<StatementReport>('/api/finance/statements', {
      periods: inp.periods, lines: inp.lines.map((l) => ({ label: l.label.slice(0, 160), statement: l.statement, key: l.key, values: l.values, source: l.source?.slice(0, 400) ?? null })),
    }, { signal });
    return { report };
  } catch (e) {
    return { report: null, error: (e as Error).message };
  }
}

function statementsBlock(inp: EngineInput, rep: StatementReport, route: string | null): Block {
  const rows: CalcRow[] = [];
  const n = rep.periods.length, last = n - 1, prev = n - 2;
  const P = rep.periods;
  const line = (k: string) => inp.lines.find((l) => l.key === k);
  const at = (k: string, i: number) => line(k)?.values[i] ?? null;
  const ix = (k: string) => inp.lines.findIndex((l) => l.key === k);

  if (n >= 2) {
    for (const k of HORIZONTAL) {
      const i = ix(k);
      const ch = i >= 0 ? rep.lines[i]?.changes[last] : null;
      const cur = at(k, last), pri = at(k, prev);
      if (!ch || !isNum(cur) || !isNum(pri)) continue;
      rows.push({ metric: `${inp.lines[i].label}: change ${P[prev]} → ${P[last]}`, formula: '(Current − Prior) / |Prior| × 100',
        substituted: `(${num(cur)} − ${num(pri)}) / ${num(Math.abs(pri))} × 100`, result: isNum(ch.pct) ? pct(ch.pct) : 'Not meaningful',
        unit: '%', source: cellSource(inp.lines[i], prev, last), note: ch.note ?? undefined });
    }
  }

  const margin = (key: string, metric: string, numKey: string, numLabel: string, derived?: { rule: string; value: (i: number) => number | null }) => {
    const v = rep.metrics[key]?.[last];
    if (!isNum(v)) return;
    const rev = at('revenue', last);
    const direct = at(numKey, last);
    const numerator = isNum(direct) ? direct : derived?.value(last) ?? null;
    if (!isNum(numerator) || !isNum(rev)) return;
    const prior = n >= 2 ? rep.metrics[key]?.[prev] : null;
    rows.push({ metric: `${metric} ${P[last]}`, formula: `${isNum(direct) ? numLabel : derived?.rule ?? numLabel} / Revenue × 100`,
      substituted: `${num(numerator)} / ${num(rev)} × 100`, result: `${pct(v)}${isNum(prior) ? ` (${P[prev]}: ${pct(prior)})` : ''}`, unit: '%',
      source: isNum(direct) ? cellSource(line(numKey), last) + ' / ' + cellSource(line('revenue'), last).split(' · ').pop()
        : `Derived: ${derived?.rule} · ${cellSource(line('revenue'), last)}`,
      note: isNum(direct) ? undefined : `Derived: ${numLabel.toLowerCase()} = ${derived?.rule.toLowerCase()}` });
  };
  margin('gross_margin_pct', 'Gross margin', 'gross_profit', 'Gross profit',
    { rule: '(Revenue − COGS)', value: (i) => (isNum(at('revenue', i)) && isNum(at('cogs', i)) ? (at('revenue', i) as number) - (at('cogs', i) as number) : null) });
  margin('operating_margin_pct', 'Operating margin', 'operating_income', 'Operating income (EBIT)');
  margin('ebitda_margin_pct', 'EBITDA margin', 'ebitda', 'EBITDA',
    { rule: '(EBIT + D&A)', value: (i) => (isNum(at('operating_income', i)) && isNum(at('depreciation_amortization', i)) ? (at('operating_income', i) as number) + (at('depreciation_amortization', i) as number) : null) });
  margin('net_margin_pct', 'Net margin', 'net_income', 'Net income');

  const common = (keys: string[], baseKey: string, baseLabel: string) => {
    for (const k of keys) {
      const i = ix(k);
      const v = i >= 0 ? rep.lines[i]?.common_size[last] : null;
      if (!isNum(v)) continue;
      const prior = n >= 2 ? rep.lines[i].common_size[prev] : null;
      rows.push({ metric: `${inp.lines[i].label} as % of ${baseLabel.toLowerCase()}, ${P[last]}`, formula: `${inp.lines[i].label} / ${baseLabel} × 100`,
        substituted: `${num(at(k, last))} / ${num(at(baseKey, last))} × 100`, result: `${pct(v)}${isNum(prior) ? ` (${P[prev]}: ${pct(prior)})` : ''}`,
        unit: '%', source: `${cellSource(inp.lines[i], last)} / ${cellSource(line(baseKey), last).split(' · ').pop()}` });
    }
  };
  common(COMMON_INCOME, 'revenue', 'Revenue');
  common(COMMON_BALANCE, 'total_assets', 'Total assets');

  for (const c of rep.checks.filter((c) => c.status !== 'insufficient' && c.period === P[last])) {
    rows.push({ metric: `Check: ${c.name} (${c.period})`, formula: c.name, substituted: c.detail, unit: '—', source: 'Statement lines above',
      result: c.status === 'pass' ? 'Pass' : `Fails by ${num(c.difference)}` });
  }

  if (!rows.length) {
    const missing = n < 2 ? 'a second period (for changes)' : 'revenue or total assets mapped to a standard item (for margins and common-size)';
    return { id: 'statements', title: 'Financial statements', route, status: 'gap', rows: [], message: `Missing: ${missing}.` };
  }
  return { id: 'statements', title: 'Financial statements', route, status: 'ok', rows: rows.slice(0, MAX_ROWS), more: Math.max(0, rows.length - MAX_ROWS) };
}

function cashBlock(inp: EngineInput, rep: StatementReport, route: string | null): Block {
  const rows: CalcRow[] = [];
  const last = rep.periods.length - 1, P = rep.periods;
  const line = (k: string) => inp.lines.find((l) => l.key === k);
  const at = (k: string) => line(k)?.values[last] ?? null;
  const fcf = rep.metrics.free_cash_flow?.[last];
  if (isNum(fcf) && isNum(at('operating_cash_flow')) && isNum(at('capex'))) {
    rows.push({ metric: `Free cash flow ${P[last]}`, formula: 'Operating cash flow − |Capital expenditure|',
      substituted: `${num(at('operating_cash_flow'))} − ${num(Math.abs(at('capex') as number))}`, result: num(fcf), unit: 'amount',
      source: `${cellSource(line('operating_cash_flow'), last)} / ${cellSource(line('capex'), last).split(' · ').pop()}` });
  }
  const conv = rep.metrics.cash_conversion?.[last];
  if (isNum(conv)) {
    rows.push({ metric: `Cash conversion ${P[last]}`, formula: 'Operating cash flow / Net income', substituted: `${num(at('operating_cash_flow'))} / ${num(at('net_income'))}`,
      result: `${fmtNum(conv, 2)}×`, unit: '×', source: `${cellSource(line('operating_cash_flow'), last)} / ${cellSource(line('net_income'), last).split(' · ').pop()}` });
  }
  for (const c of rep.checks.filter((c) => /cash/i.test(c.name) && c.status !== 'insufficient' && c.period === P[last])) {
    rows.push({ metric: `Check: ${c.name} (${c.period})`, formula: c.name, substituted: c.detail, unit: '—', source: 'Cash flow lines', result: c.status === 'pass' ? 'Pass' : `Fails by ${num(c.difference)}` });
  }
  if (!rows.length) {
    const miss = ['operating_cash_flow', 'capex', 'net_income'].filter((k) => !isNum(at(k)));
    return { id: 'cash', title: 'Cash flow', route, status: 'gap', rows: [], message: `Missing: ${miss.map(labelOf).join(', ')}. Working-capital targets (target DSO/DIO/DPO) are set on the full page.` };
  }
  return { id: 'cash', title: 'Cash flow', route, status: 'ok', rows,
    message: 'Working-capital release needs your target days, so it is not run here.' };
}

// ---------------------------------------------------------------- ratio engine

interface Ratio { key: string; name: string; category: string; formula: string; unit: string; value: number | null; status: 'ok' | 'missing' | 'undefined'; inputs: Record<string, number>; steps: string; notes: string[]; missing: string[] }

export function ratioData(inp: EngineInput): { data: Record<string, number>; sources: Record<string, string> } {
  const data: Record<string, number> = {}, sources: Record<string, string> = {};
  for (const l of inp.lines) {
    if (!l.key || l.key in data) continue;
    const i = lastIndex(l.values);
    if (i < 0) continue;
    data[l.key] = l.values[i] as number;
    sources[l.key] = `${cellSource(l, i)} (${inp.periods[i]})`;
    if (AVERAGEABLE.has(l.key) && i > 0 && isNum(l.values[i - 1])) {
      data[`${l.key}_prior`] = l.values[i - 1] as number;
      sources[`${l.key}_prior`] = `${cellSource(l, i - 1)} (${inp.periods[i - 1]})`;
    }
  }
  return { data, sources };
}

const RATIO_ITEMS = new Set(['revenue', 'cogs', 'operating_income', 'depreciation_amortization', 'interest_expense', 'net_income', 'operating_cash_flow', 'cash',
  'marketable_securities', 'receivables', 'inventory', 'current_assets', 'total_assets', 'current_liabilities', 'accounts_payable', 'total_debt',
  'total_liabilities', 'total_equity', 'tax_rate', 'debt_service', 'shares_outstanding', 'share_price']);

async function ratiosBlock(data: Record<string, number>, sources: Record<string, string>, route: string | null, signal?: AbortSignal): Promise<Block> {
  const body = Object.fromEntries(Object.entries(data).filter(([k]) => RATIO_ITEMS.has(k.replace(/_prior$/, ''))));
  if (!Object.keys(body).length) return { id: 'ratios', title: 'Ratios', route, status: 'gap', rows: [], message: 'Missing: no line mapped to a ratio input (revenue, net income, total assets…).' };
  let ratios: Ratio[];
  try {
    ratios = (await api.post<{ ratios: Ratio[] }>('/api/finance/ratios', { data: body, period_days: 365 }, { signal })).ratios;
  } catch (e) {
    return { id: 'ratios', title: 'Ratios', route, status: 'error', rows: [], message: (e as Error).message };
  }
  const src = (r: Ratio) => [...new Set(Object.keys(r.inputs).map((k) => {
    const base = k.replace(/^average /, '').replace(/ \((closing|opening)\)$/, '');
    return sources[k.includes('(opening)') ? `${base}_prior` : base] ?? sources[base];
  }).filter(Boolean))].join('; ') || '—';
  const ok = ratios.filter((r) => r.status === 'ok' && isNum(r.value)).map((r): CalcRow => ({
    metric: r.name, formula: r.formula, substituted: r.steps.replace(/\s=\s[^=]*$/, ''), result: fmtRatio(r.value, r.unit),
    unit: r.unit === 'x' ? '×' : r.unit, source: src(r), note: r.notes[0] }));
  const undef = ratios.filter((r) => r.status === 'undefined').map((r): CalcRow => ({
    metric: r.name, formula: r.formula, substituted: '—', result: 'Not meaningful', unit: r.unit === 'x' ? '×' : r.unit, source: src(r), note: r.notes[0] }));
  const missing = ratios.filter((r) => r.status === 'missing');
  const fields = [...new Set(missing.flatMap((r) => r.missing))];
  const rows = [...ok, ...undef];
  const gap = missing.length ? `${missing.length} ratio(s) not calculated. Missing: ${fields.join(', ')}.` : undefined;
  if (!rows.length) return { id: 'ratios', title: 'Ratios', route, status: 'gap', rows: [], message: gap };
  return { id: 'ratios', title: 'Ratios', route, status: 'ok', rows: rows.slice(0, MAX_ROWS), more: Math.max(0, rows.length - MAX_ROWS), message: gap };
}

// ---------------------------------------------------------------- variance and forecast

async function varianceBlock(v: VarianceSuggestion, route: string | null, signal?: AbortSignal): Promise<Block> {
  try {
    const r = await api.post<{ lines: { name: string; kind: string; budget: number; actual: number; variance: number; variance_pct: number | null; status: string; source: string | null }[] }>(
      '/api/finance/variance', { lines: v.lines.map((l) => ({ name: l.name.slice(0, 120), kind: l.kind, budget: l.budget, actual: l.actual, source: l.source })) }, { signal });
    const lines = [...r.lines].sort((a, b) => Math.abs(b.variance) - Math.abs(a.variance));
    const rows = lines.map((l): CalcRow => ({
      metric: `${l.name} (${l.kind})`, formula: 'Actual − Budget', substituted: `${num(l.actual)} − ${num(l.budget)}`,
      result: `${num(l.variance)}${isNum(l.variance_pct) ? ` (${pct(l.variance_pct)})` : ''} · ${l.status.replace('_', ' ')}`, unit: 'amount', source: l.source ?? '—' }));
    return { id: 'variance', title: 'Variance (budget vs actual)', route, status: 'ok', rows: rows.slice(0, MAX_ROWS), more: Math.max(0, rows.length - MAX_ROWS), message: v.note };
  } catch (e) {
    return { id: 'variance', title: 'Variance (budget vs actual)', route, status: 'error', rows: [], message: (e as Error).message };
  }
}

async function forecastBlock(inp: EngineInput, route: string | null, signal?: AbortSignal): Promise<Block> {
  const l = inp.lines.find((x) => x.key === 'revenue');
  const title = 'Forecast (revenue, linear trend)';
  if (!l) return { id: 'forecast', title, route, status: 'gap', rows: [], message: 'Missing: a revenue line mapped to Revenue.' };
  const first = l.values.findIndex(isNum), last = lastIndex(l.values);
  const vals = first >= 0 ? l.values.slice(first, last + 1) : [];
  if (vals.length < 3) return { id: 'forecast', title, route, status: 'gap', rows: [], message: `Missing: at least 3 periods of revenue (found ${vals.length}).` };
  if (vals.some((v) => !isNum(v))) return { id: 'forecast', title, route, status: 'gap', rows: [], message: 'Missing: revenue has blank periods in between; blanks are not treated as zero.' };
  try {
    const r = await api.post<{ forecast: number[]; lower: (number | null)[]; upper: (number | null)[]; confidence: number; backtest: { mape: number | null; holdout: number } }>(
      '/api/finance/forecast', { series: vals, method: 'linear', horizon: 1 }, { signal });
    const P = inp.periods;
    const rows: CalcRow[] = [{ metric: 'Revenue, next period', formula: 'Least-squares trend a + b·t, extended one period', substituted: `Fitted on ${P[first]}–${P[last]} (${vals.length} values)`,
      result: num(r.forecast[0]), unit: 'amount', source: cellSource(l, first, last) }];
    if (isNum(r.lower[0]) && isNum(r.upper[0])) rows.push({ metric: `${Math.round(r.confidence * 100)}% prediction interval`, formula: 'Forecast ± t × standard error of prediction',
      substituted: `${num(r.forecast[0])} ± ${num(((r.upper[0] as number) - (r.lower[0] as number)) / 2)}`, result: `${num(r.lower[0])} to ${num(r.upper[0])}`, unit: 'amount', source: cellSource(l, first, last) });
    if (isNum(r.backtest.mape)) rows.push({ metric: 'Backtest error (MAPE)', formula: 'Mean |actual − forecast| / |actual| × 100 on held-out periods',
      substituted: `Last ${r.backtest.holdout} period(s) held out`, result: pct(r.backtest.mape), unit: '%', source: cellSource(l, last) });
    return { id: 'forecast', title, route, status: 'ok', rows, message: 'Forecasts are estimates, not guarantees.' };
  } catch (e) {
    return { id: 'forecast', title, route, status: 'error', rows: [], message: (e as Error).message };
  }
}

// ---------------------------------------------------------------- orchestration

const ENGINE_OF: Record<string, string> = {
  'Financial Statements': 'statements', 'Ratio Analysis': 'ratios', 'Cash Flow & Working Capital': 'cash', 'Variance Analysis': 'variance', Forecasting: 'forecast',
};
const SKIP_REASON: Record<string, string> = {
  'Investment Appraisal': 'Not run automatically: choose which row holds the project cash flows and enter your discount rate on the full page.',
  'AI Finance Assistant': 'Not run automatically: AI answers need your consent for each question.',
  'Data & Code Lab': 'Not run: uploaded code is never executed.',
  'Upload & Analyse': 'Open the files inside the archive one by one.',
};

function labelOf(k: string) { return k.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase()); }

/** Run every engine that is recommended or whose inputs exist; list the others as gaps or skips. */
export async function buildBlocks(opts: {
  inp: EngineInput | null; variance: VarianceSuggestion | null; recommendations: Recommendation[]; routeFor: (route: string) => string;
  only?: string[]; signal?: AbortSignal;
}): Promise<Block[]> {
  const { inp, variance, recommendations, routeFor, only, signal } = opts;
  const rec = (engine: string) => recommendations.find((r) => ENGINE_OF[r.module] === engine);
  const route = (engine: string, fallback: string) => routeFor(rec(engine)?.route ?? fallback);
  const want = (engine: string) => !only || only.includes(engine);
  const blocks: Block[] = [];
  const hasKeys = !!inp?.lines.some((l) => l.key);

  let report: StatementReport | null = null;
  if (inp && inp.lines.length && (want('statements') || want('cash'))) {
    const r = await runStatements(inp, signal);
    report = r.report;
    if (r.error && want('statements')) blocks.push({ id: 'statements', title: 'Financial statements', route: route('statements', '/statements'), status: 'error', rows: [], message: r.error });
  }
  if (want('statements')) {
    if (report && inp) blocks.push(statementsBlock(inp, report, route('statements', '/statements')));
    else if (!inp?.lines.length && rec('statements')) blocks.push({ id: 'statements', title: 'Financial statements', route: route('statements', '/statements'), status: 'gap', rows: [],
      message: 'Missing: a statement-shaped table (line items down the first column, years or periods across).' });
  }
  if (want('ratios') && (hasKeys || rec('ratios'))) {
    const { data, sources } = inp ? ratioData(inp) : { data: {}, sources: {} };
    blocks.push(await ratiosBlock(data, sources, route('ratios', '/ratios'), signal));
  }
  const hasCash = !!inp?.lines.some((l) => l.key === 'operating_cash_flow');
  if (want('cash') && (hasCash || rec('cash'))) {
    blocks.push(report && inp ? cashBlock(inp, report, route('cash', '/cash-flow'))
      : { id: 'cash', title: 'Cash flow', route: route('cash', '/cash-flow'), status: 'gap', rows: [], message: 'Missing: cash from operating activities and capital expenditure.' });
  }
  if (want('variance') && (variance?.lines.length || rec('variance'))) {
    blocks.push(variance?.lines.length ? await varianceBlock(variance, route('variance', '/variance'), signal)
      : { id: 'variance', title: 'Variance (budget vs actual)', route: route('variance', '/variance'), status: 'gap', rows: [], message: 'Missing: a line-item column with Budget and Actual columns.' });
  }
  const hasRevenue = !!inp?.lines.some((l) => l.key === 'revenue');
  if (want('forecast') && (hasRevenue || rec('forecast'))) blocks.push(await forecastBlock(inp ?? { periods: [], lines: [] }, route('forecast', '/forecasting'), signal));

  if (!only) {
    for (const r of recommendations) {
      if (ENGINE_OF[r.module]) continue;
      blocks.push({ id: `skip:${r.module}`, title: r.module, route: routeFor(r.route), status: 'skipped', rows: [],
        message: `${r.reason} ${SKIP_REASON[r.module] ?? 'Not run automatically; open the full page to choose its inputs.'}` });
    }
  }
  return blocks;
}

export { num as fmtReveal };
