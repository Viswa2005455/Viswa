import { Gauge, Search, Upload } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { C, ChartTooltip, axisProps, gridProps } from '../components/charts';
import { Badge, Callout, Card, ErrorBox, Field, Kpi, NumberField, PageHeader, Skeleton } from '../components/ui';
import { api } from '../lib/api';
import { fmtNum, fmtPct, isNum } from '../lib/format';
import { loadRaw, save } from '../lib/storage';
import { useAsync } from '../lib/useApi';

interface Status { configured: boolean; provider: string | null; label: string | null; attribution: string | null; licence: string; benchmarks: Record<string, string>; demo: boolean }
interface Hit { symbol: string; name: string | null; exchange: string | null; country: string | null; currency: string | null; type: string | null }
interface Quote { symbol: string; name: string | null; exchange: string | null; currency: string | null; price: number | null; previous_close: number | null; change: number | null; change_pct: number | null; high: number | null; low: number | null; volume: number | null; as_of: string | null; delay: string; attribution: string }
interface Factor { factor: string; value: number | boolean | null; points: number; bands: string }
interface Metrics {
  points: number; from: string; to: string; years: number; last_price: number; cagr: number; volatility: number; sharpe: number | null; sortino: number | null;
  max_drawdown: number; max_drawdown_peak: string; max_drawdown_trough: string; recovered_on: string | null; current_drawdown: number;
  var_95_1d: number; cvar_95_1d: number; var_95_10d: number; high_52w: number; low_52w: number; from_52w_high: number; ma_200: number | null;
  above_ma_200: boolean | null; beta: number | null; correlation: number | null; best_day: number; worst_day: number; positive_days: number;
}
interface Risk { metrics: Metrics; factors: Factor[]; score: number; rating: string; profile: string; assessment: { fit: string; message: string }; warnings: string[]; disclaimer: string; prices: { dates: string[]; closes: (number | null)[] }; source: string; symbol?: string; benchmark?: string | null }

type Profile = 'conservative' | 'balanced' | 'aggressive';
const RATING_TONE: Record<string, 'accent' | 'info' | 'warn' | 'neg'> = { Low: 'accent', Moderate: 'info', High: 'warn', 'Very high': 'neg' };
const FIT: Record<string, ['success' | 'warn' | 'error', string]> = { fits: ['success', 'Fits your risk profile'], borderline: ['warn', 'Borderline for your profile'], does_not_fit: ['error', 'Does not fit your profile'] };

