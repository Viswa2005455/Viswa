import { Download, FileUp, Plus, RotateCcw, Trash2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { C, axisProps, gridProps } from '../components/charts';
import { SaveLoad } from '../components/SaveLoad';
import { Badge, Callout, Card, ErrorBox, Formula, Kpi, LearnBox, NumberField, PageHeader } from '../components/ui';
import { api } from '../lib/api';
import { downloadFile, fmtCompact, fmtMoney, fmtPctPoints, isNum, toCSV } from '../lib/format';
import { useSettings } from '../lib/settings';
import { useToast } from '../lib/toast';
import type { UploadSummary } from '../lib/types';
import { useAsync, useDebounced } from '../lib/useApi';
import { loadRaw } from '../lib/storage';

interface Line { name: string; kind: 'revenue' | 'expense'; budget: number | null; actual: number | null; source?: string | null }
interface OutLine { name: string; kind: string; budget: number; actual: number; variance: number; variance_pct: number | null; status: string; profit_impact: number; material: boolean; notes: string[]; source: string | null }
interface VarRes { policy: Record<string, string>; lines: OutLine[]; totals: Record<string, OutLine>; largest_contributors: OutLine[] }

const EXAMPLE: Line[] = [
  { name: 'Product sales', kind: 'revenue', budget: 1200000, actual: 1265000 },
  { name: 'Service revenue', kind: 'revenue', budget: 300000, actual: 271500 },
  { name: 'Cost of goods sold', kind: 'expense', budget: 690000, actual: 742000 },
  { name: 'Salaries', kind: 'expense', budget: 280000, actual: 286400 },
  { name: 'Marketing', kind: 'expense', budget: 90000, actual: 72300 },
  { name: 'Rent & utilities', kind: 'expense', budget: 60000, actual: 60000 },
  { name: 'Software subscriptions', kind: 'expense', budget: 0, actual: 12500 },
];

const statusBadge = (s: string) => s === 'favourable' ? <Badge tone="accent">Favourable</Badge> : s === 'adverse' ? <Badge tone="neg">Adverse</Badge> : <Badge>On budget</Badge>;

export function Variance() {
  const { settings } = useSettings();
  const cur = settings.currency;
  const toast = useToast();
  const [params] = useSearchParams();
  const [lines, setLines] = useState<Line[]>(EXAMPLE);
  const [isExample, setIsExample] = useState(true);
  const [materiality, setMateriality] = useState<number | null>(10);
  const [importNote, setImportNote] = useState<string | null>(null);

  const uploads = useAsync((signal) => api.get<{ uploads: UploadSummary[] }>('/api/uploads', { signal }), []);
  const candidates = uploads.data?.uploads.filter((u) => u.recommendations.some((r) => r.module === 'Variance Analysis')) ?? [];

  const importFrom = async (id: string) => {
    try {
      const rec = await api.get<{ name: string; variance_lines: { lines: Line[]; note: string; sheet: string } | null }>(`/api/uploads/${id}`);
      if (!rec.variance_lines?.lines.length) { toast('No Budget/Actual columns found in that file', 'error'); return; }
      setLines(rec.variance_lines.lines);
      setIsExample(false);
      setImportNote(`Imported ${rec.variance_lines.lines.length} lines from ${rec.name} › ${rec.variance_lines.sheet}. ${rec.variance_lines.note}`);
      toast('Budget lines imported');
    } catch (e) { toast((e as Error).message, 'error'); }
  };
  const fileParam = params.get('file');
  useEffect(() => { if (fileParam) importFrom(fileParam); }, [fileParam]); // eslint-disable-line react-hooks/exhaustive-deps
  // Hand-off from the Budgeting page ("Compare with actuals").
  useEffect(() => {
    const handoff = loadRaw<{ lines: Line[]; note: string } | null>('fis.variance.import', null);
    if (handoff?.lines?.length) {
      setLines(handoff.lines);
      setIsExample(false);
      setImportNote(handoff.note);
      try { localStorage.removeItem('fis.variance.import'); } catch { /* ignore */ }
    }
  }, []);

  const incomplete = lines.some((l) => !l.name.trim() || l.budget === null || l.actual === null);
  const body = useMemo(() => (incomplete || !lines.length ? null : { lines, materiality_pct: materiality }), [lines, materiality, incomplete]);
  const req = useDebounced(body, 150);
  const res = useAsync((signal) => api.post<VarRes>('/api/finance/variance', req, { signal }), [JSON.stringify(req)], !!req);
  const r = res.data;

  const edit = (i: number, p: Partial<Line>) => { setIsExample(false); setLines((ls) => ls.map((l, j) => (j === i ? { ...l, ...p } : l))); };

  // Waterfall: budget profit -> each line's profit impact -> actual profit
  const waterfall = useMemo(() => {
    if (!r?.totals.profit) return [];
    const out: { name: string; base: number; value: number; kind: 'total' | 'up' | 'down'; raw: number }[] = [];
    let run = r.totals.profit.budget;
    out.push({ name: 'Budget profit', base: Math.min(0, run), value: Math.abs(run), kind: 'total', raw: run });
    [...r.lines].filter((l) => l.profit_impact !== 0).sort((a, b) => Math.abs(b.profit_impact) - Math.abs(a.profit_impact)).forEach((l) => {
      const next = run + l.profit_impact;
      out.push({ name: l.name, base: Math.min(run, next), value: Math.abs(l.profit_impact), kind: l.profit_impact >= 0 ? 'up' : 'down', raw: l.profit_impact });
      run = next;
    });
    out.push({ name: 'Actual profit', base: Math.min(0, run), value: Math.abs(run), kind: 'total', raw: run });
    return out;
  }, [r]);

  const exportCsv = () => {
    if (!r) return;
    const rows: unknown[][] = [['Budget vs actual', isExample ? 'EXAMPLE DATA' : 'User data'], ['Policy', r.policy.percentage], [],
      ['Line', 'Type', 'Budget', 'Actual', 'Variance', 'Variance %', 'Status', 'Material', 'Source', 'Notes'],
      ...r.lines.map((l) => [l.name, l.kind, l.budget, l.actual, l.variance, l.variance_pct ?? 'n/a', l.status, l.material ? 'yes' : '', l.source ?? '', l.notes.join(' ')]), [],
      ...Object.values(r.totals).map((t) => [t.name, '', t.budget, t.actual, t.variance, t.variance_pct ?? 'n/a', t.status]), ['Generated', new Date().toISOString()]];
    downloadFile('variance-analysis.csv', toCSV(rows));
  };

  return (
    <div className="page">
      <PageHeader title="Variance Analysis" badge={isExample ? <Badge tone="sample">Example data</Badge> : undefined}
        subtitle="Compare actual results with budget, line by line and in total. Variances are classified by their effect on profit."
        actions={<>
          <SaveLoad kind="variance" label="variance analysis" getData={() => ({ lines, materiality })}
            onLoad={(d: { lines: Line[]; materiality: number | null }) => { setLines(d.lines); setMateriality(d.materiality); setIsExample(false); setImportNote(null); }} />
          <button className="btn" onClick={() => { setLines(EXAMPLE); setIsExample(true); setImportNote(null); }}><RotateCcw size={15} />Example</button>
          <button className="btn" onClick={exportCsv} disabled={!r}><Download size={15} />Export CSV</button>
        </>} />

      <div className="grid cols-3" style={{ marginBottom: 16 }}>
        <Card title="Import from an upload" className="span-2">
          {candidates.length ? (
            <div className="row">
              {candidates.map((u) => <button key={u.id} className="btn sm" onClick={() => importFrom(u.id)}><FileUp size={14} />{u.name}</button>)}
            </div>
          ) : <p className="muted">Upload an Excel or CSV file with <b>Budget</b> and <b>Actual</b> columns and a line-item column. <Link to="/upload">Upload a file</Link></p>}
          {importNote && <div className="mt-sm"><Callout tone="warn">{importNote}</Callout></div>}
        </Card>
        <Card title="Materiality">
          <NumberField label="Flag variances of at least" suffix="%" value={materiality} onChange={setMateriality} min={0} />
        </Card>
      </div>

      {r && (
        <div className="grid cols-4" style={{ marginBottom: 16 }}>
          {(['revenue', 'expense', 'profit'] as const).filter((k) => r.totals[k]).map((k) => {
            const t = r.totals[k];
            return <Kpi key={k} label={`${t.name} variance`} value={`${t.variance >= 0 ? '+' : '−'}${fmtMoney(Math.abs(t.variance), cur)}`}
              delta={<>{t.status === 'favourable' ? 'Favourable' : t.status === 'adverse' ? 'Adverse' : 'On budget'} · {fmtPctPoints(t.variance_pct)}</>}
              deltaTone={t.status === 'favourable' ? 'pos' : t.status === 'adverse' ? 'neg' : 'muted'} />;
          })}
          <Kpi label="Material lines" value={String(r.lines.filter((l) => l.material).length)} delta={`of ${r.lines.length} lines (≥ ${materiality ?? 0}%)`} />
        </div>
      )}

      <Card title="Budget lines" subtitle="Type decides direction: revenue above budget is favourable; expense above budget is adverse." flush>
        <div className="table-wrap" tabIndex={0} style={{ border: 0, borderRadius: 0 }}>
          <table className="data">
            <thead><tr><th>Line item</th><th>Type</th><th className="r">Budget</th><th className="r">Actual</th><th className="r">Variance</th><th className="r">Variance %</th><th>Status</th><th /></tr></thead>
            <tbody>
              {lines.map((l, i) => {
                const o = r && !incomplete && r.lines.length === lines.length ? r.lines[i] : undefined;
                return (
                  <tr key={i} style={o?.material ? { background: o.status === 'adverse' ? 'var(--negative-soft)' : 'var(--accent-soft)' } : undefined}>
                    <td style={{ minWidth: 180 }}>
                      <input className="input compact" aria-label="Line item" value={l.name} onChange={(e) => edit(i, { name: e.target.value })} />
                      {l.source && <div className="faint" style={{ fontSize: 11 }} title={l.source}>Source: {l.source.split(' › ').slice(-1)[0]}</div>}
                    </td>
                    <td>
                      <select className="input compact" style={{ minWidth: 112 }} aria-label="Type" value={l.kind} onChange={(e) => edit(i, { kind: e.target.value as Line['kind'] })}>
                        <option value="revenue">Revenue</option><option value="expense">Expense</option>
                      </select>
                    </td>
                    <td style={{ minWidth: 120 }}><NumberField compact ariaLabel="Budget" value={l.budget} required onChange={(v) => edit(i, { budget: v })} /></td>
                    <td style={{ minWidth: 120 }}><NumberField compact ariaLabel="Actual" value={l.actual} required onChange={(v) => edit(i, { actual: v })} /></td>
                    <td className={`r ${o ? (o.profit_impact >= 0 ? 'pos' : 'neg') : ''}`}>{o ? fmtMoney(o.variance, cur) : '—'}</td>
                    <td className="r" title={o?.notes.join(' ')}>{o ? (isNum(o.variance_pct) ? fmtPctPoints(o.variance_pct) : <span className="faint">n/a</span>) : '—'}</td>
                    <td>{o && statusBadge(o.status)}</td>
                    <td><button className="btn icon sm ghost" aria-label={`Remove ${l.name}`} onClick={() => { setIsExample(false); setLines((ls) => ls.filter((_, j) => j !== i)); }}><Trash2 size={14} /></button></td>
                  </tr>
                );
              })}
            </tbody>
            {r && !incomplete && (
              <tfoot>
                {Object.values(r.totals).map((t) => (
                  <tr key={t.name}><td>{t.name}</td><td /><td className="r">{fmtMoney(t.budget, cur)}</td><td className="r">{fmtMoney(t.actual, cur)}</td>
                    <td className={`r ${t.profit_impact >= 0 ? 'pos' : 'neg'}`}>{fmtMoney(t.variance, cur)}</td><td className="r">{fmtPctPoints(t.variance_pct)}</td><td>{statusBadge(t.status)}</td><td /></tr>
                ))}
              </tfoot>
            )}
          </table>
        </div>
        <div style={{ padding: '12px 18px' }} className="row">
          <button className="btn sm" onClick={() => { setIsExample(false); setLines((ls) => [...ls, { name: '', kind: 'expense', budget: null, actual: null }]); }}><Plus size={14} />Add line</button>
          {incomplete && <span className="faint" style={{ fontSize: 12.5 }}>Complete every name, budget and actual to calculate. Blanks are not treated as zero.</span>}
        </div>
      </Card>
      {res.error && <div className="mt"><ErrorBox error={res.error} /></div>}

      {r && r.lines.some((l) => l.notes.length) && (
        <div className="mt"><Callout tone="info" title="Notes on percentages">
          <ul>{r.lines.filter((l) => l.notes.length).map((l) => <li key={l.name}><b>{l.name}:</b> {l.notes.join(' ')}</li>)}</ul>
        </Callout></div>
      )}

      {r && waterfall.length > 0 && (
        <div className="grid cols-3 mt">
          <Card className="span-2" title="Profit bridge: budget to actual" subtitle="Each bar is a line's effect on profit (green helps, orange hurts)">
            <div className="chart tall">
              <ResponsiveContainer>
                <BarChart data={waterfall} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid {...gridProps} />
                  <XAxis dataKey="name" {...axisProps} interval={0} angle={-20} textAnchor="end" height={64} />
                  <YAxis {...axisProps} width={60} tickFormatter={(v) => fmtCompact(v, cur)} />
                  <Tooltip cursor={{ fill: 'var(--bg-hover)' }} content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const p = payload[0].payload as (typeof waterfall)[number];
                    return <div className="chart-tooltip"><div className="t">{p.name}</div><b className="num">{p.kind === 'total' ? fmtMoney(p.raw, cur) : `${p.raw >= 0 ? '+' : ''}${fmtMoney(p.raw, cur)}`}</b></div>;
                  }} />
                  <Bar dataKey="base" stackId="w" fill="transparent" isAnimationActive={false} />
                  <Bar dataKey="value" stackId="w" radius={3} maxBarSize={44}>
                    {waterfall.map((w) => <Cell key={w.name} fill={w.kind === 'total' ? C.c3 : w.kind === 'up' ? C.c1 : C.neg} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
          <Card title="Largest contributors" subtitle="By effect on profit">
            {r.largest_contributors.map((l) => (
              <div key={l.name} className="metric-row"><span>{l.name}</span><span className={`v ${l.profit_impact >= 0 ? 'pos' : 'neg'}`}>{l.profit_impact >= 0 ? '+' : ''}{fmtMoney(l.profit_impact, cur)}</span></div>
            ))}
            <div className="mt"><Callout tone="info">Causes are not inferred from numbers alone. Any explanation of <i>why</i> a variance occurred is a hypothesis until supported by evidence (volumes, prices, invoices).</Callout></div>
          </Card>
        </div>
      )}

      <div className="grid cols-2 mt" style={{ alignItems: 'start' }}>
        <PriceVolume />
        <LearnBox title="Variance analysis">
          <div className="stack" style={{ fontSize: 13 }}>
            <Formula>{`Absolute variance = Actual − Budget
Variance % = (Actual − Budget) / |Budget| × 100`}</Formula>
            <p>Revenue above budget is <b>favourable (F)</b>; costs above budget are <b>adverse (A)</b>. A zero budget has no meaningful percentage, so only the absolute variance is shown.</p>
            <p><b>Common mistake:</b> reading a favourable cost variance as good news without checking volume — lower costs may simply reflect lower sales. Flexible budgets separate volume effects from spending effects.</p>
          </div>
        </LearnBox>
      </div>
    </div>
  );
}

function PriceVolume() {
  const { settings } = useSettings();
  const [bp, setBp] = useState<number | null>(500);
  const [bq, setBq] = useState<number | null>(2400);
  const [ap, setAp] = useState<number | null>(530);
  const [aq, setAq] = useState<number | null>(2387);
  const ok = [bp, bq, ap, aq].every(isNum);
  const req = useDebounced(ok ? { budget_price: bp, budget_quantity: bq, actual_price: ap, actual_quantity: aq } : null, 150);
  const res = useAsync((signal) => api.post<Record<string, number>>('/api/finance/variance/price-volume', req, { signal }), [JSON.stringify(req)], !!req);
  const r = res.data;
  const cur = settings.currency;
  return (
    <Card title="Sales price & volume variance" subtitle="Splits the revenue variance into price and volume effects (example inputs)">
      <div className="form-grid">
        <NumberField label="Budget price" value={bp} onChange={setBp} required />
        <NumberField label="Budget quantity" value={bq} onChange={setBq} required min={0} />
        <NumberField label="Actual price" value={ap} onChange={setAp} required />
        <NumberField label="Actual quantity" value={aq} onChange={setAq} required min={0} />
      </div>
      {res.error && <div className="mt-sm"><ErrorBox error={res.error} /></div>}
      {r && (
        <div className="mt">
          <div className="metric-row"><span>Price variance = (AP − BP) × AQ</span><span className={`v ${r.price_variance >= 0 ? 'pos' : 'neg'}`}>{fmtMoney(r.price_variance, cur)} {r.price_variance >= 0 ? 'F' : 'A'}</span></div>
          <div className="metric-row"><span>Volume variance = (AQ − BQ) × BP</span><span className={`v ${r.volume_variance >= 0 ? 'pos' : 'neg'}`}>{fmtMoney(r.volume_variance, cur)} {r.volume_variance >= 0 ? 'F' : 'A'}</span></div>
          <div className="metric-row"><span><b>Total revenue variance</b></span><span className="v">{fmtMoney(r.total_variance, cur)}</span></div>
        </div>
      )}
    </Card>
  );
}
