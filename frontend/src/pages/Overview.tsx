import { ArrowDownRight, ArrowUpRight, Calculator, FileUp, Landmark, Layers, Lightbulb, Percent, TrendingUp, FileText } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Area, Bar, BarChart, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { C, ChartTooltip, Legend, axisProps, gridProps } from '../components/charts';
import { Badge, Card, EmptyState, ErrorBox, Kpi, PageHeader, SampleBadge, Skeleton, SkeletonCards } from '../components/ui';
import { api } from '../lib/api';
import { fmtNum, fmtPctPoints, fmtRatio, isNum } from '../lib/format';
import type { UploadSummary } from '../lib/types';
import { useAsync } from '../lib/useApi';
import { useAuth } from '../lib/auth';
import { useProjects } from '../lib/project';
import { useState } from 'react';
import { CompanyDashboard } from '../components/CompanyDashboard';
import { useCompanySources } from '../lib/company';
import { loadRaw } from '../lib/storage';

interface Dashboard {
  is_sample: boolean; company: string; currency: string; units: string; period: string;
  kpis: Record<string, { value: number; prior?: number; pct?: number | null; status?: string; label: string }>;
  trend: { period: string; revenue: number; ebitda: number; net_income: number; budget_revenue: number }[];
  forecast: { period: string; revenue: number; lower: number | null; upper: number | null }[];
  forecast_method: string;
  budget_vs_actual: { period: string; budget: number; actual: number }[];
  health: { key: string; name: string; value: number | null; unit: string; interpretation: string }[];
  insights: string[];
}

const L = (v: number | null | undefined, d = 1) => (isNum(v) ? `₹${fmtNum(v, d)} L` : '—');

function delta(v: number, prior?: number) {
  if (!isNum(prior) || prior === 0) return { text: undefined, tone: 'muted' as const };
  const pct = ((v - prior) / Math.abs(prior)) * 100;
  const Icon = pct >= 0 ? ArrowUpRight : ArrowDownRight;
  return { text: <><Icon size={14} />{fmtPctPoints(Math.abs(pct))} vs prior month</>, tone: pct >= 0 ? 'pos' as const : 'neg' as const };
}

