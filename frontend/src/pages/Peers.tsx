import { Bot, Download, Trophy, Users } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { C, ChartTooltip, axisProps, gridProps } from '../components/charts';
import { Badge, Callout, Card, EmptyState, ErrorBox, Field, Kpi, LearnBox, NumberField, PageHeader, Skeleton } from '../components/ui';
import { api } from '../lib/api';
import { toCompany, useCompanySources, type CompanyData } from '../lib/company';
import { downloadFile, fmtNum, fmtPct, isNum, toCSV } from '../lib/format';
import { useSettings } from '../lib/settings';
import { loadRaw, save } from '../lib/storage';
import { useAsync, useDebounced } from '../lib/useApi';

interface Row { key: string; name: string; group: string; unit: string; better: 'higher' | 'lower' | 'neutral'; formula: string; values: (number | null)[]; ranks: (number | null)[]; median: number | null; notes: string[] }
interface Report { companies: string[]; latest_periods: string[]; rows: Row[]; average_rank: (number | null)[]; ranked_on: number[]; warnings: string[] }
interface Picked { id: string; name: string; marketCap: number | null }

/** Three fictional IT-services companies, used only when the user has no saved statements; always labelled. */
const mk = (s: number, g: number, m: number, cogs: number): CompanyData => ({
  periods: ['FY2023', 'FY2024', 'FY2025'],
  items: {
    revenue: [1000 * s, 1000 * s * (1 + g), 1000 * s * (1 + g) ** 2], cogs: [cogs * 1000 * s, cogs * 1000 * s * (1 + g), cogs * 1000 * s * (1 + g) ** 2],
    operating_income: [1000 * s * m, 1000 * s * (1 + g) * m, 1000 * s * (1 + g) ** 2 * (m + 0.01)],
    depreciation_amortization: [30 * s, 32 * s, 35 * s], interest_expense: [5 * s, 5 * s, 4 * s],
    net_income: [750 * s * m, 760 * s * (1 + g) * m, 770 * s * (1 + g) ** 2 * m], total_assets: [900 * s, 980 * s, 1060 * s],
    total_equity: [600 * s, 650 * s, 700 * s], total_debt: [50 * s, 40 * s, 30 * s], receivables: [200 * s, 215 * s, 240 * s],
    current_assets: [500 * s, 540 * s, 590 * s], current_liabilities: [250 * s, 260 * s, 280 * s], cash: [150 * s, 160 * s, 180 * s],
    operating_cash_flow: [180 * s, 200 * s, 215 * s], capex: [-30 * s, -35 * s, -40 * s], retained_earnings: [450 * s, 500 * s, 550 * s],
  },
});
const EXAMPLES: { name: string; data: CompanyData }[] = [
  { name: 'Alpha Tech (example)', data: mk(2.4, 0.07, 0.25, 0.58) }, { name: 'Beta Infosystems (example)', data: mk(1.6, 0.05, 0.21, 0.62) },
  { name: 'Gamma Digital (example)', data: mk(0.9, 0.12, 0.17, 0.66) },
];

function fmtVal(v: number | null, unit: string, currency: string) {
  if (!isNum(v)) return '—';
  if (unit === '%') return fmtPct(v, 1);
  if (unit === 'days') return `${fmtNum(v, 0)} d`;
  if (unit === 'amount') return fmtNum(v, 0, currency as never);
  if (unit === 'score') return fmtNum(v, 2);
  return `${fmtNum(v, 2)}×`;
}

