import { CheckCircle2, CircleSlash, Download, FileUp, Plus, RotateCcw, Trash2, XCircle } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { C, ChartTooltip, Legend, axisProps, gridProps } from '../components/charts';
import { SaveLoad } from '../components/SaveLoad';
import { Badge, Callout, Card, ErrorBox, Kpi, LearnBox, NumberField, PageHeader, Tabs, Warnings } from '../components/ui';
import { api } from '../lib/api';
import { downloadFile, fmtCompact, fmtNum, fmtPct, fmtPctPoints, isNum, toCSV } from '../lib/format';
import { useSettings } from '../lib/settings';
import { loadRaw, save } from '../lib/storage';
import { useToast } from '../lib/toast';
import type { UploadSummary } from '../lib/types';
import { useAsync, useDebounced } from '../lib/useApi';

type Stmt = 'income' | 'balance' | 'cashflow';
interface Line { label: string; statement: Stmt; key: string | null; values: (number | null)[]; source?: string | null }
interface Data { periods: string[]; lines: Line[] }
interface Change { absolute: number | null; pct: number | null; note: string | null }
interface Report {
  periods: string[];
  lines: { label: string; statement: Stmt; key: string | null; values: (number | null)[]; changes: (Change | null)[]; common_size: (number | null)[]; cagr: number | null; source: string | null }[];
  metrics: Record<string, (number | null)[]>;
  checks: { name: string; period: string; status: 'pass' | 'fail' | 'insufficient'; difference: number | null; detail: string }[];
  quality_flags: string[]; notes: string[];
}
interface Suggested { sheet: string; statement: Stmt; periods: string[]; reordered: boolean; lines: { label: string; key: string | null; values: (number | null)[]; source: string | null }[] }

const STMTS: { value: Stmt; label: string }[] = [{ value: 'income', label: 'Income statement' }, { value: 'balance', label: 'Balance sheet' }, { value: 'cashflow', label: 'Cash flow statement' }];

const ex = (label: string, statement: Stmt, values: number[], key: string): Line => ({ label, statement, key, values });
const EXAMPLE: Data = {
  periods: ['FY2023', 'FY2024', 'FY2025'],
  lines: [
    ex('Revenue', 'income', [1000, 1200, 1500], 'revenue'), ex('Cost of goods sold', 'income', [600, 700, 900], 'cogs'),
    ex('Gross profit', 'income', [400, 500, 600], 'gross_profit'), ex('Operating expenses', 'income', [200, 240, 290], 'operating_expenses'),
    ex('Depreciation & amortisation', 'income', [50, 60, 70], 'depreciation_amortization'), ex('Operating income (EBIT)', 'income', [150, 200, 240], 'operating_income'),
    ex('Interest expense', 'income', [20, 15, 10], 'interest_expense'), ex('Profit before tax', 'income', [130, 185, 230], 'pretax_income'),
    ex('Income tax', 'income', [30, 45, 55], 'income_tax'), ex('Net income', 'income', [100, 140, 175], 'net_income'),
    ex('Cash & equivalents', 'balance', [80, 100, 120], 'cash'), ex('Trade receivables', 'balance', [150, 180, 300], 'receivables'),
    ex('Inventory', 'balance', [100, 120, 150], 'inventory'), ex('Total current assets', 'balance', [350, 420, 590], 'current_assets'),
    ex('Property, plant & equipment', 'balance', [650, 680, 710], 'ppe'), ex('Total assets', 'balance', [1000, 1100, 1300], 'total_assets'),
    ex('Trade payables', 'balance', [90, 100, 110], 'accounts_payable'), ex('Total current liabilities', 'balance', [200, 230, 260], 'current_liabilities'),
    ex('Total debt', 'balance', [300, 290, 340], 'total_debt'), ex('Total liabilities', 'balance', [500, 520, 600], 'total_liabilities'),
    ex('Total equity', 'balance', [500, 580, 700], 'total_equity'),
    ex('Cash from operating activities', 'cashflow', [90, 120, 110], 'operating_cash_flow'), ex('Capital expenditure', 'cashflow', [-40, -50, -60], 'capex'),
    ex('Cash from investing activities', 'cashflow', [-40, -50, -60], 'investing_cash_flow'), ex('Cash from financing activities', 'cashflow', [-30, -50, -30], 'financing_cash_flow'),
    ex('Net change in cash', 'cashflow', [20, 20, 20], 'net_change_in_cash'), ex('Cash at beginning of year', 'cashflow', [60, 80, 100], 'beginning_cash'),
    ex('Cash at end of year', 'cashflow', [80, 100, 120], 'ending_cash'),
  ],
};

