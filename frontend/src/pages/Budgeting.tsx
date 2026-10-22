import { ArrowRight, ChevronDown, ChevronRight, Copy, Download, Plus, RotateCcw, Trash2 } from 'lucide-react';
import { Fragment, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { C, ChartTooltip, Legend, axisProps, gridProps } from '../components/charts';
import { SaveLoad } from '../components/SaveLoad';
import { Badge, Callout, Card, ErrorBox, Field, Kpi, LearnBox, NumberField, PageHeader, Stable, Warnings } from '../components/ui';
import { api } from '../lib/api';
import { downloadFile, fmtCompact, fmtMoney, fmtNum, fmtPctPoints, isNum, toCSV } from '../lib/format';
import { useSettings } from '../lib/settings';
import { loadRaw, save } from '../lib/storage';
import { useToast } from '../lib/toast';
import { useAsync, useDebounced } from '../lib/useApi';

type Kind = 'revenue' | 'expense' | 'capex';
type Method = 'monthly' | 'annual' | 'incremental' | 'driver';
type Status = 'Draft' | 'Submitted' | 'Approved' | 'Rejected';
interface BLine {
  name: string; kind: Kind; method: Method; department: string; product: string | null;
  monthly: (number | null)[]; annual: number | null; prior_actual: number | null; change_pct: number | null;
  quantity: (number | null)[]; rate: number | null; weights: (number | null)[] | null; justification: string;
}
interface Version { id: string; name: string; status: Status; created: string; start_month: number; start_year: number; zero_based: boolean; lines: BLine[] }
interface Store { versions: Version[]; active: string; isExample: boolean }
interface LineOut { name: string; kind: Kind; department: string; product: string | null; method: Method; monthly: number[]; quarterly: number[]; annual: number; explanation: string }
interface BudgetRes {
  months: string[]; lines: LineOut[]; totals_monthly: Record<string, number[]>; totals_annual: Record<string, number>;
  by_department: Record<string, Record<Kind, number>>; by_product: Record<string, number>; warnings: string[];
}

const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const uid = () => Math.random().toString(36).slice(2, 9);
const blank = (p: Partial<BLine>): BLine => ({
  name: 'New line', kind: 'expense', method: 'annual', department: 'General', product: null, monthly: Array(12).fill(0), annual: 0,
  prior_actual: null, change_pct: null, quantity: Array(12).fill(0), rate: null, weights: null, justification: '', ...p,
});
const SEASONAL = [7, 7, 8, 8, 8, 9, 9, 10, 11, 9, 7, 7];

const EXAMPLE_LINES: BLine[] = [
  blank({ name: 'Product A sales', kind: 'revenue', method: 'driver', department: 'Sales', product: 'Product A', quantity: [400, 420, 430, 450, 470, 500, 560, 600, 580, 480, 450, 460], rate: 1250 }),
  blank({ name: 'Product B sales', kind: 'revenue', method: 'annual', department: 'Sales', product: 'Product B', annual: 2400000, weights: SEASONAL }),
  blank({ name: 'Service contracts', kind: 'revenue', method: 'incremental', department: 'Services', product: 'Services', prior_actual: 1500000, change_pct: 8 }),
  blank({ name: 'Raw materials', kind: 'expense', method: 'driver', department: 'Operations', quantity: [400, 420, 430, 450, 470, 500, 560, 600, 580, 480, 450, 460], rate: 540, justification: 'BOM cost per Product A unit' }),
  blank({ name: 'Salaries', kind: 'expense', method: 'incremental', department: 'Operations', prior_actual: 3600000, change_pct: 7, justification: '7% merit increase, no new hires' }),
  blank({ name: 'Marketing', kind: 'expense', method: 'monthly', department: 'Sales', monthly: [60000, 60000, 80000, 80000, 90000, 120000, 150000, 150000, 90000, 60000, 60000, 60000], justification: 'Festive-season campaign Sep–Nov' }),
  blank({ name: 'Rent & utilities', kind: 'expense', method: 'annual', department: 'Admin', annual: 720000, justification: 'Lease agreement' }),
  blank({ name: 'Delivery van', kind: 'capex', method: 'monthly', department: 'Operations', monthly: [0, 0, 0, 0, 0, 1200000, 0, 0, 0, 0, 0, 0], justification: 'Replace 2016 van' }),
];
const EXAMPLE: Store = {
  versions: [{ id: 'v1', name: 'FY27 Budget v1', status: 'Draft', created: '2026-10-15', start_month: 4, start_year: 2026, zero_based: false, lines: EXAMPLE_LINES }],
  active: 'v1', isExample: true,
};

function toPayload(v: Version) {
  return { start_month: v.start_month, start_year: v.start_year, zero_based: v.zero_based, lines: v.lines.map((l) => ({ ...l, product: l.product || null, justification: l.justification || null })) };
}
function incomplete(l: BLine): boolean {
  if (!l.name.trim()) return true;
  if (l.method === 'monthly') return l.monthly.some((x) => x === null);
  if (l.method === 'annual') return l.annual === null || (l.weights !== null && l.weights.some((x) => x === null));
  if (l.method === 'incremental') return l.prior_actual === null || l.change_pct === null;
  return l.rate === null || l.quantity.some((x) => x === null);
}

export function Budgeting() {
  const { settings } = useSettings();
  const cur = settings.currency;
  const toast = useToast();
  const nav = useNavigate();
  const [store, setStoreState] = useState<Store>(() => loadRaw('fis.budgets', EXAMPLE));
  const setStore = (s: Store) => { setStoreState(s); save('fis.budgets', s); };
  const v = store.versions.find((x) => x.id === store.active) ?? store.versions[0];
  const updV = (p: Partial<Version>) => setStore({ ...store, isExample: false, versions: store.versions.map((x) => (x.id === v.id ? { ...x, ...p } : x)) });
  const updLine = (i: number, p: Partial<BLine>) => updV({ lines: v.lines.map((l, j) => (j === i ? { ...l, ...p } : l)) });
  const [open, setOpen] = useState<number | null>(null);
  const [compareId, setCompareId] = useState<string>('');

  const bad = v.lines.filter(incomplete).map((l) => l.name);
  const body = useMemo(() => (bad.length || !v.lines.length ? null : toPayload(v)), [v, bad.length]);
  const req = useDebounced(body, 150);
  const res = useAsync((signal) => api.post<BudgetRes>('/api/finance/budget', req, { signal }), [JSON.stringify(req)], !!req);
  const r = res.data;
  const outByIndex = r && r.lines.length === v.lines.length ? r.lines : null;
  const locked = v.status === 'Approved';

  const other = store.versions.find((x) => x.id === compareId && x.id !== v.id);
  const cmp = useAsync(async () => {
    if (!other || !r) return null;
    const b = await api.post<BudgetRes>('/api/finance/budget', toPayload(other));
    return api.post<{ lines: { name: string; kind: string; a: number | null; b: number | null; change: number | null; change_pct: number | null; status: string }[] }>(
      '/api/finance/budget/compare', { a: b.lines.map((l) => ({ name: l.name, kind: l.kind, annual: l.annual })), b: r.lines.map((l) => ({ name: l.name, kind: l.kind, annual: l.annual })) });
  }, [compareId, JSON.stringify(r?.totals_annual), JSON.stringify(other?.lines)], !!other && !!r);

  const newVersion = () => {
    const id = uid();
    const n = store.versions.length + 1;
    setStore({ ...store, isExample: false, active: id, versions: [...store.versions, { ...v, id, name: `${v.name.replace(/ v\d+$/, '')} v${n}`, status: 'Draft', created: new Date().toISOString().slice(0, 10), lines: v.lines.map((l) => ({ ...l })) }] });
    setCompareId(v.id);
    toast('New draft version created from the current one');
  };

  const sendToVariance = () => {
    if (!r) return;
    const lines = r.lines.filter((l) => l.kind !== 'capex').map((l) => ({ name: l.name, kind: l.kind, budget: l.annual, actual: null, source: `Budgeting › ${v.name} (${v.status})` }));
    save('fis.variance.import', { lines, note: `Budget imported from "${v.name}" (${v.status}). Enter the actual amounts for the same period.` });
    nav('/variance');
  };

  const exportCsv = () => {
    if (!r) return;
    const rows: unknown[][] = [['Budget', v.name, v.status, store.isExample ? 'EXAMPLE DATA' : ''], ['Fiscal year start', `${MONTH_NAMES[v.start_month - 1]} ${v.start_year}`], [],
      ['Line', 'Type', 'Department', 'Product', 'Method', ...r.months, 'Q1', 'Q2', 'Q3', 'Q4', 'Annual', 'Basis', 'Justification'],
      ...r.lines.map((l, i) => [l.name, l.kind, l.department, l.product ?? '', l.method, ...l.monthly, ...l.quarterly, l.annual, l.explanation, v.lines[i]?.justification ?? '']), [],
      ...(['revenue', 'expense', 'capex', 'operating_result'] as const).map((k) => [`Total ${k.replace('_', ' ')}`, '', '', '', '', ...r.totals_monthly[k], '', '', '', '', r.totals_annual[k]]),
      ['Generated', new Date().toISOString()]];
    downloadFile(`${v.name.replace(/\W+/g, '-')}.csv`, toCSV(rows));
  };

  const chart = r ? r.months.map((m, i) => ({ month: m, revenue: r.totals_monthly.revenue[i], expense: r.totals_monthly.expense[i], result: r.totals_monthly.operating_result[i] })) : [];

  return (
    <div className="page">
      <PageHeader title="Budgeting" badge={store.isExample ? <Badge tone="sample">Example budget</Badge> : undefined}
        subtitle="Build monthly budgets line by line using direct entry, annual phasing, incremental or driver-based (zero-based) methods. Save versions, compare them and send the budget to Variance Analysis."
        actions={<>
          <SaveLoad kind="budget" label="budget" getData={() => store} onLoad={(d: Store) => { setStore({ ...d, isExample: false }); setCompareId(''); }} />
          <button className="btn" onClick={() => { setStore(EXAMPLE); setCompareId(''); }}><RotateCcw size={15} />Example</button>
          <button className="btn" onClick={exportCsv} disabled={!r}><Download size={15} />Export CSV</button>
          <button className="btn primary" onClick={sendToVariance} disabled={!r}>Compare with actuals <ArrowRight size={15} /></button>
        </>} />

      <div className="grid cols-4">
        <Card className="span-2 wide-sm" title="Version">
          <div className="form-grid">
            <Field label="Active version">
              <select className="input" value={v.id} onChange={(e) => setStore({ ...store, active: e.target.value })}>
                {store.versions.map((x) => <option key={x.id} value={x.id}>{x.name} · {x.status}</option>)}
              </select>
            </Field>
            <Field label="Name"><input className="input" value={v.name} maxLength={60} onChange={(e) => updV({ name: e.target.value })} /></Field>
            <Field label="Approval status">
              <select className="input" value={v.status} onChange={(e) => updV({ status: e.target.value as Status })}>
                {(['Draft', 'Submitted', 'Approved', 'Rejected'] as Status[]).map((s) => <option key={s}>{s}</option>)}
              </select>
            </Field>
          </div>
          <div className="row mt-sm">
            <button className="btn sm" onClick={newVersion}><Copy size={14} />New version from this</button>
            <button className="btn sm danger" disabled={store.versions.length <= 1} onClick={() => {
              if (!confirm(`Delete version "${v.name}"?`)) return;
              const rest = store.versions.filter((x) => x.id !== v.id);
              setStore({ ...store, versions: rest, active: rest[0].id });
            }}><Trash2 size={14} />Delete version</button>
          </div>
          <p className="faint mt-sm" style={{ fontSize: 12 }}>Approval status is a label in this version — user sign-off and audit trail arrive with accounts (Phase 7). Approved versions are locked for editing.</p>
        </Card>
        <Card title="Fiscal year">
          <div className="stack" style={{ gap: 10 }}>
            <Field label="Starts in">
              <select className="input" value={v.start_month} disabled={locked} onChange={(e) => updV({ start_month: Number(e.target.value) })}>
                {MONTH_NAMES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
              </select>
            </Field>
            <NumberField label="Year" value={v.start_year} onChange={(y) => y && updV({ start_year: Math.round(y) })} min={1990} max={2100} />
          </div>
        </Card>
        <Card title="Approach">
          <label className="row" style={{ fontSize: 13 }}>
            <input type="checkbox" checked={v.zero_based} disabled={locked} onChange={(e) => updV({ zero_based: e.target.checked })} />
            Zero-based budgeting
          </label>
          <p className="faint mt-sm" style={{ fontSize: 12.5 }}>When on, every line needs a justification and cost lines should be built from drivers rather than last year's figures.</p>
        </Card>
      </div>

      {r && (
        <div className="grid cols-4 mt">
          <Kpi label="Budgeted revenue" value={fmtMoney(r.totals_annual.revenue, cur)} />
          <Kpi label="Budgeted operating expenses" value={fmtMoney(r.totals_annual.expense, cur)} />
          <Kpi label="Operating result" value={fmtMoney(r.totals_annual.operating_result, cur)} deltaTone={r.totals_annual.operating_result >= 0 ? 'pos' : 'neg'}
            delta={r.totals_annual.revenue ? `${fmtPctPoints((r.totals_annual.operating_result / r.totals_annual.revenue) * 100, 1)} margin` : undefined} />
          <Kpi label="Capital expenditure" value={fmtMoney(r.totals_annual.capex, cur)} />
        </div>
      )}
      {res.error && <div className="mt"><ErrorBox error={res.error} /></div>}
      {bad.length > 0 && <div className="mt"><Callout tone="warn">Complete the inputs for: {bad.slice(0, 6).join(', ')}. Blank values are not treated as zero.</Callout></div>}
      {r && r.warnings.length > 0 && <div className="mt"><Warnings items={r.warnings} /></div>}
      {locked && <div className="mt"><Callout tone="info">This version is approved and locked. Create a new version to make changes.</Callout></div>}

      <Card title="Budget lines" subtitle="Click a line to edit its method and inputs" flush className="mt">
        <div className="table-wrap" tabIndex={0} style={{ border: 0, borderRadius: 0 }}>
          <table className="data">
            <thead><tr><th /><th>Line</th><th>Type</th><th>Department</th><th>Product</th><th>Method</th><th className="r">Q1</th><th className="r">Q2</th><th className="r">Q3</th><th className="r">Q4</th><th className="r">Annual</th><th /></tr></thead>
            <tbody>
              {v.lines.map((l, i) => {
                const o = outByIndex?.[i];
                return (
                  <Fragment key={i}>
                    <tr style={{ cursor: 'pointer' }} onClick={() => setOpen(open === i ? null : i)}>
                      <td>{open === i ? <ChevronDown size={15} /> : <ChevronRight size={15} />}</td>
                      <td style={{ fontWeight: 550 }}>{l.name}{incomplete(l) && <Badge tone="warn">incomplete</Badge>}</td>
                      <td><Badge tone={l.kind === 'revenue' ? 'accent' : l.kind === 'capex' ? 'info' : undefined}>{l.kind}</Badge></td>
                      <td>{l.department}</td><td>{l.product ?? ''}</td><td>{l.method}</td>
                      {[0, 1, 2, 3].map((q) => <td key={q} className="r">{o ? fmtNum(o.quarterly[q], 0) : '—'}</td>)}
                      <td className="r" style={{ fontWeight: 650 }}>{o ? fmtNum(o.annual, 0) : '—'}</td>
                      <td><button className="btn icon sm ghost" aria-label={`Remove ${l.name}`} disabled={locked} onClick={(e) => { e.stopPropagation(); updV({ lines: v.lines.filter((_, j) => j !== i) }); setOpen(null); }}><Trash2 size={14} /></button></td>
                    </tr>
                    {open === i && (
                      <tr><td colSpan={12} style={{ whiteSpace: 'normal', background: 'var(--bg-sunken)' }}>
                        <LineEditor line={l} months={r?.months} locked={locked} onChange={(p) => updLine(i, p)} explanation={o?.explanation} />
                      </td></tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
            {r && (
              <tfoot>
                {(['revenue', 'expense', 'capex', 'operating_result'] as const).map((k) => (
                  <tr key={k}><td /><td colSpan={5}>{k === 'operating_result' ? 'Operating result (revenue − expenses)' : `Total ${k}`}</td>
                    {[0, 1, 2, 3].map((q) => <td key={q} className="r">{fmtNum(r.totals_monthly[k].slice(q * 3, q * 3 + 3).reduce((a, b) => a + b, 0), 0)}</td>)}
                    <td className="r">{fmtNum(r.totals_annual[k], 0)}</td><td /></tr>
                ))}
              </tfoot>
            )}
          </table>
        </div>
        <div style={{ padding: '12px 18px' }} className="row">
          {(['revenue', 'expense', 'capex'] as Kind[]).map((k) => (
            <button key={k} className="btn sm" disabled={locked} onClick={() => { updV({ lines: [...v.lines, blank({ kind: k, name: `New ${k} line` })] }); setOpen(v.lines.length); }}><Plus size={14} />{k}</button>
          ))}
        </div>
      </Card>

      <Stable deps={[r, cur]} render={() => r && (
        <div className="grid cols-3 mt">
          <Card className="span-2" title="Monthly profile" subtitle={`${r.months[0]} to ${r.months[11]}`}>
            <div className="chart">
              <ResponsiveContainer>
                <ComposedChart data={chart} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid {...gridProps} />
                  <XAxis dataKey="month" {...axisProps} />
                  <YAxis {...axisProps} width={56} tickFormatter={(x) => fmtCompact(x, cur)} />
                  <Tooltip cursor={{ fill: 'var(--bg-hover)' }} content={<ChartTooltip format={(x) => fmtMoney(x, cur)} />} />
                  <Bar dataKey="revenue" name="Revenue" fill={C.c1} radius={[4, 4, 0, 0]} maxBarSize={18} />
                  <Bar dataKey="expense" name="Expenses" fill={C.c4} radius={[4, 4, 0, 0]} maxBarSize={18} />
                  <Line dataKey="result" name="Operating result" stroke={C.c3} strokeWidth={2.2} dot={{ r: 2.5 }} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <Legend items={[{ label: 'Revenue', color: 'var(--chart-1)' }, { label: 'Expenses', color: 'var(--chart-4)' }, { label: 'Operating result', color: 'var(--chart-3)' }]} />
          </Card>
          <Card title="By department & product">
            <div className="table-wrap" tabIndex={0}>
              <table className="data">
                <thead><tr><th>Department</th><th className="r">Revenue</th><th className="r">Expense</th><th className="r">CapEx</th></tr></thead>
                <tbody>{Object.entries(r.by_department).map(([d, x]) => (
                  <tr key={d}><td>{d}</td><td className="r">{fmtCompact(x.revenue, cur)}</td><td className="r">{fmtCompact(x.expense, cur)}</td><td className="r">{fmtCompact(x.capex, cur)}</td></tr>
                ))}</tbody>
              </table>
            </div>
            {Object.keys(r.by_product).length > 0 && (
              <div className="mt">{Object.entries(r.by_product).map(([p, x]) => (
                <div key={p} className="metric-row"><span>{p}</span><span className="v">{fmtMoney(x, cur)} · {fmtPctPoints((x / r.totals_annual.revenue) * 100, 1)}</span></div>
              ))}</div>
            )}
          </Card>
        </div>
      )} />

      <div className="grid cols-2 mt" style={{ alignItems: 'start' }}>
        <Card title="Compare versions" subtitle={`Annual totals: selected version → ${v.name}`}>
          <Field label="Compare against">
            <select className="input" value={compareId} onChange={(e) => setCompareId(e.target.value)}>
              <option value="">— choose a version —</option>
              {store.versions.filter((x) => x.id !== v.id).map((x) => <option key={x.id} value={x.id}>{x.name} · {x.status}</option>)}
            </select>
          </Field>
          {store.versions.length < 2 && <p className="faint mt-sm" style={{ fontSize: 12.5 }}>Create a second version with "New version from this" to compare.</p>}
          {cmp.error && <ErrorBox error={cmp.error} />}
          {other && cmp.data && (
            <div className="table-wrap mt" tabIndex={0}>
              <table className="data">
                <thead><tr><th>Line</th><th className="r">{other.name}</th><th className="r">{v.name}</th><th className="r">Change</th><th className="r">%</th></tr></thead>
                <tbody>{cmp.data.lines.filter((d) => d.status !== 'unchanged').map((d) => (
                  <tr key={d.kind + d.name}><td>{d.name} {d.status !== 'changed' && <Badge tone={d.status === 'added' ? 'accent' : 'neg'}>{d.status}</Badge>}</td>
                    <td className="r">{fmtNum(d.a, 0)}</td><td className="r">{fmtNum(d.b, 0)}</td><td className="r">{fmtNum(d.change, 0)}</td><td className="r">{fmtPctPoints(d.change_pct, 1)}</td></tr>
                ))}</tbody>
              </table>
              {cmp.data.lines.every((d) => d.status === 'unchanged') && <p className="faint" style={{ padding: 10 }}>No differences.</p>}
            </div>
          )}
        </Card>
        <FlexibleBudget />
      </div>

      <div className="mt">
        <LearnBox title="Budgeting methods">
          <div className="stack" style={{ fontSize: 13 }}>
            <p><b>Incremental budgeting</b> starts from last year's actual and adjusts by a percentage — quick, but it can carry forward inefficiencies.</p>
            <p><b>Zero-based budgeting (ZBB)</b> starts every line from zero and builds it from drivers (quantity × rate) with a written justification — slower, but it challenges every cost.</p>
            <p><b>Flexible budgets</b> restate costs at the actual level of activity (fixed + variable per unit × units) so that variance analysis compares like with like.</p>
            <p><b>Phasing</b> spreads an annual figure over months; seasonal businesses should phase by expected activity, not evenly.</p>
          </div>
        </LearnBox>
      </div>
    </div>
  );
}

function LineEditor({ line, months, locked, onChange, explanation }: { line: BLine; months?: string[]; locked: boolean; onChange: (p: Partial<BLine>) => void; explanation?: string }) {
  const labels = months ?? Array.from({ length: 12 }, (_, i) => `M${i + 1}`);
  const grid = (values: (number | null)[], key: 'monthly' | 'quantity' | 'weights', suffix?: string) => (
    <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(92px, 1fr))', gap: 6 }}>
      {values.map((x, i) => (
        <div key={i}><div className="faint" style={{ fontSize: 11 }}>{labels[i]}</div>
          <NumberField compact ariaLabel={`${key} ${labels[i]}`} suffix={suffix} value={x} min={0} required onChange={(n) => onChange({ [key]: values.map((y, j) => (j === i ? n : y)) } as Partial<BLine>)} />
        </div>
      ))}
    </div>
  );
  return (
    <fieldset disabled={locked} style={{ border: 0, padding: 6, margin: 0 }} className="stack">
      <div className="form-grid">
        <Field label="Name"><input className="input" value={line.name} onChange={(e) => onChange({ name: e.target.value })} /></Field>
        <Field label="Type">
          <select className="input" value={line.kind} onChange={(e) => onChange({ kind: e.target.value as Kind })}>
            <option value="revenue">Revenue</option><option value="expense">Expense</option><option value="capex">Capital expenditure</option>
          </select>
        </Field>
        <Field label="Department / cost centre"><input className="input" value={line.department} onChange={(e) => onChange({ department: e.target.value })} /></Field>
        <Field label="Product (optional)"><input className="input" value={line.product ?? ''} onChange={(e) => onChange({ product: e.target.value || null })} /></Field>
        <Field label="Method">
          <select className="input" value={line.method} onChange={(e) => onChange({ method: e.target.value as Method })}>
            <option value="annual">Annual amount, phased</option><option value="monthly">Enter each month</option>
            <option value="incremental">Incremental (prior year ± %)</option><option value="driver">Driver-based (quantity × rate)</option>
          </select>
        </Field>
      </div>
      {line.method === 'annual' && (
        <div className="stack" style={{ gap: 8 }}>
          <div className="form-grid">
            <NumberField label="Annual amount" value={line.annual} onChange={(n) => onChange({ annual: n })} required />
            <Field label="Phasing">
              <select className="input" value={line.weights ? 'custom' : 'even'} onChange={(e) => onChange({ weights: e.target.value === 'even' ? null : e.target.value === 'seasonal' ? [...SEASONAL] : Array(12).fill(1) })}>
                <option value="even">Even (1/12 each month)</option><option value="custom">Custom weights</option><option value="seasonal">Seasonal preset (Q3-peak)</option>
              </select>
            </Field>
          </div>
          {line.weights && <><div className="field-label">Relative weights (any scale)</div>{grid(line.weights, 'weights')}</>}
        </div>
      )}
      {line.method === 'incremental' && (
        <div className="form-grid">
          <NumberField label="Prior-year actual" value={line.prior_actual} onChange={(n) => onChange({ prior_actual: n })} required />
          <NumberField label="Change" suffix="%" value={line.change_pct} onChange={(n) => onChange({ change_pct: n })} required />
          <Field label="Phasing">
            <select className="input" value={line.weights ? 'seasonal' : 'even'} onChange={(e) => onChange({ weights: e.target.value === 'even' ? null : [...SEASONAL] })}>
              <option value="even">Even</option><option value="seasonal">Seasonal preset</option>
            </select>
          </Field>
        </div>
      )}
      {line.method === 'monthly' && grid(line.monthly, 'monthly')}
      {line.method === 'driver' && (
        <div className="stack" style={{ gap: 8 }}>
          <NumberField label="Rate per unit" value={line.rate} onChange={(n) => onChange({ rate: n })} required />
          <div className="field-label">Quantity per month</div>{grid(line.quantity, 'quantity')}
        </div>
      )}
      <Field label="Justification / assumptions" hint="Required for every line in zero-based budgeting">
        <input className="input" value={line.justification} maxLength={500} onChange={(e) => onChange({ justification: e.target.value })} />
      </Field>
      {explanation && <div className="faint" style={{ fontSize: 12.5 }}>Basis: {explanation}</div>}
    </fieldset>
  );
}

function FlexibleBudget() {
  const { settings } = useSettings();
  const [fixed, setFixed] = useState<number | null>(500000);
  const [variable, setVariable] = useState<number | null>(540);
  const [levels, setLevels] = useState('4000, 5000, 6000, 7000');
  const lv = levels.split(/[\s,;]+/).filter(Boolean).map(Number);
  const ok = isNum(fixed) && isNum(variable) && lv.length > 0 && lv.every((x) => Number.isFinite(x) && x >= 0);
  const req = useDebounced(ok ? { fixed_cost: fixed, variable_cost_per_unit: variable, activity_levels: lv } : null, 150);
  const res = useAsync((signal) => api.post<{ levels: { activity: number; fixed: number; variable: number; total: number; cost_per_unit: number | null }[] }>('/api/finance/budget/flexible', req, { signal }), [JSON.stringify(req)], !!req);
  return (
    <Card title="Flexible budget" subtitle="Cost at different activity levels (example inputs)">
      <div className="form-grid">
        <NumberField label="Fixed costs" value={fixed} onChange={setFixed} min={0} required />
        <NumberField label="Variable cost per unit" value={variable} onChange={setVariable} min={0} required />
        <Field label="Activity levels (units)"><input className="input" value={levels} onChange={(e) => setLevels(e.target.value)} /></Field>
      </div>
      {!ok && <div className="mt-sm"><Callout tone="warn">Enter fixed cost, variable cost and at least one non-negative activity level.</Callout></div>}
      {res.error && <ErrorBox error={res.error} />}
      {res.data && (
        <div className="table-wrap mt" tabIndex={0}>
          <table className="data">
            <thead><tr><th className="r">Units</th><th className="r">Fixed</th><th className="r">Variable</th><th className="r">Total cost</th><th className="r">Cost per unit</th></tr></thead>
            <tbody>{res.data.levels.map((x) => (
              <tr key={x.activity}><td className="r">{fmtNum(x.activity, 0)}</td><td className="r">{fmtNum(x.fixed, 0)}</td><td className="r">{fmtNum(x.variable, 0)}</td>
                <td className="r">{fmtMoney(x.total, settings.currency)}</td><td className="r">{isNum(x.cost_per_unit) ? fmtNum(x.cost_per_unit, 2) : 'n/a'}</td></tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
