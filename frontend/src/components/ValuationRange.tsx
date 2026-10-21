import { Dices, Play } from 'lucide-react';
import { useState } from 'react';
import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api } from '../lib/api';
import { fmtCompact, fmtMoney, fmtNum, fmtPct, isNum } from '../lib/format';
import { useSettings } from '../lib/settings';
import { loadRaw, save } from '../lib/storage';
import type { DCFModel } from '../lib/types';
import { useAsync, useDebounced } from '../lib/useApi';
import { C, ChartTooltip, axisProps, gridProps } from './charts';
import { Badge, Callout, Card, ErrorBox, Field, Kpi, NumberField } from './ui';

type Output = 'value_per_share' | 'equity_value';
const avg = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;

export function useMarketPrice() {
  const [price, setPrice] = useState<number | null>(() => loadRaw<{ price: number | null }>('fis.dcf.market', { price: null }).price);
  return [price, (p: number | null) => { setPrice(p); save('fis.dcf.market', { price: p }); }] as const;
}

interface Reverse { variable: string; variable_label: string; implied: number | null; base_value: number; base_output: number | null; target: number; curve: { x: number; value: number | null }[]; message: string; notes: string[] }

/** "What is the market expecting?" — solves one assumption so the DCF equals the market price. */
export function ReverseDCF({ model, price, setPrice }: { model: DCFModel; price: number | null; setPrice: (p: number | null) => void }) {
  const { settings } = useSettings();
  const cur = settings.currency;
  const [variable, setVariable] = useState('revenue_growth');
  const output: Output = model.shares_outstanding ? 'value_per_share' : 'equity_value';
  const options = [['revenue_growth', 'Revenue growth'], ['ebit_margin', 'EBIT margin'], ['wacc', 'WACC'],
    ...(model.terminal_method === 'gordon' ? [['terminal_growth', 'Terminal growth']] : [['exit_multiple', 'Exit multiple']])];
  const v = options.some(([k]) => k === variable) ? variable : 'revenue_growth';
  const req = useDebounced(isNum(price) && price > 0 ? { model, target: price, variable: v, output } : null, 300);
  const res = useAsync(() => api.post<Reverse>('/api/finance/dcf/reverse', req), [JSON.stringify(req)], !!req);
  const r = req ? res.data : null;
  const isMult = v === 'exit_multiple';
  const fmtX = (x: number | null) => (isNum(x) ? (isMult ? `${fmtNum(x, 1)}×` : fmtPct(x, 1)) : '—');

  return (
    <Card title="Reverse DCF — what is the market expecting?" subtitle="Enter today's market price; the app finds the assumption that makes your DCF equal to it">
      <div className="grid cols-2" style={{ gap: 12 }}>
        <NumberField label={output === 'value_per_share' ? 'Market price per share' : 'Market value of equity'} value={price} onChange={setPrice} min={0}
          hint={output === 'equity_value' ? 'Add shares outstanding to work per share' : 'Same currency as the model'} />
        <Field label="Solve for">
          <select className="input" value={v} onChange={(e) => setVariable(e.target.value)}>
            {options.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </Field>
      </div>
      {!req && <p className="faint mt-sm" style={{ fontSize: 13 }}>Enter a market price to see the growth (or margin, or WACC) that the price assumes.</p>}
      {req && res.error && <div className="mt-sm"><ErrorBox error={res.error} /></div>}
      {r && (
        <div className="stack mt" style={{ gap: 12 }}>
          <div className="grid cols-3">
            <Kpi label={`Implied ${r.variable_label.toLowerCase()}`} value={fmtX(r.implied)} delta={r.implied === null ? <Badge tone="warn">No solution in range</Badge> : undefined} />
            <Kpi label="Your assumption" value={fmtX(r.base_value)} />
            <Kpi label={output === 'value_per_share' ? 'Your DCF value per share' : 'Your DCF equity value'} value={fmtMoney(r.base_output, cur, output === 'value_per_share' ? 2 : 0)} />
          </div>
          <Callout tone={r.implied === null ? 'warn' : 'info'}>{r.message} {r.notes.join(' ')}</Callout>
          <div style={{ height: 220 }}>
            <ResponsiveContainer>
              <LineChart data={r.curve} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="x" type="number" domain={['dataMin', 'dataMax']} {...axisProps} tickFormatter={(x) => fmtX(x)} />
                <YAxis {...axisProps} width={60} tickFormatter={(y) => fmtCompact(y, cur)} />
                <Tooltip content={<ChartTooltip format={(y) => fmtMoney(y, cur, 2)} labelFormat={(l) => `${r.variable_label}: ${fmtX(Number(l))}`} />} />
                <ReferenceLine y={r.target} stroke={C.neg} strokeDasharray="4 4" label={{ value: 'Market', fill: 'var(--text-muted)', fontSize: 11, position: 'insideTopRight' }} />
                {isNum(r.implied) && <ReferenceLine x={r.implied} stroke={C.c1} strokeDasharray="4 4" />}
                <Line dataKey="value" name="DCF value" stroke={C.c2} dot={false} strokeWidth={2} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </Card>
  );
}

interface DistRow { variable: string; label: string; on: boolean; kind: 'normal' | 'triangular' | 'uniform'; a: number | null; b: number | null; c: number | null; percent: boolean }
interface MC {
  output: string; simulations: number; valid: number; invalid: number; seed: number; base_output: number | null; mean: number | null; std: number | null;
  percentiles: Record<string, number>; histogram: { from: number; to: number; count: number }[]; prob_above_target: number | null; target: number | null; notes: string[];
}

function defaults(m: DCFModel): DistRow[] {
  const g = avg(m.revenue_growth), em = avg(m.ebit_margin);
  return [
    { variable: 'revenue_growth', label: 'Revenue growth', on: true, kind: 'normal', a: g, b: 0.02, c: null, percent: true },
    { variable: 'ebit_margin', label: 'EBIT margin', on: true, kind: 'triangular', a: em - 0.03, b: em, c: em + 0.02, percent: true },
    { variable: 'wacc', label: 'WACC', on: true, kind: 'normal', a: m.wacc, b: 0.01, c: null, percent: true },
    m.terminal_method === 'gordon'
      ? { variable: 'terminal_growth', label: 'Terminal growth', on: true, kind: 'uniform', a: m.terminal_growth - 0.01, b: m.terminal_growth + 0.01, c: null, percent: true }
      : { variable: 'exit_multiple', label: 'Exit multiple', on: true, kind: 'triangular', a: (m.exit_multiple ?? 10) * 0.75, b: m.exit_multiple ?? 10, c: (m.exit_multiple ?? 10) * 1.25, percent: false },
  ];
}
const PARAM_LABELS = { normal: ['Average', 'Std. deviation', ''], triangular: ['Low', 'Most likely', 'High'], uniform: ['Low', 'High', ''] } as const;

/** Monte Carlo: thousands of DCFs with uncertain assumptions, giving a range instead of one number. */
export function MonteCarlo({ model, price }: { model: DCFModel; price: number | null }) {
  const { settings } = useSettings();
  const cur = settings.currency;
  const [rows, setRows] = useState<DistRow[]>(() => defaults(model));
  const [n, setN] = useState<number | null>(5000);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [r, setR] = useState<MC | null>(null);
  const output: Output = model.shares_outstanding ? 'value_per_share' : 'equity_value';
  const money = (v: number | null | undefined) => fmtMoney(v, cur, output === 'value_per_share' ? 2 : 0);
  const set = (i: number, p: Partial<DistRow>) => setRows(rows.map((x, j) => (j === i ? { ...x, ...p } : x)));

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const distributions = rows.filter((x) => x.on).map((x) => ({ variable: x.variable, kind: x.kind, a: x.a, b: x.b, c: x.kind === 'triangular' ? x.c : null }));
      if (distributions.some((d) => !isNum(d.a) || !isNum(d.b) || (d.kind === 'triangular' && !isNum(d.c)))) throw new Error('Fill in every parameter for the assumptions you turned on.');
      setR(await api.post<MC>('/api/finance/dcf/monte-carlo', { model, distributions, output, simulations: n ?? 5000, seed: 42, target: isNum(price) ? price : null }));
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };

  const hist = r?.histogram.map((h) => ({ mid: (h.from + h.to) / 2, count: h.count, label: `${money(h.from)} – ${money(h.to)}` })) ?? [];

  return (
    <Card title="Valuation range (Monte Carlo)" subtitle="Runs the DCF thousands of times with uncertain assumptions, so you see a range of values instead of one number"
      actions={<button className="btn primary" onClick={run} disabled={busy}><Play size={15} />{busy ? 'Running…' : 'Run simulation'}</button>}>
      <div className="table-wrap">
        <table className="data">
          <thead><tr><th>Uncertain?</th><th>Assumption</th><th>Distribution</th><th>Parameters</th></tr></thead>
          <tbody>{rows.map((x, i) => {
            const labels = PARAM_LABELS[x.kind];
            return (
              <tr key={x.variable}>
                <td><input type="checkbox" aria-label={`Vary ${x.label}`} checked={x.on} onChange={(e) => set(i, { on: e.target.checked })} /></td>
                <td>{x.label}</td>
                <td><select className="input compact" aria-label={`${x.label} distribution`} value={x.kind} onChange={(e) => set(i, { kind: e.target.value as DistRow['kind'] })}>
                  <option value="normal">Normal</option><option value="triangular">Triangular</option><option value="uniform">Uniform</option></select></td>
                <td><div className="row" style={{ gap: 6, flexWrap: 'nowrap' }}>
                  {(['a', 'b', 'c'] as const).map((k, j) => labels[j] ? (
                    <div key={k} style={{ width: 104 }}><NumberField compact ariaLabel={`${x.label} ${labels[j]}`} percent={x.percent}
                      value={x[k]} onChange={(v) => set(i, { [k]: v })} /><div className="faint" style={{ fontSize: 11 }}>{labels[j]}</div></div>) : null)}
                </div></td>
              </tr>
            );
          })}</tbody>
        </table>
      </div>
      <div className="row mt-sm" style={{ gap: 12 }}>
        <div style={{ width: 180 }}><NumberField label="Simulations" value={n} onChange={setN} min={100} max={20000} /></div>
        <button className="btn" onClick={() => setRows(defaults(model))}><Dices size={15} />Reset ranges from model</button>
      </div>
      {error && <div className="mt-sm"><ErrorBox error={error} /></div>}
      {r && (
        <div className="stack mt" style={{ gap: 12 }}>
          <div className="grid cols-4">
            <Kpi label="Pessimistic (P10)" value={money(r.percentiles.p10)} />
            <Kpi label="Middle (P50)" value={money(r.percentiles.p50)} />
            <Kpi label="Optimistic (P90)" value={money(r.percentiles.p90)} />
            <Kpi label={isNum(r.target) ? 'Chance value > market price' : 'Your base case'} value={isNum(r.prob_above_target) ? fmtPct(r.prob_above_target, 0) : money(r.base_output)} />
          </div>
          <Callout tone="info">In 80% of the {r.valid.toLocaleString()} valid runs the value was between <b>{money(r.percentiles.p10)}</b> and <b>{money(r.percentiles.p90)}</b>.
            {isNum(r.prob_above_target) && <> The value was above the market price in {fmtPct(r.prob_above_target, 0)} of runs.</>}</Callout>
          <div style={{ height: 230 }}>
            <ResponsiveContainer>
              <BarChart data={hist} margin={{ top: 8, right: 12, left: 0, bottom: 0 }} barCategoryGap={1}>
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="mid" type="number" domain={['dataMin', 'dataMax']} {...axisProps} tickFormatter={(x) => fmtCompact(x, cur)} />
                <YAxis {...axisProps} width={44} />
                <Tooltip cursor={{ fill: 'var(--bg-hover)' }} content={<ChartTooltip format={(v) => `${v} runs`} labelFormat={(l) => hist.find((h) => h.mid === Number(l))?.label ?? ''} />} />
                {isNum(r.target) && <ReferenceLine x={r.target} stroke={C.neg} strokeDasharray="4 4" label={{ value: 'Market', fill: 'var(--text-muted)', fontSize: 11, position: 'insideTopRight' }} />}
                <Bar dataKey="count" name="Runs" fill={C.c1} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          {r.notes.map((t) => <p key={t} className="faint" style={{ fontSize: 12.5 }}>{t}</p>)}
        </div>
      )}
    </Card>
  );
}