export function Peers() {
  const { settings } = useSettings();
  const { sources, error: srcError } = useCompanySources();
  const [picked, setPicked] = useState<Picked[]>(() => loadRaw('fis.peers.picked', []));
  const [useExample, setUseExample] = useState(false);
  const [loaded, setLoaded] = useState<Record<string, CompanyData>>({});
  const [chartKey, setChartKey] = useState('roe');
  const real = (sources ?? []).filter((s) => !s.isExample);

  const persist = (p: Picked[]) => { setPicked(p); save('fis.peers.picked', p); };
  const toggle = (id: string, name: string) => persist(picked.some((p) => p.id === id) ? picked.filter((p) => p.id !== id) : [...picked, { id, name, marketCap: null }]);

  useEffect(() => {
    if (!sources) return;
    for (const p of picked) {
      const src = sources.find((s) => s.id === p.id);
      if (src && !loaded[p.id]) src.load().then((d) => setLoaded((m) => ({ ...m, [p.id]: toCompany(d) }))).catch(() => undefined);
    }
  }, [sources, picked, loaded]);

  const body = useMemo(() => {
    const list = useExample ? EXAMPLES.map((e) => ({ name: e.name, ...e.data }))
      : picked.filter((p) => loaded[p.id] && sources?.some((s) => s.id === p.id)).map((p) => {
        const d = loaded[p.id];
        const items = { ...d.items };
        if (isNum(p.marketCap)) items.market_cap = d.periods.map((_, i) => (i === d.periods.length - 1 ? p.marketCap : null));
        return { name: p.name, periods: d.periods, items };
      });
    return list.length >= 2 ? { companies: list } : null;
  }, [useExample, picked, loaded, sources]);
  const req = useDebounced(body, 150);
  const res = useAsync((signal) => api.post<Report>('/api/analysis/peers', req, { signal }), [JSON.stringify(req)], !!req);
  const r = req ? res.data : null;

  const groups = useMemo(() => {
    const g: Record<string, Row[]> = {};
    for (const row of r?.rows ?? []) (g[row.group] ??= []).push(row);
    return Object.entries(g);
  }, [r]);
  const chartRow = r?.rows.find((x) => x.key === chartKey) ?? r?.rows.find((x) => x.unit === '%');
  const chart = r && chartRow ? r.companies.map((c, i) => ({ name: c, value: chartRow.values[i], rank: chartRow.ranks[i] })) : [];

  const exportCsv = () => {
    if (!r) return;
    downloadFile('peer-comparison.csv', toCSV([['Peer comparison', useExample ? 'EXAMPLE DATA' : 'User data'], [],
      ['Metric', 'Formula', 'Better', ...r.companies.flatMap((c) => [c, `${c} rank`]), 'Median'],
      ...r.rows.map((x) => [x.name, x.formula, x.better, ...x.values.flatMap((v, i) => [v ?? '', x.ranks[i] ?? '']), x.median ?? '']),
      ['Average rank', '', '', ...r.average_rank.flatMap((v, i) => [v ?? '', `${r.ranked_on[i]} metrics`]), ''], [],
      ...r.warnings.map((w) => [w]), ['Generated', new Date().toISOString()]]));
  };

  return (
    <div className="page">
      <PageHeader title="Peer Comparison" badge={useExample ? <Badge tone="sample">Example data</Badge> : r ? <Badge tone="accent">Your data</Badge> : undefined}
        subtitle="Compare companies side by side on growth, profitability, returns, efficiency, cash quality, safety, red-flag scores and valuation — each with its formula and a rank."
        actions={r && <>
          <Link className="btn" to="/assistant?topic=peers"><Bot size={15} />Explain with AI</Link>
          <button className="btn" onClick={exportCsv}><Download size={15} />Export CSV</button>
        </>} />

      <div className="grid cols-3 mt">
        <div className="stack">
          <Card title="Companies" subtitle="Saved statements from the Financial Statements page">
            {!sources ? <Skeleton h={60} /> : (
              <div className="stack" style={{ gap: 10 }}>
                {srcError && <Callout tone="warn">Could not load saved statements: {srcError}</Callout>}
                {real.length === 0 && <p className="muted" style={{ fontSize: 13 }}>No saved companies yet. On <Link to="/statements">Financial Statements</Link>, import each company's file and click <b>Save</b>, one company per saved model.</p>}
                {real.map((s) => {
                  const p = picked.find((x) => x.id === s.id);
                  return (
                    <div key={s.id} className="stack" style={{ gap: 6 }}>
                      <label className="row" style={{ fontSize: 13.5 }}>
                        <input type="checkbox" checked={!!p} disabled={useExample} onChange={() => toggle(s.id, s.name)} />{s.name}
                      </label>
                      {p && !useExample && (
                        <div className="grid cols-2" style={{ gap: 8, paddingLeft: 24 }}>
                          <Field label="Show as"><input className="input" value={p.name} maxLength={80}
                            onChange={(e) => persist(picked.map((x) => (x.id === s.id ? { ...x, name: e.target.value } : x)))} /></Field>
                          <NumberField label="Market cap (optional)" value={p.marketCap} min={0} hint="Same units; enables P/E, P/B, EV/EBITDA"
                            onChange={(v) => persist(picked.map((x) => (x.id === s.id ? { ...x, marketCap: v } : x)))} />
                        </div>
                      )}
                    </div>
                  );
                })}
                <label className="row" style={{ fontSize: 13 }}>
                  <input type="checkbox" checked={useExample} onChange={(e) => setUseExample(e.target.checked)} />Use three fictional example companies instead
                </label>
              </div>
            )}
          </Card>
          <LearnBox title="Comparing peers fairly">
            <div className="stack" style={{ fontSize: 13 }}>
              <p>Compare companies in the <b>same industry</b> (e.g. TCS, Infosys, Wipro, HCLTech), with the <b>same year-end</b> and the <b>same units</b>.</p>
              <p><b>Rank 1</b> is the best value on that metric. "Better" depends on the metric: for debt/equity and receivable days, lower is better.</p>
              <p>The <b>average rank</b> is a quick summary, not a verdict. A company can rank lower overall and still be the better business.</p>
            </div>
          </LearnBox>
        </div>

        <div className="span-2 stack">
          {!body && <EmptyState icon={<Users size={22} />} title="Choose at least two companies">Tick two or more saved companies, or use the example companies.</EmptyState>}
          {body && res.error && <ErrorBox error={res.error} />}
          {body && !r && !res.error && <Skeleton h={160} />}
          {r && (
            <>
              <Warnings items={r.warnings} />
              <Card title="Overall" subtitle="Average rank across the metrics each company could be ranked on (lower is better)">
                <div className="grid cols-4">
                  {r.companies.map((c, i) => {
                    const best = Math.min(...r.average_rank.filter(isNum));
                    return (
                      <Kpi key={c} label={c} value={isNum(r.average_rank[i]) ? fmtNum(r.average_rank[i], 1) : '—'}
                        delta={<>{r.average_rank[i] === best && <Trophy size={13} style={{ color: 'var(--accent)' }} />}{r.ranked_on[i]} metrics · {r.latest_periods[i]}</>} />
                    );
                  })}
                </div>
              </Card>
              {chartRow && (
                <Card title={chartRow.name} subtitle={`${chartRow.formula} · ${chartRow.better === 'neutral' ? 'not ranked' : `${chartRow.better} is better`}`}
                  actions={<select className="input compact" aria-label="Metric to chart" value={chartRow.key} onChange={(e) => setChartKey(e.target.value)}>
                    {r.rows.map((x) => <option key={x.key} value={x.key}>{x.name}</option>)}
                  </select>}>
                  <div style={{ height: 240 }}>
                    <ResponsiveContainer>
                      <BarChart data={chart} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                        <CartesianGrid {...gridProps} />
                        <XAxis dataKey="name" {...axisProps} />
                        <YAxis {...axisProps} width={56} tickFormatter={(v) => fmtVal(v, chartRow.unit, settings.currency)} />
                        <Tooltip cursor={{ fill: 'var(--bg-hover)' }} content={<ChartTooltip format={(v) => fmtVal(v, chartRow.unit, settings.currency)} />} />
                        <Bar dataKey="value" name={chartRow.name} radius={[4, 4, 0, 0]}>
                          {chart.map((d) => <Cell key={d.name} fill={d.rank === 1 ? C.c1 : C.c2} />)}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </Card>
              )}
            </>
          )}
        </div>
      </div>
      {r && <div className="mt">
              <Card title="All metrics" subtitle="Latest year for each company. Rank badges: 1 is best." flush>
                <div className="table-wrap" tabIndex={0}>
                  <table className="data">
                    <thead><tr><th>Metric</th>{r.companies.map((c) => <th key={c} className="r">{c}</th>)}<th className="r">Median</th></tr></thead>
                    <tbody>
                      {groups.map(([g, rows]) => [
                        <tr key={g}><td colSpan={r.companies.length + 2} className="faint" style={{ fontWeight: 650, fontSize: 12, background: 'var(--bg-sunken)' }}>{g}</td></tr>,
                        ...rows.map((x) => (
                          <tr key={x.key}>
                            <td title={x.formula}>{x.name}{x.better === 'lower' && <span className="faint"> (lower is better)</span>}
                              {x.notes.map((n) => <div key={n} className="faint" style={{ fontSize: 11.5, whiteSpace: 'normal' }}>{n}</div>)}</td>
                            {x.values.map((v, i) => (
                              <td key={i} className="r">{fmtVal(v, x.unit, settings.currency)}
                                {x.ranks[i] !== null && <> <Badge tone={x.ranks[i] === 1 ? 'accent' : undefined}>#{x.ranks[i]}</Badge></>}</td>
                            ))}
                            <td className="r faint">{fmtVal(x.median, x.unit, settings.currency)}</td>
                          </tr>
                        )),
                      ])}
                    </tbody>
                  </table>
                </div>
              </Card>
      </div>}
    </div>
  );
}

function Warnings({ items }: { items: string[] }) {
  return items.length ? <Callout tone="warn" title="Before you compare">{items.map((w) => <div key={w}>{w}</div>)}</Callout> : null;
}
