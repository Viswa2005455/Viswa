import { Bot, FileText, ShieldAlert, Users } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bar, CartesianGrid, ComposedChart, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api } from '../lib/api';
import { toCompany, type CompanySource, type StatementData } from '../lib/company';
import { fmtCompactUnits, fmtNum, fmtPct, fmtScaled, isNum, type UnitScale } from '../lib/format';
import { useSettings } from '../lib/settings';
import { save } from '../lib/storage';
import { useAsync } from '../lib/useApi';
import { C, ChartTooltip, Legend, axisProps, gridProps } from './charts';
import { Badge, Card, ErrorBox, Kpi, Skeleton } from './ui';

interface Profile {
  periods: string[]; series: Record<string, (number | null)[]>;
  metrics: Record<string, { label: string; unit: string; group: string; formula: string }>;
  cagr: Record<string, { label: string; value: number | null }>;
  scores: Record<string, { value: number | null; verdict?: string | null; model?: string; tested?: number }>;
  highlights: string[]; derived: string[];
}

const VERDICT: Record<string, { tone: 'accent' | 'warn' | 'neg'; text: string }> = {
  safe: { tone: 'accent', text: 'Safe zone' }, grey: { tone: 'warn', text: 'Grey zone' }, distress: { tone: 'neg', text: 'Distress zone' },
  flag: { tone: 'neg', text: 'Red flag' }, no_flag: { tone: 'accent', text: 'No flag' },
};