export function Markets() {
  const status = useAsync((signal) => api.get<Status>('/api/market/status', { signal }), []);
  const [params, setParams] = useState(() => loadRaw('fis.market', { symbol: 'RELIANCE.NSE', benchmark: 'NSEI.INDX', years: 5, profile: 'balanced' as Profile, horizon: 5 as number | null, rf: 0.065 as number | null }));
  const upd = (p: Partial<typeof params>) => { const s = { ...params, ...p }; setParams(s); save('fis.market', s); };
  const [risk, setRisk] = useState<Risk | null>(null);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const s = status.data;

  const analyseLive = async (symbol = params.symbol) => {
    setBusy(true); setErr(null);
    try {
      const q = new URLSearchParams({ symbol, years: String(params.years), profile: params.profile, risk_free: String(params.rf ?? 0.065), horizon_years: String(params.horizon ?? 5) });
      if (params.benchmark.trim()) q.set('benchmark', params.benchmark.trim());
      const [rq, rr] = await Promise.allSettled([api.get<Quote>(`/api/market/quote?symbol=${encodeURIComponent(symbol)}`), api.get<Risk>(`/api/market/risk?${q}`)]);
      setQuote(rq.status === 'fulfilled' ? rq.value : null);
      if (rr.status === 'fulfilled') setRisk(rr.value); else { setRisk(null); throw rr.reason; }
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <div className="page">
      <PageHeader title="Markets & Risk" badge={s?.configured ? <Badge tone="accent">{s.demo ? 'Demo key' : `Live · ${s.label}`}</Badge> : <Badge>Price files</Badge>}
        subtitle="Share prices for companies worldwide (NSE, BSE, NYSE, NASDAQ, LSE and more) and a transparent check of how risky a share has been: volatility, worst fall, beta, Value at Risk and trend, scored against your risk profile." />
      {status.loading ? <Skeleton h={60} /> : s && !s.configured ? (
        <Callout tone="info" title="Live prices are not switched on — you can still upload a price file below">
          <ol style={{ margin: '4px 0 0', paddingLeft: 18 }}>
            <li>Get an API key from <a href="https://eodhd.com" target="_blank" rel="noreferrer">EODHD</a> (covers NSE and BSE; free key: 20 requests a day) or <a href="https://twelvedata.com" target="_blank" rel="noreferrer">Twelve Data</a> (free key: US shares).</li>
            <li>Add two lines to <code>backend\.env</code>: <code>FIS_MARKET_PROVIDER=eodhd</code> and <code>FIS_MARKET_API_KEY=your-key</code> (on a hosted copy, set them in the host's environment settings). To try it first, <code>FIS_MARKET_API_KEY=demo</code> works with EODHD for AAPL.US, TSLA.US and AMZN.US.</li>
            <li>Restart the app. The key stays on the server; the browser never sees it.</li>
          </ol>
          <div className="faint mt-sm" style={{ fontSize: 12 }}>{s.licence}</div>
        </Callout>
      ) : s ? <Callout tone="success" title={`Live prices from ${s.label}`}>{s.attribution}. {s.licence}</Callout> : null}

      <div className="grid cols-3 mt">
        <Card title="Your risk profile" subtitle="Used to judge the fit; it does not change the figures">
          <div className="grid cols-2" style={{ gap: 10 }}>
            <Field label="Risk appetite"><select className="input" value={params.profile} onChange={(e) => upd({ profile: e.target.value as Profile })}>
              <option value="conservative">Conservative</option><option value="balanced">Balanced</option><option value="aggressive">Aggressive</option></select></Field>
            <NumberField label="Holding period (years)" value={params.horizon} onChange={(v) => upd({ horizon: v })} />
            <NumberField label="Risk-free rate" percent value={params.rf} onChange={(v) => upd({ rf: v })} hint="e.g. 10-year G-sec yield" />
            <Field label="History"><select className="input" value={params.years} onChange={(e) => upd({ years: Number(e.target.value) })}>{[1, 2, 3, 5, 10].map((y) => <option key={y} value={y}>{y} year{y > 1 ? 's' : ''}</option>)}</select></Field>
          </div>
        </Card>
        {s?.configured && <LivePicker params={params} upd={upd} benchmarks={s.benchmarks} busy={busy} onAnalyse={analyseLive} />}
        <FileRisk params={params} onResult={(r) => { setRisk(r); setQuote(null); setErr(null); }} onError={setErr} wide={!s?.configured} />
      </div>
      {err && <div className="mt"><ErrorBox error={err} /></div>}
      {quote && <QuoteCard q={quote} />}
      {busy && !risk && <div className="mt"><Skeleton h={200} /></div>}
      {risk && <RiskView r={risk} />}
    </div>
  );
}

function LivePicker({ params, upd, benchmarks, busy, onAnalyse }: { params: { symbol: string; benchmark: string }; upd: (p: { symbol?: string; benchmark?: string }) => void; benchmarks: Record<string, string>; busy: boolean; onAnalyse: (s?: string) => void }) {
  const [q, setQ] = useState('');
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const search = async () => {
    if (!q.trim()) return;
    setErr(null);
    try { setHits((await api.get<{ results: Hit[] }>(`/api/market/search?q=${encodeURIComponent(q.trim())}`)).results); } catch (e) { setErr((e as Error).message); }
  };
  const pick = (h: Hit) => {
    const ex = h.symbol.split('.').pop() ?? '';
    upd({ symbol: h.symbol, benchmark: benchmarks[ex] ?? params.benchmark });
    setHits(null);
  };
  return (
    <Card title="Find a company" subtitle="Search by name or ticker, then analyse">
      <div className="row" style={{ flexWrap: 'nowrap' }}>
        <input className="input" placeholder="e.g. Infosys, TCS, Apple" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && search()} />
        <button className="btn" onClick={search} aria-label="Search"><Search size={15} /></button>
      </div>
      {err && <div className="mt-sm"><ErrorBox error={err} /></div>}
      {hits && <div className="list mt-sm" style={{ maxHeight: 200, overflow: 'auto' }}>{hits.length === 0 ? <p className="faint">No matches.</p> : hits.map((h) => (
        <button key={h.symbol} className="list-item btn ghost" style={{ justifyContent: 'flex-start', height: 'auto', textAlign: 'left' }} onClick={() => pick(h)}>
          <div className="grow"><b>{h.symbol}</b> <span className="muted">{h.name}</span><div className="faint" style={{ fontSize: 11 }}>{[h.exchange, h.country, h.currency, h.type].filter(Boolean).join(' · ')}</div></div>
        </button>))}</div>}
      <div className="grid cols-2 mt-sm" style={{ gap: 10 }}>
        <Field label="Symbol"><input className="input" value={params.symbol} onChange={(e) => upd({ symbol: e.target.value.toUpperCase() })} /></Field>
        <Field label="Benchmark (for beta)"><input className="input" value={params.benchmark} onChange={(e) => upd({ benchmark: e.target.value.toUpperCase() })} placeholder="NSEI.INDX" /></Field>
      </div>
      <button className="btn primary mt-sm" disabled={busy || !params.symbol.trim()} onClick={() => onAnalyse()}><Gauge size={15} />{busy ? 'Analysing…' : 'Analyse risk'}</button>
    </Card>
  );
}

function FileRisk({ params, onResult, onError, wide }: { params: { profile: Profile; rf: number | null; horizon: number | null }; onResult: (r: Risk) => void; onError: (e: string) => void; wide: boolean }) {
  const [file, setFile] = useState<File | null>(null);
  const [bench, setBench] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    if (!file) return;
    setBusy(true);
    try {
      onResult(await api.form<Risk>('/api/market/risk-from-file', { file, benchmark_file: bench, profile: params.profile, risk_free: String(params.rf ?? 0.065), horizon_years: String(params.horizon ?? 5) }));
    } catch (e) { onError((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Card title="Or analyse a price file" subtitle="A CSV or Excel file with Date and Close columns — for example the historical data download from nseindia.com or bseindia.com" className={wide ? 'span-2' : ''}>
      <div className="grid cols-2" style={{ gap: 10 }}>
        {[['Share prices', file, setFile], ['Index prices (optional, for beta)', bench, setBench]].map(([label, f, setF]) => (
          <Field key={label as string} label={label as string}>
            <label className="btn" style={{ justifyContent: 'flex-start', overflow: 'hidden' }}><Upload size={15} /><span className="truncate">{(f as File | null)?.name ?? 'Choose .csv or .xlsx'}</span>
              <input type="file" accept=".csv,.xlsx,.xlsm" hidden onChange={(e) => (setF as (x: File | null) => void)(e.target.files?.[0] ?? null)} /></label>
          </Field>
        ))}
      </div>
      <button className="btn primary mt-sm" disabled={!file || busy} onClick={run}><Gauge size={15} />{busy ? 'Analysing…' : 'Analyse file'}</button>
    </Card>
  );
}

function QuoteCard({ q }: { q: Quote }) {
  return (
    <div className="grid cols-4 mt">
      <Kpi label={`${q.symbol}${q.name ? ` · ${q.name}` : ''}`} value={`${q.currency ?? ''} ${fmtNum(q.price, 2)}`.trim()}
        delta={isNum(q.change_pct) ? `${q.change_pct >= 0 ? '▲' : '▼'} ${fmtNum(Math.abs(q.change_pct), 2)}% (${fmtNum(q.change, 2)})` : undefined} deltaTone={isNum(q.change_pct) && q.change_pct < 0 ? 'neg' : 'pos'} />
      <Kpi label="Day range" value={`${fmtNum(q.low, 2)} – ${fmtNum(q.high, 2)}`} />
      <Kpi label="Previous close" value={fmtNum(q.previous_close, 2)} />
      <Kpi label="As of" value={q.as_of ? new Date(q.as_of).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) : '—'} delta={q.delay} deltaTone="muted" />
    </div>
  );
}

function RiskView({ r }: { r: Risk }) {
  const m = r.metrics;
  const data = useMemo(() => r.prices.dates.map((d, i) => ({ d, p: r.prices.closes[i] })).filter((x) => isNum(x.p)), [r]);
  const [tone, label] = FIT[r.assessment.fit];
  return (
    <div className="stack mt">
      <div className="grid cols-4">
        <Kpi label="Risk rating" value={`${r.rating} (${r.score}/100)`} />
        <Kpi label="Volatility (annual)" value={fmtPct(m.volatility, 1)} />
        <Kpi label="Largest fall from a peak" value={fmtPct(m.max_drawdown, 1)} delta={m.recovered_on ? `recovered ${m.recovered_on}` : 'not yet recovered'} deltaTone={m.recovered_on ? 'pos' : 'neg'} />
        <Kpi label="Return a year (CAGR)" value={fmtPct(m.cagr, 1)} delta={`${m.from} → ${m.to}`} deltaTone="muted" />
      </div>
      <Callout tone={tone} title={`${label} (${r.profile})`}>{r.assessment.message}</Callout>
      <div className="grid cols-3">
        <Card title="Price history" subtitle={r.source} className="span-2">
          <div className="chart tall">
            <ResponsiveContainer>
              <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="d" {...axisProps} minTickGap={40} tickFormatter={(d: string) => d.slice(0, 7)} />
                <YAxis {...axisProps} width={60} domain={['auto', 'auto']} tickFormatter={(v: number) => fmtNum(v, 0)} />
                <Tooltip content={<ChartTooltip format={(v) => fmtNum(v, 2)} />} />
                <Area type="monotone" dataKey="p" name="Close" stroke={C.c1} strokeWidth={2} fill={C.c1} fillOpacity={0.08} dot={false} isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card title="Key figures">
          {[['Last price', fmtNum(m.last_price, 2)], ['52-week range', `${fmtNum(m.low_52w, 2)} – ${fmtNum(m.high_52w, 2)}`], ['From 52-week high', fmtPct(m.from_52w_high, 1)],
            ['200-day average', m.ma_200 === null ? '—' : `${fmtNum(m.ma_200, 2)} (${m.above_ma_200 ? 'above' : 'below'})`], ['Beta', fmtNum(m.beta, 2)], ['Correlation', fmtNum(m.correlation, 2)],
            ['Sharpe ratio', fmtNum(m.sharpe, 2)], ['Sortino ratio', fmtNum(m.sortino, 2)], ['1-day VaR (95%)', fmtPct(m.var_95_1d, 2)], ['10-day VaR (95%)', fmtPct(m.var_95_10d, 2)],
            ['Expected shortfall (95%)', fmtPct(m.cvar_95_1d, 2)], ['Worst day', fmtPct(m.worst_day, 1)], ['Up days', fmtPct(m.positive_days, 0)]].map(([k, v]) => (
            <div key={k} className="metric-row"><span>{k}</span><span className="v">{v}</span></div>))}
        </Card>
      </div>
      <Card title="How the rating is scored" actions={<Badge tone={RATING_TONE[r.rating]}>{r.rating} risk · {r.score}/100</Badge>} subtitle="Each factor scores 0 (low risk) to 3 (very high); the total is scaled to 100. Low < 25 · Moderate < 50 · High < 75 · Very high">
        <div className="table-wrap" tabIndex={0}><table className="data">
          <thead><tr><th>Factor</th><th className="r">Value</th><th className="r">Points</th><th>Bands (0 / 1 / 2 / 3)</th></tr></thead>
          <tbody>{r.factors.map((f) => (
            <tr key={f.factor}><td>{f.factor}</td><td className="r">{typeof f.value === 'boolean' ? (f.value ? 'above' : 'below') : f.value === null ? '—' : f.factor.startsWith('Beta') ? fmtNum(f.value, 2) : fmtPct(f.value, 1)}</td>
              <td className="r"><b>{f.points}</b></td><td className="faint" style={{ fontSize: 12 }}>{f.bands}</td></tr>))}</tbody></table></div>
        {r.warnings.length > 0 && <ul className="faint mt-sm" style={{ fontSize: 12, paddingLeft: 18 }}>{r.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
      </Card>
      <Callout tone="warn" title="Not investment advice">{r.disclaimer}</Callout>
    </div>
  );
}
