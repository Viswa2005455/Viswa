import { Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { C, ChartTooltip, Legend, axisProps, gridProps } from '../components/charts';
import { SaveLoad } from '../components/SaveLoad';
import { Badge, Callout, Card, ErrorBox, Formula, Kpi, NumberField, PageHeader, Skeleton, Tabs } from '../components/ui';
import { api } from '../lib/api';
import { fmtCompact, fmtNum, fmtPct, isNum } from '../lib/format';
import { useSettings } from '../lib/settings';
import { loadRaw, save } from '../lib/storage';
import { useAsync, useDebounced } from '../lib/useApi';

type Tab = 'variances' | 'cvp' | 'absorption' | 'lf';
interface Variance { name: string; value: number; nature: 'F' | 'A' | '—'; formula: string; working: string; level: number }
interface VarRes { variances: Variance[]; reconciles?: boolean; note?: string; absorption_rate?: number }
type N = number | null;

const EXAMPLE = {
  materials: [{ name: 'Material A', std_qty: 60, std_price: 2, actual_qty: 70, actual_price: 2.2 }, { name: 'Material B', std_qty: 40, std_price: 5, actual_qty: 35, actual_price: 4.8 }] as { name: string; std_qty: N; std_price: N; actual_qty: N; actual_price: N }[],
  labour: { std_hours: 1000 as N, std_rate: 10 as N, hours_paid: 1100 as N, hours_worked: 1050 as N, actual_rate: 11 as N },
  voh: { std_hours: 1000 as N, std_rate: 4 as N, hours_worked: 1050 as N, actual_cost: 4500 as N },
  foh: { budgeted_cost: 10000 as N, actual_cost: 10500 as N, budgeted_hours: 1000 as N, std_hours: 1100 as N, hours_worked: 1050 as N },
  sales: { budget_qty: 1000 as N, budget_price: 50 as N, actual_qty: 1100 as N, actual_price: 48 as N, std_margin: 20 as N },
  cvp: { products: [{ name: 'Product X', price: 50, variable_cost: 30, mix: 1 }] as { name: string; price: N; variable_cost: N; mix: N }[], fixed_costs: 40000 as N, target_profit: 30000 as N, tax_rate: 0.25 as N, expected_units: 3000 as N },
  absorption: { price: 20 as N, variable_prod_cost: 8 as N, variable_selling_cost: 1 as N, fixed_prod_overhead: 30000 as N, normal_units: 10000 as N, produced_units: 12000 as N, sold_units: 10000 as N, opening_units: 0 as N, fixed_selling_admin: 5000 as N },
  lf: { products: [{ name: 'A', contribution_per_unit: 10, resource_per_unit: 2, max_demand: 100 }, { name: 'B', contribution_per_unit: 12, resource_per_unit: 4, max_demand: 100 }, { name: 'C', contribution_per_unit: 6, resource_per_unit: 1, max_demand: 100 }] as { name: string; contribution_per_unit: N; resource_per_unit: N; max_demand: N }[], resource_available: 400 as N, resource_name: 'machine hours', fixed_costs: 1000 as N },
};
type Model = typeof EXAMPLE;
const allNum = (o: Record<string, unknown>) => Object.values(o).every((v) => typeof v === 'string' || isNum(v));

export function Costing() {
  const [tab, setTab] = useState<Tab>(() => loadRaw('fis.costing.tab', 'variances'));
  const [state, setState] = useState<{ m: Model; example: boolean }>(() => loadRaw('fis.costing', { m: EXAMPLE, example: true }));
  const m = state.m;
  const set = (p: Partial<Model>) => { const s = { m: { ...m, ...p }, example: false }; setState(s); save('fis.costing', s); };
  return (
    <div className="page">
      <PageHeader title="Cost & Management Accounting" badge={state.example ? <Badge tone="sample">Example figures</Badge> : <Badge tone="accent">Your figures</Badge>}
        subtitle="Standard-cost variances, cost-volume-profit, absorption vs marginal costing reconciliation and limiting-factor product mix — each with formulas and workings (CIMA / ICAI / IMA terminology)."
        actions={<>
          <SaveLoad kind="costing" label="costing workings" getData={() => m} onLoad={(d: Model) => { const s = { m: { ...EXAMPLE, ...d }, example: false }; setState(s); save('fis.costing', s); }} />
          <button className="btn" onClick={() => { setState({ m: EXAMPLE, example: true }); save('fis.costing', { m: EXAMPLE, example: true }); }}>Example</button>
        </>} />
      <Tabs label="Section" value={tab} onChange={(t) => { setTab(t); save('fis.costing.tab', t); }} options={[
        { value: 'variances', label: 'Standard-cost variances' }, { value: 'cvp', label: 'CVP & break-even' },
        { value: 'absorption', label: 'Absorption vs marginal' }, { value: 'lf', label: 'Limiting factor' }]} />
      <div className="mt">
        {tab === 'variances' && <Variances m={m} set={set} />}
        {tab === 'cvp' && <CVP m={m} set={set} />}
        {tab === 'absorption' && <Absorption m={m} set={set} />}
        {tab === 'lf' && <LimitingFactor m={m} set={set} />}
      </div>
    </div>
  );
}

function VarianceTable({ res }: { res: VarRes }) {
  const { settings } = useSettings();
  return (
    <>
      <div className="table-wrap" tabIndex={0}>
        <table className="data">
          <thead><tr><th>Variance</th><th className="r">Amount</th><th>F / A</th><th>Formula · working</th></tr></thead>
          <tbody>{res.variances.map((v) => (
            <tr key={v.name} style={v.level === 0 ? { fontWeight: 650 } : undefined}>
              <td style={{ paddingLeft: 12 + v.level * 14 }}>{v.name}</td>
              <td className="r">{fmtNum(Math.abs(v.value), 2, settings.currency)}</td>
              <td><Badge tone={v.nature === 'F' ? 'accent' : v.nature === 'A' ? 'neg' : undefined}>{v.nature === 'F' ? 'Favourable' : v.nature === 'A' ? 'Adverse' : 'Nil'}</Badge></td>
              <td className="mono" style={{ fontSize: 11.5, whiteSpace: 'normal', minWidth: 220 }}>{v.formula}<br /><span className="faint">{v.working}</span></td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      {res.reconciles !== undefined && <div className="faint mt-sm" style={{ fontSize: 12 }}>{res.reconciles ? '✓ Sub-variances reconcile to the total.' : '⚠ Sub-variances do not reconcile — check the inputs.'}{res.note ? ` ${res.note}` : ''}</div>}
    </>
  );
}

function useCalc<T>(path: string, body: unknown) {
  const req = useDebounced(body, 300);
  return useAsync(() => api.post<T>(path, req), [JSON.stringify(req)], !!req);
}

function Fields<T extends Record<string, N | string>>({ obj, labels, onChange, cols = 3 }: { obj: T; labels: Record<string, string>; onChange: (o: T) => void; cols?: number }) {
  return (
    <div className={`grid cols-${cols}`} style={{ gap: 10 }}>
      {Object.entries(labels).map(([k, label]) => (
        <NumberField key={k} label={label} value={obj[k] as N} percent={k === 'tax_rate'} onChange={(v) => onChange({ ...obj, [k]: v })} />
      ))}
    </div>
  );
}

function Result<T>({ r, children }: { r: { data: T | null; error: string | null; loading: boolean }; children: (d: T) => React.ReactNode }) {
  if (r.error) return <div className="mt-sm"><ErrorBox error={r.error} /></div>;
  if (!r.data) return r.loading ? <Skeleton h={80} /> : <p className="faint mt-sm">Fill in every field to calculate.</p>;
  return <div className="mt-sm">{children(r.data)}</div>;
}

function Variances({ m, set }: { m: Model; set: (p: Partial<Model>) => void }) {
  const matOk = m.materials.length > 0 && m.materials.every((x) => allNum(x));
  const mat = useCalc<VarRes>('/api/costing/materials', matOk ? { materials: m.materials } : null);
  const lab = useCalc<VarRes>('/api/costing/labour', allNum(m.labour) ? m.labour : null);
  const voh = useCalc<VarRes>('/api/costing/variable-overhead', allNum(m.voh) ? m.voh : null);
  const foh = useCalc<VarRes>('/api/costing/fixed-overhead', allNum(m.foh) ? m.foh : null);
  const sal = useCalc<VarRes>('/api/costing/sales', allNum(m.sales) ? m.sales : null);
  const updMat = (i: number, p: Partial<Model['materials'][number]>) => set({ materials: m.materials.map((x, j) => (j === i ? { ...x, ...p } : x)) });
  return (
    <div className="stack">
      <Card title="Direct materials" subtitle="SQ = standard quantity allowed for actual output. With two or more materials, mix and yield variances are shown."
        actions={<button className="btn sm" onClick={() => set({ materials: [...m.materials, { name: `Material ${m.materials.length + 1}`, std_qty: null, std_price: null, actual_qty: null, actual_price: null }] })}><Plus size={14} />Material</button>}>
        <div className="table-wrap" tabIndex={0}>
          <table className="data">
            <thead><tr><th>Material</th><th>Std qty (SQ)</th><th>Std price (SP)</th><th>Actual qty (AQ)</th><th>Actual price (AP)</th><th /></tr></thead>
            <tbody>{m.materials.map((x, i) => (
              <tr key={i}>
                <td><input className="input compact" aria-label="Material name" value={x.name} onChange={(e) => updMat(i, { name: e.target.value })} /></td>
                {(['std_qty', 'std_price', 'actual_qty', 'actual_price'] as const).map((k) => <td key={k} style={{ minWidth: 110 }}><NumberField compact ariaLabel={`${x.name} ${k}`} value={x[k]} onChange={(v) => updMat(i, { [k]: v })} /></td>)}
                <td><button className="btn sm ghost" aria-label="Remove material" disabled={m.materials.length <= 1} onClick={() => set({ materials: m.materials.filter((_, j) => j !== i) })}><Trash2 size={14} /></button></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <Result r={mat}>{(d) => <VarianceTable res={d} />}</Result>
      </Card>
      <div className="grid cols-2">
        <Card title="Direct labour" subtitle="Idle time is separated from efficiency">
          <Fields obj={m.labour} onChange={(labour) => set({ labour })} labels={{ std_hours: 'Std hours for actual output (SH)', std_rate: 'Std rate (SR)', hours_paid: 'Hours paid', hours_worked: 'Hours worked', actual_rate: 'Actual rate (AR)' }} cols={2} />
          <Result r={lab}>{(d) => <VarianceTable res={d} />}</Result>
        </Card>
        <Card title="Variable production overhead" subtitle="Absorbed on labour or machine hours">
          <Fields obj={m.voh} onChange={(voh) => set({ voh })} labels={{ std_hours: 'Std hours (SH)', std_rate: 'Std rate per hour', hours_worked: 'Actual hours', actual_cost: 'Actual variable overhead' }} cols={2} />
          <Result r={voh}>{(d) => <VarianceTable res={d} />}</Result>
        </Card>
        <Card title="Fixed production overhead" subtitle="Absorption costing: expenditure, volume (capacity + efficiency)">
          <Fields obj={m.foh} onChange={(foh) => set({ foh })} labels={{ budgeted_cost: 'Budgeted fixed overhead', actual_cost: 'Actual fixed overhead', budgeted_hours: 'Budgeted hours', std_hours: 'Std hours for actual output', hours_worked: 'Actual hours' }} cols={2} />
          <Result r={foh}>{(d) => <>{isNum(d.absorption_rate) && <div className="faint" style={{ fontSize: 12.5 }}>Absorption rate: {fmtNum(d.absorption_rate, 4)} per hour</div>}<VarianceTable res={d} /></>}</Result>
        </Card>
        <Card title="Sales" subtitle="Margin can be standard contribution (marginal costing) or standard profit (absorption costing)">
          <Fields obj={m.sales} onChange={(sales) => set({ sales })} labels={{ budget_qty: 'Budgeted units', budget_price: 'Budgeted price', actual_qty: 'Actual units', actual_price: 'Actual price', std_margin: 'Std contribution per unit' }} cols={2} />
          <Result r={sal}>{(d) => <VarianceTable res={d} />}</Result>
        </Card>
      </div>
    </div>
  );
}

interface CVPRes {
  contribution_per_unit: number; pv_ratio: number; breakeven_units: number; breakeven_sales: number; steps: string[];
  products: { name: string; contribution_per_unit: number; pv_ratio: number | null; breakeven_units: number; breakeven_sales: number }[];
  target?: { units: number; sales: number; pre_tax_profit: number };
  at_expected?: { profit: number; margin_of_safety_units: number; margin_of_safety_pct: number | null; operating_leverage: number | null; sales: number };
  chart: { units: number; sales: number; total_cost: number; fixed: number }[];
}

function CVP({ m, set }: { m: Model; set: (p: Partial<Model>) => void }) {
  const { settings } = useSettings();
  const c = m.cvp;
  const ok = c.products.every((p) => isNum(p.price) && isNum(p.variable_cost) && isNum(p.mix)) && isNum(c.fixed_costs);
  const r = useCalc<CVPRes>('/api/costing/cvp', ok ? { ...c, tax_rate: c.tax_rate ?? 0 } : null);
  const upd = (p: Partial<Model['cvp']>) => set({ cvp: { ...c, ...p } });
  const updP = (i: number, p: Partial<Model['cvp']['products'][number]>) => upd({ products: c.products.map((x, j) => (j === i ? { ...x, ...p } : x)) });
  const money = (v: number | null | undefined) => fmtNum(v, 0, settings.currency);
  return (
    <div className="grid cols-3">
      <div className="stack">
        <Card title="Products and sales mix" actions={<button className="btn sm" onClick={() => upd({ products: [...c.products, { name: `Product ${c.products.length + 1}`, price: null, variable_cost: null, mix: 1 }] })}><Plus size={14} />Product</button>}>
          <div className="stack" style={{ gap: 10 }}>
            {c.products.map((p, i) => (
              <div key={i} className="stack" style={{ gap: 6, borderBottom: '1px solid var(--border)', paddingBottom: 8 }}>
                <div className="row"><input className="input compact" aria-label="Product name" value={p.name} onChange={(e) => updP(i, { name: e.target.value })} />
                  <button className="btn sm ghost" aria-label="Remove product" disabled={c.products.length <= 1} onClick={() => upd({ products: c.products.filter((_, j) => j !== i) })}><Trash2 size={14} /></button></div>
                <div className="grid cols-3" style={{ gap: 6 }}>
                  <NumberField label="Price" value={p.price} onChange={(v) => updP(i, { price: v })} />
                  <NumberField label="Variable cost" value={p.variable_cost} onChange={(v) => updP(i, { variable_cost: v })} />
                  <NumberField label="Mix (units)" value={p.mix} onChange={(v) => updP(i, { mix: v })} />
                </div>
              </div>
            ))}
          </div>
        </Card>
        <Card title="Costs and targets">
          <div className="stack" style={{ gap: 10 }}>
            <NumberField label="Fixed costs" value={c.fixed_costs} onChange={(v) => upd({ fixed_costs: v })} />
            <NumberField label="Target profit after tax (optional)" value={c.target_profit} onChange={(v) => upd({ target_profit: v })} />
            <NumberField label="Tax rate" percent value={c.tax_rate} onChange={(v) => upd({ tax_rate: v })} />
            <NumberField label="Expected sales units (optional)" value={c.expected_units} onChange={(v) => upd({ expected_units: v })} hint="For margin of safety and operating leverage" />
          </div>
        </Card>
      </div>
      <div className="span-2 stack">
        <Result r={r}>{(d) => (
          <div className="stack">
            <div className="grid cols-4">
              <Kpi label="Contribution / unit" value={money(d.contribution_per_unit)} delta={`P/V ratio ${fmtPct(d.pv_ratio, 1)}`} />
              <Kpi label="Break-even" value={`${fmtNum(d.breakeven_units, 0)} units`} delta={money(d.breakeven_sales)} />
              <Kpi label="Units for target profit" value={d.target ? fmtNum(d.target.units, 0) : '—'} delta={d.target ? money(d.target.sales) : undefined} />
              <Kpi label="Margin of safety" value={d.at_expected && isNum(d.at_expected.margin_of_safety_pct) ? fmtPct(d.at_expected.margin_of_safety_pct, 1) : '—'}
                delta={d.at_expected && isNum(d.at_expected.operating_leverage) ? `DOL ${fmtNum(d.at_expected.operating_leverage, 2)}×` : undefined} />
            </div>
            <Card title="Break-even chart" subtitle="Sales revenue vs total cost; they cross at break-even">
              <div style={{ height: 260 }}>
                <ResponsiveContainer>
                  <LineChart data={d.chart} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                    <CartesianGrid {...gridProps} />
                    <XAxis dataKey="units" type="number" domain={['dataMin', 'dataMax']} {...axisProps} tickFormatter={(x) => fmtCompact(x, settings.currency)} />
                    <YAxis {...axisProps} width={56} tickFormatter={(y) => fmtCompact(y, settings.currency)} />
                    <Tooltip content={<ChartTooltip format={(y) => money(y)} labelFormat={(l) => `${fmtNum(Number(l), 0)} units`} />} />
                    <ReferenceLine x={d.breakeven_units} stroke={C.neg} strokeDasharray="4 4" label={{ value: 'BEP', fill: 'var(--text-muted)', fontSize: 11, position: 'insideTopRight' }} />
                    <Line dataKey="sales" name="Sales" stroke={C.c1} strokeWidth={2} dot={false} isAnimationActive={false} />
                    <Line dataKey="total_cost" name="Total cost" stroke={C.c4} strokeWidth={2} dot={false} isAnimationActive={false} />
                    <Line dataKey="fixed" name="Fixed cost" stroke={C.c3} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <Legend items={[{ label: 'Sales', color: C.c1 }, { label: 'Total cost', color: C.c4 }, { label: 'Fixed cost', color: C.c3, dashed: true }]} />
            </Card>
            {d.products.length > 1 && (
              <Card title="Break-even by product (at the stated mix)">
                <div className="table-wrap" tabIndex={0}><table className="data">
                  <thead><tr><th>Product</th><th className="r">Contribution / unit</th><th className="r">P/V</th><th className="r">BEP units</th><th className="r">BEP sales</th></tr></thead>
                  <tbody>{d.products.map((p) => <tr key={p.name}><td>{p.name}</td><td className="r">{money(p.contribution_per_unit)}</td><td className="r">{fmtPct(p.pv_ratio, 1)}</td><td className="r">{fmtNum(p.breakeven_units, 0)}</td><td className="r">{money(p.breakeven_sales)}</td></tr>)}</tbody>
                </table></div>
              </Card>
            )}
            <Formula>{d.steps.join('\n')}</Formula>
          </div>
        )}</Result>
      </div>
    </div>
  );
}

interface AbsRes {
  oar: number; closing_units: number; full_cost_per_unit: number; note: string;
  marginal: Record<string, number>; absorption: Record<string, number>;
  reconciliation: { difference: number; explained: number; working: string; reconciles: boolean };
}

function Absorption({ m, set }: { m: Model; set: (p: Partial<Model>) => void }) {
  const { settings } = useSettings();
  const r = useCalc<AbsRes>('/api/costing/absorption-vs-marginal', allNum(m.absorption) ? m.absorption : null);
  const money = (v: number | null | undefined) => fmtNum(v, 0, settings.currency);
  const row = (label: string, v: number | undefined, neg = false, bold = false) => (
    <div className="metric-row" style={bold ? { fontWeight: 650 } : undefined}><span>{label}</span><span className="v">{isNum(v) ? (neg ? `(${money(v)})` : money(v)) : '—'}</span></div>
  );
  return (
    <div className="grid cols-3">
      <Card title="Inputs (per period)">
        <Fields obj={m.absorption} onChange={(absorption) => set({ absorption })} cols={1} labels={{ price: 'Selling price / unit', variable_prod_cost: 'Variable production cost / unit',
          variable_selling_cost: 'Variable selling cost / unit', fixed_prod_overhead: 'Budgeted fixed production overhead', normal_units: 'Normal (budgeted) production units',
          produced_units: 'Actual production units', sold_units: 'Units sold', opening_units: 'Opening inventory units', fixed_selling_admin: 'Fixed selling & admin' }} />
      </Card>
      <div className="span-2 stack">
        <Result r={r}>{(d) => (
          <div className="stack">
            <div className="grid cols-2">
              <Card title="Marginal (variable) costing" subtitle="Fixed production overhead is a period cost">
                {row('Sales', d.marginal.sales)}{row('Variable cost of sales', d.marginal.variable_cost_of_sales, true)}{row('Variable selling cost', d.marginal.variable_selling, true)}
                {row('Contribution', d.marginal.contribution, false, true)}{row('Fixed production overhead', d.marginal.fixed_production, true)}{row('Fixed selling & admin', d.marginal.fixed_selling_admin, true)}
                {row('Profit', d.marginal.profit, false, true)}
              </Card>
              <Card title="Absorption (full) costing" subtitle={`OAR ${fmtNum(d.oar, 4)} per unit · full cost ${fmtNum(d.full_cost_per_unit, 2)}`}>
                {row('Sales', d.absorption.sales)}{row('Cost of sales at full cost', d.absorption.cost_of_sales, true)}
                {row(d.absorption.over_under_absorption >= 0 ? 'Over-absorbed overhead' : 'Under-absorbed overhead', Math.abs(d.absorption.over_under_absorption), d.absorption.over_under_absorption < 0)}
                {row('Gross profit', d.absorption.gross_profit, false, true)}{row('Variable selling cost', d.absorption.variable_selling, true)}{row('Fixed selling & admin', d.absorption.fixed_selling_admin, true)}
                {row('Profit', d.absorption.profit, false, true)}
              </Card>
            </div>
            <Callout tone={d.reconciliation.reconciles ? 'success' : 'warn'} title="Profit reconciliation">
              Absorption profit − marginal profit = {money(d.reconciliation.difference)}. Explained by fixed overhead in the inventory change: {d.reconciliation.working}.
              <div className="faint mt-sm" style={{ fontSize: 12.5 }}>{d.note} Closing inventory: {fmtNum(d.closing_units, 0)} units.</div>
            </Callout>
          </div>
        )}</Result>
      </div>
    </div>
  );
}

interface LFRes {
  plan: { name: string; rank: number; contribution_per_unit: number; resource_per_unit: number; contribution_per_resource: number; max_demand: number; units: number; resource_used: number; contribution: number; reason: string }[];
  total_contribution: number; profit: number | null; resource_needed_for_full_demand: number; is_binding: boolean; resource_unused: number; resource_name: string; note: string;
}

function LimitingFactor({ m, set }: { m: Model; set: (p: Partial<Model>) => void }) {
  const { settings } = useSettings();
  const l = m.lf;
  const ok = l.products.every((p) => isNum(p.contribution_per_unit) && isNum(p.resource_per_unit) && isNum(p.max_demand)) && isNum(l.resource_available);
  const r = useCalc<LFRes>('/api/costing/limiting-factor', ok ? l : null);
  const upd = (p: Partial<Model['lf']>) => set({ lf: { ...l, ...p } });
  const updP = (i: number, p: Partial<Model['lf']['products'][number]>) => upd({ products: l.products.map((x, j) => (j === i ? { ...x, ...p } : x)) });
  const money = (v: number | null | undefined) => fmtNum(v, 0, settings.currency);
  return (
    <div className="stack">
      <Card title="Products and the scarce resource" actions={<button className="btn sm" onClick={() => upd({ products: [...l.products, { name: `Product ${l.products.length + 1}`, contribution_per_unit: null, resource_per_unit: null, max_demand: null }] })}><Plus size={14} />Product</button>}>
        <div className="grid cols-3" style={{ gap: 10, marginBottom: 12 }}>
          <div className="field"><label className="field-label">Scarce resource</label><input className="input" value={l.resource_name} onChange={(e) => upd({ resource_name: e.target.value })} /></div>
          <NumberField label="Available" value={l.resource_available} onChange={(v) => upd({ resource_available: v })} />
          <NumberField label="Fixed costs (optional)" value={l.fixed_costs} onChange={(v) => upd({ fixed_costs: v })} />
        </div>
        <div className="table-wrap" tabIndex={0}><table className="data">
          <thead><tr><th>Product</th><th>Contribution / unit</th><th>{l.resource_name} / unit</th><th>Max demand (units)</th><th /></tr></thead>
          <tbody>{l.products.map((p, i) => (
            <tr key={i}>
              <td><input className="input compact" aria-label="Product name" value={p.name} onChange={(e) => updP(i, { name: e.target.value })} /></td>
              {(['contribution_per_unit', 'resource_per_unit', 'max_demand'] as const).map((k) => <td key={k}><NumberField compact ariaLabel={`${p.name} ${k}`} value={p[k]} onChange={(v) => updP(i, { [k]: v })} /></td>)}
              <td><button className="btn sm ghost" aria-label="Remove product" disabled={l.products.length <= 1} onClick={() => upd({ products: l.products.filter((_, j) => j !== i) })}><Trash2 size={14} /></button></td>
            </tr>
          ))}</tbody>
        </table></div>
      </Card>
      <Result r={r}>{(d) => (
        <Card title="Optimal production plan" subtitle={d.is_binding ? `${d.resource_name} is the limiting factor: ${fmtNum(d.resource_needed_for_full_demand, 0)} needed for full demand, ${fmtNum(l.resource_available, 0)} available` : `${d.resource_name} is not binding: full demand can be met`}>
          <div className="grid cols-3" style={{ marginBottom: 12 }}>
            <Kpi label="Total contribution" value={money(d.total_contribution)} />
            <Kpi label="Profit" value={isNum(d.profit) ? money(d.profit) : '—'} />
            <Kpi label={`Unused ${d.resource_name}`} value={fmtNum(d.resource_unused, 1)} />
          </div>
          <div className="table-wrap" tabIndex={0}><table className="data">
            <thead><tr><th>Rank</th><th>Product</th><th className="r">Contribution per {d.resource_name.replace(/s$/, '')}</th><th className="r">Units</th><th className="r">{d.resource_name} used</th><th className="r">Contribution</th><th>Why</th></tr></thead>
            <tbody>{d.plan.map((p) => <tr key={p.name}><td>{p.rank}</td><td>{p.name}</td><td className="r">{fmtNum(p.contribution_per_resource, 2)}</td><td className="r">{fmtNum(p.units, 2)}</td><td className="r">{fmtNum(p.resource_used, 2)}</td><td className="r">{money(p.contribution)}</td><td className="faint">{p.reason}</td></tr>)}</tbody>
          </table></div>
          <p className="faint mt-sm" style={{ fontSize: 12.5 }}>{d.note}</p>
        </Card>
      )}</Result>
    </div>
  );
}