export function CompanyDashboard({ sources, initialId }: { sources: CompanySource[]; initialId: string }) {
  const { settings } = useSettings();
  const cur = settings.currency;
  const [id, setId] = useState(initialId);
  const src = sources.find((s) => s.id === id) ?? sources[0];
  const [data, setData] = useState<StatementData | null>(null);
  useEffect(() => { setData(null); src.load().then(setData).catch(() => setData(null)); save('fis.dashboard.company', src.id); }, [src]);
  const company = useMemo(() => (data ? toCompany(data) : null), [data]);
  const res = useAsync(() => api.post<Profile>('/api/analysis/profile', company), [JSON.stringify(company)], !!company);
  const p = company ? res.data : null;
  const units = (data?.units as UnitScale | undefined) ?? settings.units;
  const last = (p?.periods.length ?? 1) - 1;
  const v = (k: string, i = last) => p?.series[k]?.[i] ?? null;
  const amt = (x: number | null) => fmtScaled(x, units, cur, 0);
  const fmt = (k: string, x: number | null) => {
    const u = p?.metrics[k]?.unit;
    if (!isNum(x)) return '—';
    if (u === '%') return fmtPct(x, 1);
    if (u === 'amount') return amt(x);
    if (u === 'days') return `${fmtNum(x, 0)} d`;
    if (u === 'per_share') return fmtNum(x, 2, cur);
    return `${fmtNum(x, 2)}×`;
  };
  const growth = (k: string) => {
    const g = k === 'revenue' ? v('revenue_growth') : v('profit_growth');
    return isNum(g) ? <span className={g >= 0 ? 'pos' : 'neg'}>{g >= 0 ? '▲' : '▼'} {fmtPct(Math.abs(g), 1)} y/y</span> : undefined;
  };
  const chart = p ? p.periods.map((per, i) => ({ period: per, revenue: v('revenue', i), profit: v('net_income', i), margin: isNum(v('net_margin', i)) ? (v('net_margin', i) as number) * 100 : null,
    roe: isNum(v('roe', i)) ? (v('roe', i) as number) * 100 : null, roce: isNum(v('roce', i)) ? (v('roce', i) as number) * 100 : null })) : [];
  const groups = p ? Object.entries(p.metrics).reduce<Record<string, string[]>>((a, [k, m]) => { (a[m.group] ??= []).push(k); return a; }, {}) : {};

  return (
    <div className="stack">
      <div className="row between">
        <div className="row">
          <select className="input" style={{ minWidth: 260 }} aria-label="Company" value={src.id} onChange={(e) => setId(e.target.value)}>
            {sources.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          {p && <span className="faint" style={{ fontSize: 12.5 }}>{p.periods[0]} – {p.periods[last]} · {cur} {units}</span>}
        </div>
        <div className="row">
          <Link className="btn sm" to="/red-flags"><ShieldAlert size={14} />Red flags</Link>
          <Link className="btn sm" to="/peers"><Users size={14} />Peers</Link>
          <Link className="btn sm" to="/reports"><FileText size={14} />Report</Link>
          <Link className="btn sm" to="/assistant?topic=red-flags"><Bot size={14} />Ask AI</Link>
        </div>
      </div>
      {res.error && <ErrorBox error={res.error} />}
      {!p && !res.error && <Skeleton h={140} />}
      {p && (
        <>
          <div className="grid cols-4">
            <Kpi label={`Revenue (${p.periods[last]})`} value={amt(v('revenue'))} delta={growth('revenue')} />
            <Kpi label="Net profit" value={amt(v('net_income'))} delta={growth('net_income')} />
            <Kpi label="ROE / ROCE" value={`${fmt('roe', v('roe'))} / ${fmt('roce', v('roce'))}`} />
            <Kpi label={isNum(v('market_cap')) ? 'Market cap · P/E' : 'Debt / equity'}
              value={isNum(v('market_cap')) ? `${fmtCompactUnits(v('market_cap'), units, cur)} · ${fmt('pe', v('pe'))}` : fmt('debt_equity', v('debt_equity'))} />
          </div>
          <div className="grid cols-2">
            <Card title="Revenue and net profit" subtitle="Bars: amounts · line: net margin %">
              <div style={{ height: 250 }}>
                <ResponsiveContainer>
                  <ComposedChart data={chart} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid {...gridProps} />
                    <XAxis dataKey="period" {...axisProps} />
                    <YAxis yAxisId="a" {...axisProps} width={56} tickFormatter={(x) => fmtCompactUnits(x, units, cur)} />
                    <YAxis yAxisId="m" orientation="right" {...axisProps} width={40} tickFormatter={(x) => `${x}%`} />
                    <Tooltip cursor={{ fill: 'var(--bg-hover)' }} content={<ChartTooltip format={(x, n) => (n === 'Net margin' ? `${fmtNum(x, 1)}%` : amt(x))} />} />
                    <Bar yAxisId="a" dataKey="revenue" name="Revenue" fill={C.c2} radius={[4, 4, 0, 0]} />
                    <Bar yAxisId="a" dataKey="profit" name="Net profit" fill={C.c1} radius={[4, 4, 0, 0]} />
                    <Line yAxisId="m" dataKey="margin" name="Net margin" stroke={C.c3} strokeWidth={2} dot={false} connectNulls={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
              <Legend items={[{ label: 'Revenue', color: C.c2 }, { label: 'Net profit', color: C.c1 }, { label: 'Net margin', color: C.c3 }]} />
            </Card>
            <Card title="Returns on capital" subtitle="ROE uses average equity; ROCE uses average equity + debt">
              <div style={{ height: 250 }}>
                <ResponsiveContainer>
                  <LineChart data={chart} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid {...gridProps} />
                    <XAxis dataKey="period" {...axisProps} />
                    <YAxis {...axisProps} width={44} tickFormatter={(x) => `${x}%`} />
                    <Tooltip content={<ChartTooltip format={(x) => `${fmtNum(x, 1)}%`} />} />
                    <Line dataKey="roe" name="ROE" stroke={C.c1} strokeWidth={2} dot={{ r: 3 }} connectNulls={false} />
                    <Line dataKey="roce" name="ROCE" stroke={C.c4} strokeWidth={2} dot={{ r: 3 }} connectNulls={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <Legend items={[{ label: 'ROE', color: C.c1 }, { label: 'ROCE', color: C.c4 }]} />
            </Card>
          </div>
          <div className="grid cols-3">
            <Card title="Highlights" subtitle="Generated from the figures, not from opinion">
              <ul style={{ margin: 0, paddingLeft: 18, display: 'grid', gap: 6, fontSize: 13.5 }}>{p.highlights.map((h) => <li key={h}>{h}</li>)}</ul>
              <div className="row mt-sm" style={{ gap: 6 }}>
                {Object.values(p.cagr).filter((c) => isNum(c.value)).map((c) => <Badge key={c.label}>{c.label}: {fmtPct(c.value, 1)}</Badge>)}
              </div>
            </Card>
            <Card title="Screening scores" subtitle={`Latest year · open Red Flags for the full working`} actions={<Link className="btn sm" to="/red-flags">Details</Link>}>
              <div className="stack" style={{ gap: 8, fontSize: 13.5 }}>
                {[['Beneish M-score', 'beneish'], ["Altman Z''", 'altman_z2'], ['Altman Z', 'altman_z']].map(([label, k]) => {
                  const s = p.scores[k];
                  return <div key={k} className="metric-row"><span>{label}</span><span className="v">{isNum(s?.value) ? fmtNum(s.value, 2) : '—'} {s?.verdict ? <Badge tone={VERDICT[s.verdict].tone}>{VERDICT[s.verdict].text}</Badge> : <Badge tone="warn">needs data</Badge>}</span></div>;
                })}
                <div className="metric-row"><span>Piotroski F-score</span><span className="v">{isNum(p.scores.piotroski?.value) ? `${p.scores.piotroski.value} / ${p.scores.piotroski.tested}` : '—'}</span></div>
              </div>
            </Card>
            <Card title="Data notes">
              <div className="stack" style={{ gap: 6, fontSize: 12.5 }} >
                {p.derived.length ? p.derived.map((d) => <div key={d} className="faint">{d}</div>) : <div className="faint">All figures come directly from the company's statements.</div>}
                <div className="faint">A dash (—) means the inputs for that metric are not in the data; nothing is assumed.</div>
              </div>
            </Card>
          </div>
          <Card title="Ten-year metrics" subtitle="Hover a metric for its formula" flush>
            <div className="table-wrap" style={{ border: 0, borderRadius: 0 }}>
              <table className="data">
                <thead><tr><th>Metric</th>{p.periods.map((per) => <th key={per} className="r">{per}</th>)}</tr></thead>
                <tbody>{Object.entries(groups).map(([g, keys]) => [
                  <tr key={g}><td colSpan={p.periods.length + 1} className="faint" style={{ fontWeight: 650, fontSize: 12, background: 'var(--bg-sunken)' }}>{g}</td></tr>,
                  ...keys.filter((k) => p.series[k].some(isNum)).map((k) => (
                    <tr key={k}><td title={p.metrics[k].formula}>{p.metrics[k].label}</td>{p.series[k].map((x, i) => <td key={i} className="r">{fmt(k, x)}</td>)}</tr>
                  )),
                ])}</tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