function SampleOverview({ hasCompanies, onBack }: { hasCompanies: boolean; onBack: () => void }) {
  const dash = useAsync(() => api.get<Dashboard>('/api/dashboard/sample'), []);
  const { user } = useAuth();
  const { active, activeId } = useProjects();
  const uploads = useAsync(() => api.get<{ uploads: UploadSummary[] }>(`/api/uploads${activeId ? `?project_id=${activeId}` : ''}`), [activeId]);
  const d = dash.data;

  const chartData = d ? [
    ...d.trend.map((t, i) => ({ ...t, forecast: i === d.trend.length - 1 ? t.revenue : null, band: null as [number, number] | null })),
    ...d.forecast.map((f) => ({ period: f.period, forecast: f.revenue, band: isNum(f.lower) && isNum(f.upper) ? [f.lower, f.upper] as [number, number] : null })),
  ] : [];

  return (
    <div className="page">
      <PageHeader
        title={`Welcome back, ${user?.display_name.split(' ')[0] ?? ''}`}
        subtitle={<>The dashboard below uses a <b>fictional sample company</b> to demonstrate the analysis engine. Your own files and saved models live in <Link to="/projects">your projects</Link>{active ? <> — active project: <b>{active.name}</b></> : null}.</>}
        badge={<SampleBadge />}
        actions={<>
          {hasCompanies ? <button className="btn" onClick={onBack}>Back to my companies</button> : <Link to="/statements" className="btn">Import a company</Link>}
          <Link to="/upload" className="btn primary"><FileUp size={16} />Upload data</Link>
        </>}
      />

      {dash.error && <ErrorBox error={dash.error} onRetry={dash.reload} />}
      {dash.loading && !d && <SkeletonCards n={5} />}

      {d && (
        <>
          <div className="row between" style={{ marginBottom: 10 }}>
            <div className="faint" style={{ fontSize: 12 }}>{d.company} · {d.period} · values in ₹ lakhs</div>
          </div>
          <div className="grid cols-5">
            {(['revenue', 'ebitda', 'net_income', 'operating_cash_flow'] as const).map((k) => {
              const kp = d.kpis[k];
              const dl = delta(kp.value, kp.prior);
              return <Kpi key={k} label={kp.label} value={L(kp.value)} delta={dl.text} deltaTone={dl.tone} />;
            })}
            <Kpi label={d.kpis.budget_variance.label} value={`${d.kpis.budget_variance.value >= 0 ? '+' : '−'}${L(Math.abs(d.kpis.budget_variance.value))}`}
              delta={<>{d.kpis.budget_variance.status === 'favourable' ? 'Favourable' : d.kpis.budget_variance.status === 'adverse' ? 'Adverse' : 'On budget'}
                {isNum(d.kpis.budget_variance.pct) && <> · {fmtPctPoints(d.kpis.budget_variance.pct)}</>}</>}
              deltaTone={d.kpis.budget_variance.status === 'favourable' ? 'pos' : d.kpis.budget_variance.status === 'adverse' ? 'neg' : 'muted'} />
          </div>

          <div className="grid cols-3 mt">
            <Card className="span-2" title="Revenue: actual and forecast" subtitle={`${d.forecast_method}. Forecasts are estimates, not guarantees.`}
              actions={<SampleBadge />}>
              <div className="chart tall">
                <ResponsiveContainer>
                  <ComposedChart data={chartData} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
                    <defs>
                      <linearGradient id="revFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.28} />
                        <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid {...gridProps} />
                    <XAxis dataKey="period" {...axisProps} />
                    <YAxis {...axisProps} width={56} tickFormatter={(v) => fmtNum(v, 0)} />
                    <Tooltip content={<ChartTooltip format={(v) => L(v)} />} />
                    <Area dataKey="band" name="Prediction interval" stroke="none" fill={C.band} isAnimationActive />
                    <Area dataKey="revenue" name="Revenue (actual)" stroke={C.c1} strokeWidth={2.2} fill="url(#revFill)" dot={false} />
                    <Line dataKey="budget_revenue" name="Budget" stroke={C.c3} strokeWidth={1.6} strokeDasharray="2 4" dot={false} />
                    <Line dataKey="forecast" name="Forecast" stroke={C.c2} strokeWidth={2.2} strokeDasharray="6 4" dot={false} />
                    <Line dataKey="ebitda" name="EBITDA" stroke={C.c4} strokeWidth={1.8} dot={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
              <Legend items={[{ label: 'Revenue (actual)', color: 'var(--chart-1)' }, { label: 'Forecast', color: 'var(--chart-2)', dashed: true },
                { label: 'Prediction interval (90%)', color: 'var(--chart-band)' }, { label: 'Budget', color: 'var(--chart-3)', dashed: true },
                { label: 'EBITDA', color: 'var(--chart-4)' }]} />
            </Card>

            <Card title="Financial health" subtitle="Trailing 12 months, from the ratio engine" actions={<SampleBadge text="Sample" />}>
              <div className="list">
                {d.health.map((h) => (
                  <div key={h.key} className="list-item">
                    <div className="grow">
                      <div style={{ fontWeight: 550 }}>{h.name}</div>
                      <div className="faint truncate" style={{ fontSize: 12 }}>{h.interpretation}</div>
                    </div>
                    <b className="num">{fmtRatio(h.value, h.unit)}</b>
                  </div>
                ))}
              </div>
              <Link to="/ratios" className="btn sm mt" style={{ width: '100%' }}>Open Ratio Analysis</Link>
            </Card>

            <Card className="span-2" title="Budget vs actual revenue" subtitle="Monthly, ₹ lakhs" actions={<SampleBadge />}>
              <div className="chart">
                <ResponsiveContainer>
                  <BarChart data={d.budget_vs_actual} margin={{ top: 8, right: 8, left: -8, bottom: 0 }} barGap={2}>
                    <CartesianGrid {...gridProps} />
                    <XAxis dataKey="period" {...axisProps} />
                    <YAxis {...axisProps} width={56} tickFormatter={(v) => fmtNum(v, 0)} />
                    <Tooltip cursor={{ fill: 'var(--bg-hover)' }} content={<ChartTooltip format={(v) => L(v)} />} />
                    <Bar dataKey="budget" name="Budget" fill={C.c3} radius={[4, 4, 0, 0]} maxBarSize={18} />
                    <Bar dataKey="actual" name="Actual" fill={C.c1} radius={[4, 4, 0, 0]} maxBarSize={18} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <Legend items={[{ label: 'Budget', color: 'var(--chart-3)' }, { label: 'Actual', color: 'var(--chart-1)' }]} />
            </Card>

            <Card title="Insights" subtitle="Computed from validated sample figures" actions={<Lightbulb size={17} className="faint" />}>
              <ul style={{ margin: 0, paddingLeft: 18, display: 'grid', gap: 8 }}>
                {d.insights.map((i) => <li key={i}>{i}</li>)}
              </ul>
            </Card>
          </div>
        </>
      )}

      <div className="grid cols-3 mt">
        <Card title="Quick actions" className="span-2">
          <div className="grid cols-3">
            {[
              { to: '/dcf', icon: Landmark, t: 'DCF valuation', s: 'FCFF, WACC, terminal value' },
              { to: '/investment', icon: Calculator, t: 'NPV & IRR', s: 'Appraise project cash flows' },
              { to: '/ratios', icon: Percent, t: 'Ratio analysis', s: '25+ ratios with formulas' },
              { to: '/scenarios', icon: Layers, t: 'Scenarios', s: 'Base, optimistic, pessimistic' },
              { to: '/forecasting', icon: TrendingUp, t: 'Forecast', s: 'Trend, smoothing, CAGR' },
              { to: '/variance', icon: FileText, t: 'Variance', s: 'Budget vs actual' },
            ].map((q) => (
              <Link key={q.to} to={q.to} className="card interactive" style={{ padding: 14, textDecoration: 'none', color: 'inherit' }}>
                <q.icon size={18} className="pos" />
                <div style={{ fontWeight: 600, marginTop: 8 }}>{q.t}</div>
                <div className="faint" style={{ fontSize: 12 }}>{q.s}</div>
              </Link>
            ))}
          </div>
        </Card>
        <Card title="Recent uploads" subtitle={active ? `In ${active.name} (your data, never mixed with the sample)` : "Your files (real data, never mixed with the sample)"}>
          {uploads.loading && !uploads.data ? <Skeleton h={60} /> : uploads.error ? <ErrorBox error={uploads.error} /> :
            uploads.data?.uploads.length ? (
              <div className="list">
                {uploads.data.uploads.slice(0, 5).map((u) => (
                  <Link key={u.id} to={`/upload?file=${u.id}`} className="list-item" style={{ color: 'inherit', textDecoration: 'none' }}>
                    <div className="grow">
                      <div className="truncate" style={{ fontWeight: 550 }}>{u.name}</div>
                      <div className="faint truncate" style={{ fontSize: 12 }}>{u.summary}</div>
                    </div>
                    <Badge tone={u.status === 'failed' ? 'neg' : 'accent'}>{u.label}</Badge>
                  </Link>
                ))}
              </div>
            ) : (
              <EmptyState icon={<FileUp size={22} />} title="No uploads yet" action={<Link className="btn sm" to="/upload">Upload a file</Link>}>
                Excel, CSV, PDF, Word, code and more.
              </EmptyState>
            )}
        </Card>
      </div>
    </div>
  );
}

/** Shows the user's own company when one has been imported or saved; the labelled sample otherwise. */
export function Overview() {
  const { user } = useAuth();
  const { sources } = useCompanySources();
  const [sample, setSample] = useState(false);
  const real = (sources ?? []).filter((s) => !s.isExample);
  if (!sources) return <div className="page"><SkeletonCards n={4} /></div>;
  if (!real.length || sample) return <SampleOverview hasCompanies={real.length > 0} onBack={() => setSample(false)} />;
  const initial = loadRaw<string>('fis.dashboard.company', '') || real[0].id;
  return (
    <div className="page">
      <PageHeader title={`Welcome back, ${user?.display_name.split(' ')[0] ?? ''}`} badge={<Badge tone="accent">Your data</Badge>}
        subtitle="Company dashboard built from your imported statements. Every figure is calculated from the source data; missing inputs show as a dash."
        actions={<>
          <button className="btn" onClick={() => setSample(true)}>View sample dashboard</button>
          <Link to="/statements" className="btn primary"><FileUp size={16} />Import a company</Link>
        </>} />
      <CompanyDashboard sources={real} initialId={real.some((s) => s.id === initial) ? initial : real[0].id} />
    </div>
  );
}