const METRIC_LABELS: [string, string, 'pct' | 'num' | 'x'][] = [
  ['gross_margin_pct', 'Gross margin', 'pct'], ['ebitda', 'EBITDA', 'num'], ['ebitda_margin_pct', 'EBITDA margin', 'pct'],
  ['operating_margin_pct', 'Operating margin', 'pct'], ['net_margin_pct', 'Net margin', 'pct'], ['free_cash_flow', 'Free cash flow (OCF − CapEx)', 'num'],
  ['fcf_margin_pct', 'FCF margin', 'pct'], ['net_working_capital', 'Net working capital (CA − CL)', 'num'], ['change_in_nwc', 'Change in NWC', 'num'],
  ['cash_conversion', 'Cash conversion (OCF / net income)', 'x'], ['accruals_ratio_pct', 'Accruals ratio ((NI − OCF) / avg assets)', 'pct'], ['capex_to_da', 'CapEx / D&A', 'x'],
];
const fmtMetric = (v: number | null | undefined, kind: string) => (kind === 'pct' ? fmtPctPoints(v, 1) : kind === 'x' ? (isNum(v) ? `${fmtNum(v, 2)}×` : '—') : fmtNum(v, 1));

export function Statements() {
  const toast = useToast();
  const { settings } = useSettings();
  const [params] = useSearchParams();
  const [state, setState] = useState<{ data: Data; isExample: boolean }>(() => loadRaw('fis.statements', { data: EXAMPLE, isExample: true }));
  const { data, isExample } = state;
  const setData = (d: Data, example = false) => { const s = { data: d, isExample: example }; setState(s); save('fis.statements', s); };
  const [tab, setTab] = useState<'overview' | 'horizontal' | 'vertical' | 'checks' | 'edit'>('overview');
  const [pending, setPending] = useState<{ file: string; sheets: (Suggested & { use: boolean })[] } | null>(null);

  const items = useAsync(() => api.get<{ items: Record<string, { statement: Stmt; label: string }> }>('/api/finance/statements/items'), []);
  const uploads = useAsync(() => api.get<{ uploads: UploadSummary[] }>('/api/uploads'), []);
  const candidates = uploads.data?.uploads.filter((u) => u.recommendations.some((r) => r.module === 'Financial Statements')) ?? [];

  const loadFrom = async (id: string) => {
    try {
      const rec = await api.get<{ name: string; statements: Suggested[] }>(`/api/uploads/${id}`);
      if (!rec.statements?.length) { toast('No statement-shaped sheets found in that file', 'error'); return; }
      setPending({ file: rec.name, sheets: rec.statements.map((s) => ({ ...s, use: true })) });
      setTab('overview');
    } catch (e) { toast((e as Error).message, 'error'); }
  };
  const fileParam = params.get('file');
  useEffect(() => { if (fileParam) loadFrom(fileParam); }, [fileParam]); // eslint-disable-line react-hooks/exhaustive-deps

  const applyImport = () => {
    if (!pending) return;
    const chosen = pending.sheets.filter((s) => s.use);
    const periods: string[] = [];
    chosen.forEach((s) => s.periods.forEach((p) => { if (!periods.includes(p)) periods.push(p); }));
    const used = new Set<string>();
    const lines: Line[] = chosen.flatMap((s) => s.lines.map((l) => {
      const key = l.key && !used.has(l.key) ? l.key : null;
      if (key) used.add(key);
      return { label: l.label, statement: s.statement, key, source: l.source, values: periods.map((p) => { const i = s.periods.indexOf(p); return i >= 0 ? l.values[i] : null; }) };
    }));
    setData({ periods, lines });
    setPending(null);
    toast(`Imported ${lines.length} lines across ${periods.length} periods`);
  };

  const complete = data.lines.every((l) => l.label.trim()) && data.periods.every((p) => p.trim());
  const body = useMemo(() => (complete ? { periods: data.periods, lines: data.lines.map((l) => ({ ...l, key: l.key || null })) } : null), [data, complete]);
  const req = useDebounced(body, 300);
  const res = useAsync(() => api.post<Report>('/api/finance/statements', req), [JSON.stringify(req)], !!req);
  const r = res.data;
  const last = (r?.periods.length ?? 1) - 1;
  const lineByKey = (k: string) => r?.lines.find((l) => l.key === k);
  const fails = r?.checks.filter((c) => c.status === 'fail') ?? [];

  const chart = r ? r.periods.map((p, i) => ({
    period: p, revenue: lineByKey('revenue')?.values[i] ?? null, net_income: lineByKey('net_income')?.values[i] ?? null,
    fcf: r.metrics.free_cash_flow[i], ocf: lineByKey('operating_cash_flow')?.values[i] ?? null,
    gm: r.metrics.gross_margin_pct[i], nm: r.metrics.net_margin_pct[i],
  })) : [];

  const exportCsv = () => {
    if (!r) return;
    const rows: unknown[][] = [['Financial statement analysis', isExample ? 'EXAMPLE DATA' : 'User data'], [],
      ['Statement', 'Line', 'Standard item', ...r.periods, ...r.periods.slice(1).map((p) => `Δ% ${p}`), ...r.periods.map((p) => `Common-size % ${p}`), 'CAGR', 'Source'],
      ...r.lines.map((l) => [l.statement, l.label, l.key ?? '', ...l.values.map((v) => v ?? ''), ...l.changes.slice(1).map((c) => c?.pct ?? ''),
        ...l.common_size.map((v) => v ?? ''), l.cagr ?? '', l.source ?? '']), [],
      ['Metric', ...r.periods], ...METRIC_LABELS.map(([k, label]) => [label, ...r.metrics[k].map((v) => v ?? '')]), [],
      ['Check', 'Period', 'Status', 'Difference', 'Detail'], ...r.checks.map((c) => [c.name, c.period, c.status, c.difference ?? '', c.detail]), [],
      ['Quality indicators'], ...r.quality_flags.map((f) => [f]), ['Generated', new Date().toISOString()]];
    downloadFile('financial-statement-analysis.csv', toCSV(rows));
  };

  return (
    <div className="page">
      <PageHeader title="Financial Statements" badge={isExample ? <Badge tone="sample">Example data</Badge> : <Badge tone="accent">Your data</Badge>}
        subtitle="Horizontal (period-over-period), vertical (common-size) and reconciliation analysis of the income statement, balance sheet and cash flow statement."
        actions={<>
          <SaveLoad kind="statements" label="statements" getData={() => data} onLoad={(d: Data) => setData(d)} />
          <button className="btn" onClick={() => setData(EXAMPLE, true)}><RotateCcw size={15} />Example</button>
          <button className="btn" onClick={exportCsv} disabled={!r}><Download size={15} />Export CSV</button>
        </>} />

      <Card title="Import from an upload" subtitle="Sheets with line items in the first column and periods across the top">
        {candidates.length ? <div className="row">{candidates.map((u) => <button key={u.id} className="btn sm" onClick={() => loadFrom(u.id)}><FileUp size={14} />{u.name}</button>)}</div>
          : <p className="muted">No statement files uploaded yet. <Link to="/upload">Upload an Excel or CSV statement</Link>, or edit the data below.</p>}
      </Card>

      {pending && (
        <div className="mt">
          <Card title={`Confirm sheets from ${pending.file}`} subtitle="Choose which sheets to import and check each statement type. Standard-item mappings can be changed in the Edit data tab.">
            <div className="stack">
              {pending.sheets.map((s, i) => (
                <div key={s.sheet} className="row" style={{ borderBottom: '1px solid var(--border)', paddingBottom: 8 }}>
                  <input type="checkbox" checked={s.use} aria-label={`Import ${s.sheet}`} onChange={(e) => setPending({ ...pending, sheets: pending.sheets.map((x, j) => j === i ? { ...x, use: e.target.checked } : x) })} />
                  <b style={{ minWidth: 160 }}>{s.sheet}</b>
                  <select className="input compact" style={{ width: 190 }} aria-label="Statement type" value={s.statement}
                    onChange={(e) => setPending({ ...pending, sheets: pending.sheets.map((x, j) => j === i ? { ...x, statement: e.target.value as Stmt } : x) })}>
                    {STMTS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                  </select>
                  <span className="faint" style={{ fontSize: 12.5 }}>{s.lines.length} lines · {s.periods.join(', ')} · {s.lines.filter((l) => l.key).length} recognised{s.reordered ? ' · periods reordered oldest-first' : ''}</span>
                </div>
              ))}
              <Callout tone="warn">Confirm that all sheets use the same currency, units and fiscal periods before importing.</Callout>
              <div className="row"><button className="btn primary" onClick={applyImport}>Import selected sheets</button><button className="btn" onClick={() => setPending(null)}>Cancel</button></div>
            </div>
          </Card>
        </div>
      )}

      <div className="row between mt">
        <Tabs label="View" value={tab} onChange={setTab} options={[
          { value: 'overview', label: 'Overview' }, { value: 'horizontal', label: 'Horizontal' }, { value: 'vertical', label: 'Common-size' },
          { value: 'checks', label: <>Checks {fails.length > 0 && <Badge tone="neg">{fails.length}</Badge>}</> }, { value: 'edit', label: 'Edit data' }]} />
        {r && <span className="faint" style={{ fontSize: 12.5 }}>{r.lines.length} lines · {r.periods.length} periods · {settings.units}</span>}
      </div>
      {res.error && <div className="mt"><ErrorBox error={res.error} /></div>}
      {!complete && <div className="mt"><Callout tone="warn">Every line and period needs a name.</Callout></div>}

      <div className="mt">
        {tab === 'overview' && r && (
          <div className="stack">
            <div className="grid cols-5">
              <Kpi label={`Revenue growth (${r.periods[last]})`} value={fmtPctPoints(lineByKey('revenue')?.changes[last]?.pct, 1)} />
              <Kpi label="Revenue CAGR" value={fmtPct(lineByKey('revenue')?.cagr, 1)} delta={`${r.periods[0]}–${r.periods[last]}`} />
              <Kpi label={`Net margin (${r.periods[last]})`} value={fmtPctPoints(r.metrics.net_margin_pct[last], 1)} />
              <Kpi label={`Free cash flow (${r.periods[last]})`} value={fmtNum(r.metrics.free_cash_flow[last], 1)} />
              <Kpi label="Reconciliation checks" value={`${r.checks.filter((c) => c.status === 'pass').length}/${r.checks.filter((c) => c.status !== 'insufficient').length}`}
                delta={fails.length ? `${fails.length} failed` : 'All testable checks pass'} deltaTone={fails.length ? 'neg' : 'pos'} />
            </div>
            <div className="grid cols-2">
              <Card title="Revenue, net income and margins">
                <div className="chart">
                  <ResponsiveContainer>
                    <ComposedChart data={chart} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid {...gridProps} />
                      <XAxis dataKey="period" {...axisProps} />
                      <YAxis yAxisId="v" {...axisProps} width={52} tickFormatter={(v) => fmtCompact(v)} />
                      <YAxis yAxisId="p" orientation="right" {...axisProps} width={44} tickFormatter={(v) => `${v}%`} />
                      <Tooltip cursor={{ fill: 'var(--bg-hover)' }} content={<ChartTooltip format={(v, n) => (n.includes('margin') ? fmtPctPoints(v, 1) : fmtNum(v, 1))} />} />
                      <Bar yAxisId="v" dataKey="revenue" name="Revenue" fill={C.c1} radius={[4, 4, 0, 0]} maxBarSize={36} />
                      <Bar yAxisId="v" dataKey="net_income" name="Net income" fill={C.c2} radius={[4, 4, 0, 0]} maxBarSize={36} />
                      <Line yAxisId="p" dataKey="gm" name="Gross margin" stroke={C.c4} strokeWidth={2} dot={{ r: 3 }} />
                      <Line yAxisId="p" dataKey="nm" name="Net margin" stroke={C.c3} strokeWidth={2} dot={{ r: 3 }} />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
                <Legend items={[{ label: 'Revenue', color: 'var(--chart-1)' }, { label: 'Net income', color: 'var(--chart-2)' }, { label: 'Gross margin (right)', color: 'var(--chart-4)' }, { label: 'Net margin (right)', color: 'var(--chart-3)' }]} />
              </Card>
              <Card title="Profit vs cash" subtitle="Accounting profit is not cash: compare net income with operating and free cash flow">
                <div className="chart">
                  <ResponsiveContainer>
                    <ComposedChart data={chart} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid {...gridProps} />
                      <XAxis dataKey="period" {...axisProps} />
                      <YAxis {...axisProps} width={52} tickFormatter={(v) => fmtCompact(v)} />
                      <Tooltip cursor={{ fill: 'var(--bg-hover)' }} content={<ChartTooltip format={(v) => fmtNum(v, 1)} />} />
                      <Bar dataKey="net_income" name="Net income" fill={C.c2} radius={[4, 4, 0, 0]} maxBarSize={28} />
                      <Bar dataKey="ocf" name="Operating cash flow" fill={C.c1} radius={[4, 4, 0, 0]} maxBarSize={28} />
                      <Bar dataKey="fcf" name="Free cash flow" fill={C.c3} radius={[4, 4, 0, 0]} maxBarSize={28} />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
                <Legend items={[{ label: 'Net income', color: 'var(--chart-2)' }, { label: 'Operating cash flow', color: 'var(--chart-1)' }, { label: 'Free cash flow', color: 'var(--chart-3)' }]} />
              </Card>
            </div>
            <Card title="Derived metrics" flush>
              <div className="table-wrap" style={{ border: 0, borderRadius: 0 }}>
                <table className="data">
                  <thead><tr><th>Metric</th>{r.periods.map((p) => <th key={p} className="r">{p}</th>)}</tr></thead>
                  <tbody>{METRIC_LABELS.map(([k, label, kind]) => (
                    <tr key={k}><td>{label}</td>{r.metrics[k].map((v, i) => <td key={i} className="r">{fmtMetric(v, kind)}</td>)}</tr>
                  ))}</tbody>
                </table>
              </div>
            </Card>
            {r.quality_flags.length > 0 && <Warnings items={r.quality_flags} />}
            <Callout tone="info">{r.notes.join(' ')}</Callout>
          </div>
        )}

        {tab === 'horizontal' && r && <StatementTable r={r} mode="horizontal" />}
        {tab === 'vertical' && r && <StatementTable r={r} mode="vertical" />}

        {tab === 'checks' && r && (
          <Card title="Reconciliation checks" subtitle="Tolerance: 0.5% of the larger value (minimum 1 unit) to allow for rounding in published statements">
            {r.checks.length === 0 ? <p className="muted">Map lines to standard items (Edit data tab) to enable checks.</p> : (
              <div className="table-wrap">
                <table className="data">
                  <thead><tr><th>Check</th><th>Period</th><th>Result</th><th className="r">Difference</th><th>Detail</th></tr></thead>
                  <tbody>{r.checks.map((c, i) => (
                    <tr key={i} style={c.status === 'fail' ? { background: 'var(--negative-soft)' } : undefined}>
                      <td>{c.name}</td><td>{c.period}</td>
                      <td>{c.status === 'pass' ? <span className="row pos"><CheckCircle2 size={15} />Pass</span> : c.status === 'fail' ? <span className="row neg"><XCircle size={15} />Fail</span> : <span className="row faint"><CircleSlash size={15} />Not enough data</span>}</td>
                      <td className="r">{fmtNum(c.difference, 2)}</td><td className="faint" style={{ whiteSpace: 'normal', minWidth: 220 }}>{c.detail}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
            <div className="mt"><Callout tone="info">A failed check shows an inconsistency to investigate — missing lines, rounding, extraction errors or reclassifications. It does not by itself indicate misstatement.</Callout></div>
          </Card>
        )}

        {tab === 'edit' && <Editor data={data} setData={(d) => setData(d)} items={items.data?.items ?? {}} />}
      </div>

      <div className="mt">
        <LearnBox title="Horizontal, vertical and common-size analysis">
          <div className="stack" style={{ fontSize: 13 }}>
            <p><b>Horizontal analysis</b> compares each line with the previous period: change = current − prior; % change = change / |prior|. It reveals growth and trends.</p>
            <p><b>Vertical analysis</b> expresses each line as a % of a base in the same period — revenue for the income statement and cash flow, total assets for the balance sheet — so companies of different size can be compared.</p>
            <p><b>Free cash flow</b> = operating cash flow − capital expenditure. Profit includes non-cash items and accruals; cash flow shows what was actually collected and paid.</p>
          </div>
        </LearnBox>
      </div>
    </div>
  );
}

function StatementTable({ r, mode }: { r: Report; mode: 'horizontal' | 'vertical' }) {
  return (
    <div className="stack">
      {STMTS.map((s) => {
        const lines = r.lines.filter((l) => l.statement === s.value);
        if (!lines.length) return null;
        return (
          <Card key={s.value} title={s.label} subtitle={mode === 'vertical' ? (s.value === 'balance' ? 'Each line as % of total assets' : 'Each line as % of revenue') : 'Values and change vs the previous period (Δ% = change / |prior|; colour-neutral because a rise is good for revenue but bad for costs)'} flush>
            <div className="table-wrap" style={{ border: 0, borderRadius: 0 }}>
              <table className="data">
                <thead>
                  <tr><th>Line item</th>{r.periods.map((p, i) => mode === 'horizontal'
                    ? [<th key={p} className="r">{p}</th>, i > 0 ? <th key={`${p}-d`} className="r">Δ%</th> : null]
                    : <th key={p} className="r">{p}</th>)}{mode === 'horizontal' && <th className="r">CAGR</th>}</tr>
                </thead>
                <tbody>
                  {lines.map((l, idx) => (
                    <tr key={idx} title={l.source ?? undefined}>
                      <td>{l.label}{l.key && <span className="faint" style={{ fontSize: 11 }}> · {l.key}</span>}</td>
                      {r.periods.map((p, i) => {
                        if (mode === 'vertical') return <td key={p} className="r">{fmtPctPoints(l.common_size[i], 1)}</td>;
                        const c = l.changes[i];
                        return [
                          <td key={p} className="r">{fmtNum(l.values[i], 1)}</td>,
                          i > 0 ? <td key={`${p}-d`} className={`r ${c && isNum(c.pct) ? 'muted' : 'faint'}`} title={c?.note ?? undefined}>{c ? (isNum(c.pct) ? fmtPctPoints(c.pct, 1) : 'n/a') : '—'}</td> : null,
                        ];
                      })}
                      {mode === 'horizontal' && <td className="r">{fmtPct(l.cagr, 1)}</td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        );
      })}
      {mode === 'vertical' && !r.lines.some((l) => l.key === 'revenue' || l.key === 'total_assets') && <Callout tone="warn">Map a line to "revenue" or "total_assets" in Edit data to compute common-size percentages.</Callout>}
    </div>
  );
}

function Editor({ data, setData, items }: { data: Data; setData: (d: Data) => void; items: Record<string, { statement: Stmt; label: string }> }) {
  const n = data.periods.length;
  const updLine = (i: number, p: Partial<Line>) => setData({ ...data, lines: data.lines.map((l, j) => (j === i ? { ...l, ...p } : l)) });
  const usedKeys = new Set(data.lines.map((l) => l.key).filter(Boolean));
  return (
    <div className="stack">
      <Card title="Periods" subtitle="Oldest first">
        <div className="row">
          {data.periods.map((p, i) => (
            <input key={i} className="input compact" style={{ width: 110 }} aria-label={`Period ${i + 1}`} value={p}
              onChange={(e) => setData({ ...data, periods: data.periods.map((x, j) => (j === i ? e.target.value : x)) })} />
          ))}
          <button className="btn sm" disabled={n >= 20} onClick={() => setData({ periods: [...data.periods, `P${n + 1}`], lines: data.lines.map((l) => ({ ...l, values: [...l.values, null] })) })}><Plus size={14} />Period</button>
          <button className="btn sm" disabled={n <= 1} onClick={() => setData({ periods: data.periods.slice(0, -1), lines: data.lines.map((l) => ({ ...l, values: l.values.slice(0, -1) })) })}>Remove last</button>
        </div>
      </Card>
      {STMTS.map((s) => (
        <Card key={s.value} title={s.label} flush actions={<button className="btn sm" onClick={() => setData({ ...data, lines: [...data.lines, { label: 'New line', statement: s.value, key: null, values: Array(n).fill(null) }] })}><Plus size={14} />Line</button>}>
          <div className="table-wrap" style={{ border: 0, borderRadius: 0 }}>
            <table className="data">
              <thead><tr><th>Line item</th><th>Standard item (enables checks)</th>{data.periods.map((p) => <th key={p} className="r">{p}</th>)}<th /></tr></thead>
              <tbody>
                {data.lines.map((l, i) => l.statement !== s.value ? null : (
                  <tr key={i}>
                    <td style={{ minWidth: 200 }}><input className="input compact" aria-label="Line item" value={l.label} onChange={(e) => updLine(i, { label: e.target.value })} /></td>
                    <td style={{ minWidth: 190 }}>
                      <select className="input compact" aria-label="Standard item" value={l.key ?? ''} onChange={(e) => updLine(i, { key: e.target.value || null })}>
                        <option value="">— none —</option>
                        {Object.entries(items).filter(([, v]) => v.statement === s.value).map(([k, v]) => (
                          <option key={k} value={k} disabled={usedKeys.has(k) && l.key !== k}>{v.label}</option>
                        ))}
                      </select>
                    </td>
                    {l.values.map((v, j) => (
                      <td key={j} style={{ minWidth: 100 }}><NumberField compact ariaLabel={`${l.label} ${data.periods[j]}`} value={v} onChange={(nv) => updLine(i, { values: l.values.map((x, k) => (k === j ? nv : x)) })} /></td>
                    ))}
                    <td><button className="btn icon sm ghost" aria-label={`Remove ${l.label}`} onClick={() => setData({ ...data, lines: data.lines.filter((_, k) => k !== i) })}><Trash2 size={14} /></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ))}
      <Callout tone="info">Blank cells are treated as missing, never as zero. Enter CapEx as a negative (cash-flow convention) or positive amount — it is always treated as an outflow.</Callout>
    </div>
  );
}
