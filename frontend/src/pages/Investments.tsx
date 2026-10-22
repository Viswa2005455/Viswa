import { Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { CartesianGrid, Line, LineChart, ReferenceDot, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from 'recharts';
import { C, ChartTooltip, axisProps, gridProps } from '../components/charts';
import { SaveLoad } from '../components/SaveLoad';
import { Badge, Callout, Card, ErrorBox, Field, Formula, Kpi, NumberField, PageHeader, Skeleton, Tabs } from '../components/ui';
import { api } from '../lib/api';
import { fmtNum, fmtPct, isNum } from '../lib/format';
import { loadRaw, save } from '../lib/storage';
import { useAsync, useDebounced } from '../lib/useApi';

type Tab = 'bond' | 'equity' | 'portfolio' | 'performance' | 'options';
type N = number | null;

const EXAMPLE = {
  bond: { face: 100 as N, coupon_rate: 0.07 as N, years: 10 as N, freq: 2, mode: 'ytm', ytm: 0.08 as N, price: null as N, shock_bp: 100 as N },
  equity: { model: 'two_stage', d0: 2 as N, d1: null as N, g: 0.05 as N, r: 0.11 as N, g1: 0.15 as N, n: 5 as N, g2: 0.05 as N, fcfe0: 500 as N, shares: 100 as N,
    book_value: 50 as N, roe: 0.16 as N, payout: 0.4 as N, years: 5 as N, terminal_growth: 0.03 as N },
  portfolio: { assets: [{ name: 'Indian equities', weight: 0.6, ret: 0.12, vol: 0.18 }, { name: 'Government bonds', weight: 0.4, ret: 0.07, vol: 0.05 }] as { name: string; weight: N; ret: N; vol: N }[],
    corr: [[1, 0.2], [0.2, 1]] as N[][], risk_free: 0.065 as N },
  performance: { portfolio: '1.2, -0.8, 2.1, 1.5, -0.3, 0.9, 1.8, -1.1, 2.4, 0.6, 0.2, 1.4', benchmark: '1.0, -1.0, 1.8, 1.2, -0.5, 0.8, 1.5, -1.3, 2.0, 0.5, 0.1, 1.1', risk_free: 0.065 as N, periods_per_year: 12 },
  options: { s: 100 as N, k: 100 as N, t: 1 as N, r: 0.05 as N, sigma: 0.2 as N, q: 0 as N, steps: 200 as N, market_call: null as N, market_put: null as N,
    legs: [{ type: 'call', position: 'long', strike: 100 as N, premium: 10.45 as N, quantity: 1 as N }, { type: 'call', position: 'short', strike: 120 as N, premium: 3.25 as N, quantity: 1 as N }] },
};
type Model = typeof EXAMPLE;
const num = (o: Record<string, unknown>, keys: string[]) => keys.every((k) => isNum(o[k]));
const parseList = (s: string) => s.split(/[\s,;]+/).filter(Boolean).map(Number);

export function Investments() {
  const [tab, setTab] = useState<Tab>(() => loadRaw('fis.investments.tab', 'bond'));
  const [state, setState] = useState<{ m: Model; example: boolean }>(() => loadRaw('fis.investments', { m: EXAMPLE, example: true }));
  const m = state.m;
  const set = (p: Partial<Model>) => { const s = { m: { ...m, ...p }, example: false }; setState(s); save('fis.investments', s); };
  return (
    <div className="page">
      <PageHeader title="Investment Analytics" badge={state.example ? <Badge tone="sample">Example inputs</Badge> : <Badge tone="accent">Your inputs</Badge>}
        subtitle="Fixed income (price, yield, duration, convexity), equity valuation models (DDM, FCFE, residual income), portfolio risk and return, performance attribution measures, and option pricing (BSM, binomial) — following CFA Program conventions."
        actions={<>
          <SaveLoad kind="investments" label="investment analytics" getData={() => m} onLoad={(d: Model) => { const s = { m: { ...EXAMPLE, ...d }, example: false }; setState(s); save('fis.investments', s); }} />
          <button className="btn" onClick={() => { setState({ m: EXAMPLE, example: true }); save('fis.investments', { m: EXAMPLE, example: true }); }}>Example</button>
        </>} />
      <Tabs label="Area" value={tab} onChange={(t) => { setTab(t); save('fis.investments.tab', t); }} options={[
        { value: 'bond', label: 'Fixed income' }, { value: 'equity', label: 'Equity valuation' }, { value: 'portfolio', label: 'Portfolio' },
        { value: 'performance', label: 'Performance' }, { value: 'options', label: 'Derivatives' }]} />
      <div className="mt">
        {tab === 'bond' && <Bond m={m} set={set} />}
        {tab === 'equity' && <Equity m={m} set={set} />}
        {tab === 'portfolio' && <Portfolio m={m} set={set} />}
        {tab === 'performance' && <Performance m={m} set={set} />}
        {tab === 'options' && <Options m={m} set={set} />}
      </div>
    </div>
  );
}

function useCalc<T>(path: string, body: unknown) {
  const req = useDebounced(body, 300);
  return useAsync(() => api.post<T>(path, req), [JSON.stringify(req)], !!req);
}
function Out<T>({ r, children }: { r: { data: T | null; error: string | null; loading: boolean }; children: (d: T) => React.ReactNode }) {
  if (r.error) return <ErrorBox error={r.error} />;
  if (!r.data) return r.loading ? <Skeleton h={120} /> : <p className="faint">Fill in the required inputs.</p>;
  return <>{children(r.data)}</>;
}
function Sel({ label, value, options, onChange }: { label: string; value: string | number; options: [string | number, string][]; onChange: (v: string) => void }) {
  return <Field label={label}><select className="input" value={value} onChange={(e) => onChange(e.target.value)}>{options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>;
}

interface BondRes { price: number; price_pct_of_par: number; ytm: number; current_yield: number; macaulay_duration: number; modified_duration: number; convexity: number; money_duration: number; dv01: number;
  shock: { bp: number; actual_up: number; actual_down: number; estimate_up: number; estimate_down: number; duration_only_up: number; duration_only_down: number }; formulas: string[]; note: string }
function Bond({ m, set }: { m: Model; set: (p: Partial<Model>) => void }) {
  const b = m.bond;
  const u = (p: Partial<Model['bond']>) => set({ bond: { ...b, ...p } });
  const ok = num(b, ['face', 'coupon_rate', 'years']) && (b.mode === 'ytm' ? isNum(b.ytm) : isNum(b.price));
  const r = useCalc<BondRes>('/api/investments/bond', ok ? { face: b.face, coupon_rate: b.coupon_rate, years: b.years, freq: b.freq, shock_bp: b.shock_bp ?? 100,
    ...(b.mode === 'ytm' ? { ytm: b.ytm } : { price: b.price }) } : null);
  return (
    <div className="grid cols-3">
      <Card title="Bond"><div className="stack" style={{ gap: 10 }}>
        <NumberField label="Face value" value={b.face} onChange={(v) => u({ face: v })} />
        <NumberField label="Coupon rate" percent value={b.coupon_rate} onChange={(v) => u({ coupon_rate: v })} />
        <NumberField label="Years to maturity" value={b.years} onChange={(v) => u({ years: v })} />
        <Sel label="Coupon frequency" value={b.freq} options={[[1, 'Annual'], [2, 'Semi-annual'], [4, 'Quarterly'], [12, 'Monthly']]} onChange={(v) => u({ freq: Number(v) })} />
        <Sel label="Solve for" value={b.mode} options={[['ytm', 'Price, given yield'], ['price', 'Yield, given price']]} onChange={(v) => u({ mode: v })} />
        {b.mode === 'ytm' ? <NumberField label="Yield to maturity" percent value={b.ytm} onChange={(v) => u({ ytm: v })} />
          : <NumberField label="Price (clean = full, on a coupon date)" value={b.price} onChange={(v) => u({ price: v })} />}
        <NumberField label="Yield shock (bp)" value={b.shock_bp} onChange={(v) => u({ shock_bp: v })} />
      </div></Card>
      <div className="span-2 stack"><Out r={r}>{(d) => <>
        <div className="grid cols-4">
          <Kpi label="Price" value={fmtNum(d.price, 4)} delta={`${fmtNum(d.price_pct_of_par, 3)}% of par`} />
          <Kpi label="Yield to maturity" value={fmtPct(d.ytm, 3)} delta={`Current yield ${fmtPct(d.current_yield, 2)}`} />
          <Kpi label="Macaulay / modified duration" value={`${fmtNum(d.macaulay_duration, 3)} / ${fmtNum(d.modified_duration, 3)}`} />
          <Kpi label="Convexity · DV01" value={`${fmtNum(d.convexity, 2)} · ${fmtNum(d.dv01, 4)}`} />
        </div>
        <Card title={`Price change for ±${d.shock.bp} bp`} subtitle="Full repricing vs the duration and duration + convexity approximations">
          <div className="table-wrap" tabIndex={0}><table className="data">
            <thead><tr><th>Shock</th><th className="r">Actual</th><th className="r">Duration only</th><th className="r">Duration + convexity</th></tr></thead>
            <tbody>
              <tr><td>+{d.shock.bp} bp</td><td className="r">{fmtNum(d.shock.actual_up, 4)}</td><td className="r">{fmtNum(d.shock.duration_only_up, 4)}</td><td className="r">{fmtNum(d.shock.estimate_up, 4)}</td></tr>
              <tr><td>−{d.shock.bp} bp</td><td className="r">{fmtNum(d.shock.actual_down, 4)}</td><td className="r">{fmtNum(d.shock.duration_only_down, 4)}</td><td className="r">{fmtNum(d.shock.estimate_down, 4)}</td></tr>
            </tbody>
          </table></div>
        </Card>
        <Formula>{d.formulas.join('\n')}</Formula>
        <p className="faint" style={{ fontSize: 12.5 }}>{d.note}</p>
      </>}</Out></div>
    </div>
  );
}

interface EqRes { value?: number; equity_value?: number; per_share?: number | null; formula: string; d1?: number; dividend_yield?: number; pv_dividends?: number; terminal_value?: number; pv_terminal?: number;
  pv_residual_income?: number; justified_multiples?: Record<string, number>; dividends?: { year: number; dividend: number; pv: number }[]; schedule?: { year: number; opening_book: number; earnings: number; residual_income: number; pv: number }[] }
const EQ_FIELDS: Record<string, [keyof Model['equity'], string, boolean][]> = {
  gordon: [['d0', 'Last dividend D₀ (or leave blank and give D₁)', false], ['d1', 'Next dividend D₁', false], ['g', 'Constant growth g', true], ['r', 'Required return r', true]],
  two_stage: [['d0', 'Last dividend D₀', false], ['g1', 'High growth g₁', true], ['n', 'High-growth years', false], ['g2', 'Long-run growth g₂', true], ['r', 'Required return r', true]],
  fcfe: [['fcfe0', 'Current FCFE', false], ['g', 'Constant growth g', true], ['r', 'Cost of equity r', true], ['shares', 'Shares outstanding (optional)', false]],
  residual_income: [['book_value', 'Book value B₀', false], ['roe', 'ROE (constant)', true], ['payout', 'Payout ratio', true], ['r', 'Cost of equity r', true], ['years', 'Explicit years', false], ['terminal_growth', 'Residual-income growth after (blank = none)', true], ['shares', 'Shares (optional)', false]],
};
function Equity({ m, set }: { m: Model; set: (p: Partial<Model>) => void }) {
  const e = m.equity;
  const u = (p: Partial<Model['equity']>) => set({ equity: { ...e, ...p } });
  const fields = EQ_FIELDS[e.model];
  const body: Record<string, unknown> = { model: e.model };
  for (const [k] of fields) body[k] = e[k];
  const r = useCalc<EqRes>('/api/investments/equity', isNum(e.r) ? body : null);
  return (
    <div className="grid cols-3">
      <Card title="Model"><div className="stack" style={{ gap: 10 }}>
        <Sel label="Valuation model" value={e.model} options={[['gordon', 'Gordon growth DDM'], ['two_stage', 'Two-stage DDM'], ['fcfe', 'Single-stage FCFE'], ['residual_income', 'Residual income']]} onChange={(v) => u({ model: v })} />
        {fields.map(([k, label, pct]) => <NumberField key={k} label={label} percent={pct} value={e[k] as N} onChange={(v) => u({ [k]: v })} />)}
      </div></Card>
      <div className="span-2 stack"><Out r={r}>{(d) => <>
        <div className="grid cols-3">
          <Kpi label="Intrinsic value" value={fmtNum(d.value ?? d.equity_value, 4)} />
          {isNum(d.per_share) && <Kpi label="Per share" value={fmtNum(d.per_share, 4)} />}
          {isNum(d.dividend_yield) && <Kpi label="Implied dividend yield" value={fmtPct(d.dividend_yield, 2)} />}
          {isNum(d.pv_terminal) && <Kpi label="PV of terminal / continuing value" value={fmtNum(d.pv_terminal, 4)} />}
        </div>
        <Formula>{d.formula}</Formula>
        {d.justified_multiples && Object.keys(d.justified_multiples).length > 0 && (
          <Card title="Justified multiples" subtitle="From the same ROE, payout and required return">
            <div className="grid cols-4">
              <Kpi label="Trailing P/E" value={fmtNum(d.justified_multiples.pe_trailing, 2)} />
              <Kpi label="Forward P/E" value={fmtNum(d.justified_multiples.pe_forward, 2)} />
              <Kpi label="P/B" value={fmtNum(d.justified_multiples.pb, 2)} />
              <Kpi label="Sustainable growth" value={fmtPct(d.justified_multiples.sustainable_growth, 2)} />
            </div>
          </Card>
        )}
        {(d.dividends || d.schedule) && (
          <Card title="Forecast" flush><div className="table-wrap" tabIndex={0} style={{ border: 0, borderRadius: 0 }}><table className="data">
            {d.dividends ? <><thead><tr><th>Year</th><th className="r">Dividend</th><th className="r">PV</th></tr></thead>
              <tbody>{d.dividends.map((x) => <tr key={x.year}><td>{x.year}</td><td className="r">{fmtNum(x.dividend, 4)}</td><td className="r">{fmtNum(x.pv, 4)}</td></tr>)}</tbody></>
              : <><thead><tr><th>Year</th><th className="r">Opening book</th><th className="r">Earnings</th><th className="r">Residual income</th><th className="r">PV</th></tr></thead>
                <tbody>{d.schedule!.map((x) => <tr key={x.year}><td>{x.year}</td><td className="r">{fmtNum(x.opening_book, 2)}</td><td className="r">{fmtNum(x.earnings, 2)}</td><td className="r">{fmtNum(x.residual_income, 2)}</td><td className="r">{fmtNum(x.pv, 2)}</td></tr>)}</tbody></>}
          </table></div></Card>
        )}
      </>}</Out></div>
    </div>
  );
}

interface PortRes { expected_return: number; std_dev: number; sharpe: number | null; diversification_ratio: number | null; risk_contribution: number[]; formula: string;
  frontier?: { w1: number; return: number; std_dev: number }[]; min_variance?: { w1: number; return: number; std_dev: number } }
function Portfolio({ m, set }: { m: Model; set: (p: Partial<Model>) => void }) {
  const p = m.portfolio;
  const n = p.assets.length;
  const u = (x: Partial<Model['portfolio']>) => set({ portfolio: { ...p, ...x } });
  const ua = (i: number, x: Partial<Model['portfolio']['assets'][number]>) => u({ assets: p.assets.map((a, j) => (j === i ? { ...a, ...x } : a)) });
  const setCorr = (i: number, j: number, v: N) => u({ corr: p.corr.map((row, a) => row.map((c, b) => ((a === i && b === j) || (a === j && b === i) ? v : c))) });
  const resize = (assets: Model['portfolio']['assets']) => {
    const k = assets.length;
    u({ assets, corr: Array.from({ length: k }, (_, i) => Array.from({ length: k }, (_, j) => (i === j ? 1 : p.corr[i]?.[j] ?? 0))) });
  };
  const ok = p.assets.every((a) => isNum(a.weight) && isNum(a.ret) && isNum(a.vol)) && p.corr.every((row) => row.every(isNum));
  const r = useCalc<PortRes>('/api/investments/portfolio', ok ? { weights: p.assets.map((a) => a.weight), returns: p.assets.map((a) => a.ret), vols: p.assets.map((a) => a.vol), corr: p.corr, risk_free: p.risk_free } : null);
  const wsum = p.assets.reduce((s, a) => s + (a.weight ?? 0), 0);
  return (
    <div className="stack">
      <Card title="Assets" subtitle={`Weights sum to ${fmtPct(wsum, 1)}`} actions={<button className="btn sm" disabled={n >= 10} onClick={() => resize([...p.assets, { name: `Asset ${n + 1}`, weight: 0, ret: null, vol: null }])}><Plus size={14} />Asset</button>}>
        <div className="table-wrap" tabIndex={0}><table className="data">
          <thead><tr><th>Asset</th><th>Weight</th><th>Expected return</th><th>Volatility (σ)</th>{p.assets.map((a) => <th key={a.name}>ρ with {a.name}</th>)}<th /></tr></thead>
          <tbody>{p.assets.map((a, i) => (
            <tr key={i}>
              <td><input className="input compact" aria-label="Asset name" value={a.name} onChange={(e) => ua(i, { name: e.target.value })} /></td>
              <td><NumberField compact percent ariaLabel="Weight" value={a.weight} onChange={(v) => ua(i, { weight: v })} /></td>
              <td><NumberField compact percent ariaLabel="Return" value={a.ret} onChange={(v) => ua(i, { ret: v })} /></td>
              <td><NumberField compact percent ariaLabel="Volatility" value={a.vol} onChange={(v) => ua(i, { vol: v })} /></td>
              {p.assets.map((_, j) => <td key={j} style={{ minWidth: 90 }}>{i === j ? <span className="faint">1</span> : j < i ? <span className="faint">{fmtNum(p.corr[i][j], 2)}</span> :
                <NumberField compact ariaLabel={`Correlation ${i + 1}-${j + 1}`} value={p.corr[i][j]} min={-1} max={1} onChange={(v) => setCorr(i, j, v)} />}</td>)}
              <td><button className="btn sm ghost" aria-label="Remove asset" disabled={n <= 1} onClick={() => resize(p.assets.filter((_, j) => j !== i))}><Trash2 size={14} /></button></td>
            </tr>
          ))}</tbody>
        </table></div>
        <div style={{ maxWidth: 240 }} className="mt-sm"><NumberField label="Risk-free rate" percent value={p.risk_free} onChange={(v) => u({ risk_free: v })} /></div>
      </Card>
      <Out r={r}>{(d) => <>
        <div className="grid cols-4">
          <Kpi label="Expected return" value={fmtPct(d.expected_return, 2)} />
          <Kpi label="Standard deviation" value={fmtPct(d.std_dev, 2)} />
          <Kpi label="Sharpe ratio" value={isNum(d.sharpe) ? fmtNum(d.sharpe, 3) : '—'} />
          <Kpi label="Diversification ratio" value={isNum(d.diversification_ratio) ? fmtNum(d.diversification_ratio, 2) : '—'} />
        </div>
        <div className="grid cols-2">
          <Card title="Risk contribution" subtitle="Share of portfolio variance from each asset">
            {p.assets.map((a, i) => <div key={i} className="metric-row"><span>{a.name}</span><span className="v">{fmtPct(d.risk_contribution[i], 1)} <span className="faint">(weight {fmtPct(a.weight, 0)})</span></span></div>)}
          </Card>
          {d.frontier && (
            <Card title="Two-asset frontier" subtitle={d.min_variance ? `Minimum variance at ${fmtPct(d.min_variance.w1, 1)} in ${p.assets[0].name}` : undefined}>
              <div style={{ height: 220 }}>
                <ResponsiveContainer>
                  <ScatterChart margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                    <CartesianGrid {...gridProps} vertical />
                    <XAxis dataKey="std_dev" type="number" name="Risk" {...axisProps} tickFormatter={(x) => fmtPct(x, 0)} domain={['dataMin', 'dataMax']} />
                    <YAxis dataKey="return" type="number" name="Return" {...axisProps} width={48} tickFormatter={(y) => fmtPct(y, 1)} domain={['dataMin', 'dataMax']} />
                    <ZAxis range={[18, 18]} />
                    <Tooltip content={<ChartTooltip format={(v) => fmtPct(v, 2)} />} />
                    <Scatter data={d.frontier} fill={C.c2} line={{ stroke: C.c2 }} name="Frontier" />
                    <ReferenceDot x={d.std_dev} y={d.expected_return} r={6} fill={C.c1} stroke="none" />
                  </ScatterChart>
                </ResponsiveContainer>
              </div>
            </Card>
          )}
        </div>
        <Formula>{d.formula}</Formula>
      </>}</Out>
    </div>
  );
}

interface PerfRes { annual_return: number; benchmark_return: number; volatility: number; beta: number | null; sharpe: number | null; treynor: number | null; jensens_alpha: number | null;
  m_squared: number | null; m_squared_excess: number | null; tracking_error: number; information_ratio: number | null; sortino: number | null; max_drawdown: number; notes: string[] }
function Performance({ m, set }: { m: Model; set: (p: Partial<Model>) => void }) {
  const p = m.performance;
  const u = (x: Partial<Model['performance']>) => set({ performance: { ...p, ...x } });
  const pr = parseList(p.portfolio).map((x) => x / 100), br = parseList(p.benchmark).map((x) => x / 100);
  const ok = pr.length >= 3 && pr.length === br.length && [...pr, ...br].every(Number.isFinite) && isNum(p.risk_free);
  const r = useCalc<PerfRes>('/api/investments/performance', ok ? { portfolio: pr, benchmark: br, risk_free: p.risk_free, periods_per_year: p.periods_per_year } : null);
  return (
    <div className="grid cols-3">
      <Card title="Periodic returns (%)"><div className="stack" style={{ gap: 10 }}>
        <Field label={`Portfolio (${pr.length} values)`}><textarea className="input" rows={4} value={p.portfolio} onChange={(e) => u({ portfolio: e.target.value })} /></Field>
        <Field label={`Benchmark (${br.length} values)`}><textarea className="input" rows={4} value={p.benchmark} onChange={(e) => u({ benchmark: e.target.value })} /></Field>
        {pr.length !== br.length && <Callout tone="warn">Portfolio and benchmark need the same number of periods.</Callout>}
        <Sel label="Periods per year" value={p.periods_per_year} options={[[12, 'Monthly'], [4, 'Quarterly'], [52, 'Weekly'], [252, 'Daily'], [1, 'Annual']]} onChange={(v) => u({ periods_per_year: Number(v) })} />
        <NumberField label="Risk-free rate (annual)" percent value={p.risk_free} onChange={(v) => u({ risk_free: v })} />
      </div></Card>
      <div className="span-2 stack"><Out r={r}>{(d) => <>
        <div className="grid cols-4">
          <Kpi label="Annual return" value={fmtPct(d.annual_return, 2)} delta={`Benchmark ${fmtPct(d.benchmark_return, 2)}`} />
          <Kpi label="Volatility" value={fmtPct(d.volatility, 2)} delta={`Beta ${fmtNum(d.beta, 2)}`} />
          <Kpi label="Sharpe" value={fmtNum(d.sharpe, 3)} delta={`Sortino ${fmtNum(d.sortino, 3)}`} />
          <Kpi label="Max drawdown" value={fmtPct(d.max_drawdown, 1)} />
        </div>
        <Card title="Risk-adjusted measures">
          {[['Treynor ratio', fmtNum(d.treynor, 4), '(Rp − Rf) / β'], ["Jensen's alpha", fmtPct(d.jensens_alpha, 2), 'Rp − [Rf + β(Rb − Rf)]'], ['M²', fmtPct(d.m_squared, 2), 'Rf + Sharpe × σb'], ['M² excess over benchmark', fmtPct(d.m_squared_excess, 2), 'M² − Rb'],
            ['Tracking error', fmtPct(d.tracking_error, 2), 'σ(Rp − Rb)'], ['Information ratio', fmtNum(d.information_ratio, 3), '(Rp − Rb) / tracking error']].map(([l, v, f]) => (
            <div key={l} className="metric-row"><span>{l} <span className="faint mono" style={{ fontSize: 11.5 }}>{f}</span></span><span className="v">{v}</span></div>))}
          {d.notes.map((n) => <p key={n} className="faint mt-sm" style={{ fontSize: 12.5 }}>{n}</p>)}
        </Card>
      </>}</Out></div>
    </div>
  );
}

interface OptRes { black_scholes: { call: number; put: number; d1: number; d2: number; greeks: Record<'call' | 'put', Record<string, number>>; notes: string[] };
  binomial: Record<string, number>; parity?: { mispricing: number; action: string; formula: string } }
interface StratRes { points: { spot: number; profit: number }[]; net_premium: number; max_profit_in_range: number; max_loss_in_range: number; breakevens: number[] }
function Options({ m, set }: { m: Model; set: (p: Partial<Model>) => void }) {
  const o = m.options;
  const u = (x: Partial<Model['options']>) => set({ options: { ...o, ...x } });
  const ul = (i: number, x: Partial<Model['options']['legs'][number]>) => u({ legs: o.legs.map((l, j) => (j === i ? { ...l, ...x } : l)) });
  const ok = num(o, ['s', 'k', 't', 'r', 'sigma']);
  const r = useCalc<OptRes>('/api/investments/options', ok ? { ...o, q: o.q ?? 0, steps: o.steps ?? 200, legs: undefined } : null);
  const legsOk = o.legs.length > 0 && o.legs.every((l) => isNum(l.premium) && isNum(l.quantity) && (l.type === 'stock' || isNum(l.strike)));
  const sr = useCalc<StratRes>('/api/investments/strategy', legsOk ? { legs: o.legs, spot_low: 0, spot_high: Math.max(...o.legs.map((l) => (l.strike ?? l.premium ?? 100) as number)) * 2 } : null);
  return (
    <div className="stack">
      <div className="grid cols-3">
        <Card title="Option inputs"><div className="stack" style={{ gap: 10 }}>
          <div className="grid cols-2" style={{ gap: 8 }}>
            <NumberField label="Spot S" value={o.s} onChange={(v) => u({ s: v })} /><NumberField label="Strike K" value={o.k} onChange={(v) => u({ k: v })} />
            <NumberField label="Time T (years)" value={o.t} onChange={(v) => u({ t: v })} /><NumberField label="Volatility σ" percent value={o.sigma} onChange={(v) => u({ sigma: v })} />
            <NumberField label="Risk-free r (cont.)" percent value={o.r} onChange={(v) => u({ r: v })} /><NumberField label="Dividend yield q" percent value={o.q} onChange={(v) => u({ q: v })} />
          </div>
          <NumberField label="Binomial steps" value={o.steps} onChange={(v) => u({ steps: v })} />
          <div className="grid cols-2" style={{ gap: 8 }}>
            <NumberField label="Market call (parity check)" value={o.market_call} onChange={(v) => u({ market_call: v })} />
            <NumberField label="Market put" value={o.market_put} onChange={(v) => u({ market_put: v })} />
          </div>
        </div></Card>
        <div className="span-2 stack"><Out r={r}>{(d) => <>
          <div className="grid cols-4">
            <Kpi label="BSM call" value={fmtNum(d.black_scholes.call, 4)} />
            <Kpi label="BSM put" value={fmtNum(d.black_scholes.put, 4)} />
            <Kpi label="American put (binomial)" value={fmtNum(d.binomial.american_put, 4)} delta={`Early-exercise premium ${fmtNum(d.binomial.american_put - d.binomial.european_put, 4)}`} />
            <Kpi label="American call (binomial)" value={fmtNum(d.binomial.american_call, 4)} />
          </div>
          <Card title="Greeks" subtitle={d.black_scholes.notes.join(' ')}>
            <div className="table-wrap" tabIndex={0}><table className="data">
              <thead><tr><th /><th className="r">Delta</th><th className="r">Gamma</th><th className="r">Vega</th><th className="r">Theta / day</th><th className="r">Rho</th></tr></thead>
              <tbody>{(['call', 'put'] as const).map((k) => <tr key={k}><td>{k}</td>{['delta', 'gamma', 'vega', 'theta', 'rho'].map((g) => <td key={g} className="r">{fmtNum(d.black_scholes.greeks[k][g], 4)}</td>)}</tr>)}</tbody>
            </table></div>
            <p className="faint mt-sm mono" style={{ fontSize: 11.5 }}>d₁ = {fmtNum(d.black_scholes.d1, 4)} · d₂ = {fmtNum(d.black_scholes.d2, 4)}</p>
          </Card>
          {d.parity && <Callout tone={Math.abs(d.parity.mispricing) < 1e-6 ? 'success' : 'warn'} title={`Put-call parity: gap ${fmtNum(d.parity.mispricing, 4)}`}>{d.parity.action} <span className="mono faint">{d.parity.formula}</span></Callout>}
        </>}</Out></div>
      </div>
      <Card title="Strategy payoff at expiry" subtitle="Profit including premiums; stock legs use 'premium' as the purchase price"
        actions={<button className="btn sm" onClick={() => u({ legs: [...o.legs, { type: 'put', position: 'long', strike: o.k, premium: 0, quantity: 1 }] })}><Plus size={14} />Leg</button>}>
        <div className="grid cols-2">
          <div className="table-wrap" tabIndex={0}><table className="data">
            <thead><tr><th>Type</th><th>Position</th><th>Strike</th><th>Premium / price</th><th>Qty</th><th /></tr></thead>
            <tbody>{o.legs.map((l, i) => (
              <tr key={i}>
                <td style={{ minWidth: 96 }}><select className="input compact" aria-label="Type" value={l.type} onChange={(e) => ul(i, { type: e.target.value })}><option value="call">Call</option><option value="put">Put</option><option value="stock">Stock</option></select></td>
                <td style={{ minWidth: 96 }}><select className="input compact" aria-label="Position" value={l.position} onChange={(e) => ul(i, { position: e.target.value })}><option value="long">Long</option><option value="short">Short</option></select></td>
                <td><NumberField compact ariaLabel="Strike" value={l.strike} onChange={(v) => ul(i, { strike: v })} /></td>
                <td><NumberField compact ariaLabel="Premium" value={l.premium} onChange={(v) => ul(i, { premium: v })} /></td>
                <td><NumberField compact ariaLabel="Quantity" value={l.quantity} onChange={(v) => ul(i, { quantity: v })} /></td>
                <td><button className="btn sm ghost" aria-label="Remove leg" disabled={o.legs.length <= 1} onClick={() => u({ legs: o.legs.filter((_, j) => j !== i) })}><Trash2 size={14} /></button></td>
              </tr>
            ))}</tbody>
          </table></div>
          <Out r={sr}>{(s) => (
            <div>
              <div className="row" style={{ gap: 6, marginBottom: 8 }}>
                <Badge>Net premium {fmtNum(s.net_premium, 2)}</Badge><Badge tone="accent">Max profit {fmtNum(s.max_profit_in_range, 2)}</Badge>
                <Badge tone="neg">Max loss {fmtNum(s.max_loss_in_range, 2)}</Badge>{s.breakevens.length > 0 && <Badge>Break-even {s.breakevens.map((b) => fmtNum(b, 2)).join(', ')}</Badge>}
              </div>
              <div style={{ height: 220 }}>
                <ResponsiveContainer>
                  <LineChart data={s.points} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                    <CartesianGrid {...gridProps} />
                    <XAxis dataKey="spot" type="number" domain={['dataMin', 'dataMax']} {...axisProps} tickFormatter={(x) => fmtNum(x, 0)} />
                    <YAxis {...axisProps} width={48} tickFormatter={(y) => fmtNum(y, 0)} />
                    <Tooltip content={<ChartTooltip format={(v) => fmtNum(v, 2)} labelFormat={(l) => `Spot ${fmtNum(Number(l), 2)}`} />} />
                    <ReferenceLine y={0} stroke={C.axis} />
                    <Line dataKey="profit" name="Profit" stroke={C.c1} strokeWidth={2} dot={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}</Out>
        </div>
      </Card>
    </div>
  );
}
