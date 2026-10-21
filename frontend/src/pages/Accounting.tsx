import { Download, Plus, Trash2 } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { SaveLoad } from '../components/SaveLoad';
import { Badge, Callout, Card, ErrorBox, Field, Formula, Kpi, NumberField, PageHeader, Skeleton, Tabs } from '../components/ui';
import { api } from '../lib/api';
import { downloadFile, fmtNum, fmtPct, isNum, toCSV } from '../lib/format';
import { useSettings } from '../lib/settings';
import { loadRaw, save } from '../lib/storage';
import { useAsync, useDebounced } from '../lib/useApi';

type Tab = 'bond' | 'lease' | 'dep' | 'eps' | 'dt' | 'mat';
type N = number | null;
interface JE { when: string; memo: string; lines: { account: string; debit: number | null; credit: number | null }[] }

const EXAMPLE = {
  bond: { face: 100000 as N, coupon_rate: 0.08 as N, market_rate: 0.1 as N, years: 5 as N, payments_per_year: 2, perspective: 'issuer' },
  lease: { payment: 10000 as N, periods: 5 as N, annual_rate: 0.06 as N, periods_per_year: 1, timing: 'advance', initial_direct_costs: 0 as N, incentives: 0 as N, prepaid: 0 as N, classification: 'finance' },
  dep: { cost: 10000 as N, salvage: 1000 as N, life: 5 as N, method: 'ddb', units: '' },
  eps: { net_income: 1000000 as N, preferred_dividends: 100000 as N, weighted_shares: 500000 as N, average_price: 25 as N,
    securities: [{ kind: 'options', name: 'Employee options', shares: 50000 as N, exercise_price: 20 as N, preferred_dividends: null as N, interest_after_tax: null as N },
      { kind: 'convertible_debt', name: 'Convertible bonds', shares: 100000 as N, exercise_price: null as N, preferred_dividends: null as N, interest_after_tax: 120000 as N },
      { kind: 'convertible_preferred', name: 'Convertible preferred', shares: 50000 as N, exercise_price: null as N, preferred_dividends: 100000 as N, interest_after_tax: null as N }] },
  dt: { tax_rate: 0.25 as N, current_tax: 50000 as N, opening_net_dtl: 1000 as N,
    items: [{ name: 'Property, plant & equipment', kind: 'asset', carrying_amount: 100000 as N, tax_base: 70000 as N },
      { name: 'Warranty provision', kind: 'liability', carrying_amount: 20000 as N, tax_base: 0 as N }] },
  mat: { values: { profit_before_tax: 1000000 as N, revenue: 20000000 as N, total_assets: 15000000 as N, equity: 8000000 as N, expenses: null as N },
    selected: 'profit_before_tax', pct: 0.05 as N, performance_pct: 0.75 as N, trivial_pct: 0.05 as N },
};
type Model = typeof EXAMPLE;
const filled = (o: Record<string, unknown>, keys: string[]) => keys.every((k) => isNum(o[k]));

export function Accounting() {
  const [tab, setTab] = useState<Tab>(() => loadRaw('fis.accounting.tab', 'bond'));
  const [state, setState] = useState<{ m: Model; example: boolean }>(() => loadRaw('fis.accounting', { m: EXAMPLE, example: true }));
  const m = state.m;
  const set = (p: Partial<Model>) => { const s = { m: { ...m, ...p }, example: false }; setState(s); save('fis.accounting', s); };
  return (
    <div className="page">
      <PageHeader title="Accounting & Audit" badge={state.example ? <Badge tone="sample">Example figures</Badge> : <Badge tone="accent">Your figures</Badge>}
        subtitle="Workpaper-ready schedules with journal entries: bonds (effective interest), leases (ASC 842 / IFRS 16), depreciation, EPS (ASC 260 / IAS 33), deferred tax (ASC 740 / IAS 12) and audit materiality (AU-C 320 / ISA 320)."
        actions={<>
          <SaveLoad kind="accounting" label="accounting schedules" getData={() => m} onLoad={(d: Model) => { const s = { m: { ...EXAMPLE, ...d }, example: false }; setState(s); save('fis.accounting', s); }} />
          <button className="btn" onClick={() => { setState({ m: EXAMPLE, example: true }); save('fis.accounting', { m: EXAMPLE, example: true }); }}>Example</button>
        </>} />
      <Tabs label="Schedule" value={tab} onChange={(t) => { setTab(t); save('fis.accounting.tab', t); }} options={[
        { value: 'bond', label: 'Bonds' }, { value: 'lease', label: 'Leases' }, { value: 'dep', label: 'Depreciation' },
        { value: 'eps', label: 'EPS' }, { value: 'dt', label: 'Deferred tax' }, { value: 'mat', label: 'Materiality' }]} />
      <div className="mt">
        {tab === 'bond' && <Bond m={m} set={set} />}
        {tab === 'lease' && <Lease m={m} set={set} />}
        {tab === 'dep' && <Depreciation m={m} set={set} />}
        {tab === 'eps' && <EPS m={m} set={set} />}
        {tab === 'dt' && <DeferredTax m={m} set={set} />}
        {tab === 'mat' && <Materiality m={m} set={set} />}
      </div>
      <p className="faint mt" style={{ fontSize: 12 }}>Schedules apply the standards' mechanics to the inputs given. Classification, measurement judgements and disclosure remain the preparer's responsibility; verify against the authoritative literature.</p>
    </div>
  );
}

function useCalc<T>(path: string, body: unknown) {
  const req = useDebounced(body, 300);
  return useAsync(() => api.post<T>(path, req), [JSON.stringify(req)], !!req);
}

function Layout({ inputs, children, r }: { inputs: ReactNode; children: (d: never) => ReactNode; r: { data: unknown; error: string | null; loading: boolean } }) {
  return (
    <div className="grid cols-3">
      <Card title="Inputs">{inputs}</Card>
      <div className="span-2 stack">
        {r.error ? <ErrorBox error={r.error} /> : r.data ? children(r.data as never) : r.loading ? <Skeleton h={120} /> : <p className="faint">Fill in every required field to build the schedule.</p>}
      </div>
    </div>
  );
}

function Schedule({ title, cols, rows, file, sub }: { title: string; cols: [string, string, ('n' | 'i')?][]; rows: Record<string, unknown>[]; file: string; sub?: string }) {
  const get = (r: Record<string, unknown>, k: string) => k.split('.').reduce<unknown>((o, p) => (o as Record<string, unknown> | undefined)?.[p], r) as number | null;
  const exportCsv = () => downloadFile(file, toCSV([cols.map((c) => c[1]), ...rows.map((r) => cols.map(([k]) => get(r, k) ?? ''))]));
  return (
    <Card title={title} subtitle={sub} flush actions={<button className="btn sm" onClick={exportCsv}><Download size={14} />CSV</button>}>
      <div className="table-wrap" style={{ border: 0, borderRadius: 0, maxHeight: 420 }}>
        <table className="data">
          <thead><tr>{cols.map(([k, l]) => <th key={k} className={k === cols[0][0] ? '' : 'r'}>{l}</th>)}</tr></thead>
          <tbody>{rows.map((r, i) => <tr key={i}>{cols.map(([k, , t], j) => <td key={k} className={j ? 'r' : ''}>{t === 'i' ? String(get(r, k) ?? '') : isNum(get(r, k)) ? fmtNum(get(r, k), 2) : '—'}</td>)}</tr>)}</tbody>
        </table>
      </div>
    </Card>
  );
}

function Journal({ jes }: { jes: JE[] }) {
  return (
    <Card title="Journal entries" subtitle="Debits first; amounts rounded to two decimals">
      <div className="table-wrap"><table className="data">
        <thead><tr><th>Date</th><th>Account</th><th className="r">Debit</th><th className="r">Credit</th></tr></thead>
        <tbody>{jes.flatMap((j, i) => [
          ...j.lines.map((l, k) => (
            <tr key={`${i}-${k}`}><td className="faint">{k === 0 ? j.when : ''}</td><td style={{ paddingLeft: l.credit ? 32 : 12 }}>{l.account}</td>
              <td className="r">{isNum(l.debit) ? fmtNum(l.debit, 2) : ''}</td><td className="r">{isNum(l.credit) ? fmtNum(l.credit, 2) : ''}</td></tr>)),
          <tr key={`${i}-memo`}><td /><td colSpan={3} className="faint" style={{ fontSize: 12, fontStyle: 'italic' }}>{j.memo}</td></tr>,
        ])}</tbody>
      </table></div>
    </Card>
  );
}

function Select({ label, value, options, onChange }: { label: string; value: string | number; options: [string | number, string][]; onChange: (v: string) => void }) {
  return <Field label={label}><select className="input" value={value} onChange={(e) => onChange(e.target.value)}>{options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>;
}

interface BondRes { issue_price: number; kind: string; premium_or_discount: number; periods: number; period_rate: number; total_interest: number; schedule: Record<string, number>[]; journal_entries: JE[]; standard: string; steps: string[] }
function Bond({ m, set }: { m: Model; set: (p: Partial<Model>) => void }) {
  const b = m.bond;
  const u = (p: Partial<Model['bond']>) => set({ bond: { ...b, ...p } });
  const r = useCalc<BondRes>('/api/accounting/bond', filled(b, ['face', 'coupon_rate', 'market_rate', 'years']) ? b : null);
  return (
    <Layout r={r} inputs={<div className="stack" style={{ gap: 10 }}>
      <NumberField label="Face value" value={b.face} onChange={(v) => u({ face: v })} />
      <NumberField label="Coupon rate (annual)" percent value={b.coupon_rate} onChange={(v) => u({ coupon_rate: v })} />
      <NumberField label="Market (effective) rate at issue" percent value={b.market_rate} onChange={(v) => u({ market_rate: v })} />
      <NumberField label="Term (years)" value={b.years} onChange={(v) => u({ years: v })} />
      <Select label="Coupons per year" value={b.payments_per_year} options={[[1, 'Annual'], [2, 'Semi-annual'], [4, 'Quarterly'], [12, 'Monthly']]} onChange={(v) => u({ payments_per_year: Number(v) })} />
      <Select label="Perspective" value={b.perspective} options={[['issuer', 'Issuer (bonds payable)'], ['investor', 'Investor (amortised cost)']]} onChange={(v) => u({ perspective: v })} />
    </div>}>
      {(d: BondRes) => <>
        <div className="grid cols-4">
          <Kpi label="Issue price" value={fmtNum(d.issue_price, 2)} />
          <Kpi label={d.kind === 'par' ? 'At par' : `${d.kind[0].toUpperCase()}${d.kind.slice(1)}`} value={fmtNum(d.premium_or_discount, 2)} />
          <Kpi label="Rate per period" value={fmtPct(d.period_rate, 3)} />
          <Kpi label="Total interest" value={fmtNum(d.total_interest, 2)} />
        </div>
        <Formula>{d.steps.join('\n')}</Formula>
        <Schedule title="Amortisation schedule" file="bond-amortisation.csv" sub={d.standard} rows={d.schedule}
          cols={[['period', 'Period', 'i'], ['opening', 'Opening carrying amount'], ['cash', 'Cash coupon'], ['interest', 'Interest (effective)'], ['amortisation', 'Amortisation'], ['closing', 'Closing carrying amount']]} />
        <Journal jes={d.journal_entries} />
      </>}
    </Layout>
  );
}

interface LeaseRes { initial_liability: number; initial_rou_asset: number; period_rate: number; total_cash: number; straight_line_cost: number | null; schedule: Record<string, unknown>[]; journal_entries: JE[]; standard: string; steps: string[]; classification: string }
function Lease({ m, set }: { m: Model; set: (p: Partial<Model>) => void }) {
  const l = m.lease;
  const u = (p: Partial<Model['lease']>) => set({ lease: { ...l, ...p } });
  const r = useCalc<LeaseRes>('/api/accounting/lease', filled(l, ['payment', 'periods', 'annual_rate']) ? { ...l, initial_direct_costs: l.initial_direct_costs ?? 0, incentives: l.incentives ?? 0, prepaid: l.prepaid ?? 0 } : null);
  return (
    <Layout r={r} inputs={<div className="stack" style={{ gap: 10 }}>
      <Select label="Classification" value={l.classification} options={[['finance', 'Finance lease (ASC 842) / IFRS 16 lessee'], ['operating', 'Operating lease (ASC 842 only)']]} onChange={(v) => u({ classification: v })} />
      <NumberField label="Lease payment" value={l.payment} onChange={(v) => u({ payment: v })} />
      <NumberField label="Number of payments" value={l.periods} onChange={(v) => u({ periods: v })} />
      <Select label="Payment frequency" value={l.periods_per_year} options={[[1, 'Annual'], [2, 'Semi-annual'], [4, 'Quarterly'], [12, 'Monthly']]} onChange={(v) => u({ periods_per_year: Number(v) })} />
      <Select label="Timing" value={l.timing} options={[['advance', 'In advance (start of period)'], ['arrears', 'In arrears (end of period)']]} onChange={(v) => u({ timing: v })} />
      <NumberField label="Discount rate (annual: implicit or incremental borrowing rate)" percent value={l.annual_rate} onChange={(v) => u({ annual_rate: v })} />
      <NumberField label="Initial direct costs" value={l.initial_direct_costs} onChange={(v) => u({ initial_direct_costs: v })} />
      <NumberField label="Lease incentives received" value={l.incentives} onChange={(v) => u({ incentives: v })} />
      <NumberField label="Prepaid lease payments" value={l.prepaid} onChange={(v) => u({ prepaid: v })} />
    </div>}>
      {(d: LeaseRes) => <>
        <div className="grid cols-4">
          <Kpi label="Lease liability" value={fmtNum(d.initial_liability, 2)} />
          <Kpi label="Right-of-use asset" value={fmtNum(d.initial_rou_asset, 2)} />
          <Kpi label="Total cash payments" value={fmtNum(d.total_cash, 2)} />
          <Kpi label={d.straight_line_cost ? 'Straight-line lease cost' : 'Rate per period'} value={d.straight_line_cost ? fmtNum(d.straight_line_cost, 2) : fmtPct(d.period_rate, 3)} />
        </div>
        <Callout tone="info">{d.standard}</Callout>
        <Formula>{d.steps.join('\n')}</Formula>
        <Schedule title="Lease schedule" file="lease-schedule.csv" rows={d.schedule}
          cols={[['period', 'Period', 'i'], ['opening_liability', 'Opening liability'], ['payment', 'Payment'], ['interest', 'Interest / accretion'], ['closing_liability', 'Closing liability'],
            ['rou_amortisation', 'ROU amortisation'], ['closing_rou', 'Closing ROU'], ['expense.total', 'P&L expense']]} />
        <Journal jes={d.journal_entries} />
      </>}
    </Layout>
  );
}

interface DepRes { schedule: Record<string, number>[]; depreciable_base: number; standard: string }
function Depreciation({ m, set }: { m: Model; set: (p: Partial<Model>) => void }) {
  const dp = m.dep;
  const u = (p: Partial<Model['dep']>) => set({ dep: { ...dp, ...p } });
  const units = dp.units.split(/[,\s]+/).filter(Boolean).map(Number);
  const ok = filled(dp, ['cost', 'salvage', 'life']) && (dp.method !== 'units' || (units.length === dp.life && units.every(Number.isFinite)));
  const r = useCalc<DepRes>('/api/accounting/depreciation', ok ? { ...dp, units: dp.method === 'units' ? units : null } : null);
  return (
    <Layout r={r} inputs={<div className="stack" style={{ gap: 10 }}>
      <NumberField label="Cost" value={dp.cost} onChange={(v) => u({ cost: v })} />
      <NumberField label="Residual (salvage) value" value={dp.salvage} onChange={(v) => u({ salvage: v })} />
      <NumberField label="Useful life (years)" value={dp.life} onChange={(v) => u({ life: v })} />
      <Select label="Method" value={dp.method} options={[['straight_line', 'Straight-line'], ['ddb', 'Double-declining balance (switch to SL)'], ['syd', "Sum-of-the-years'-digits"], ['units', 'Units of production']]} onChange={(v) => u({ method: v })} />
      {dp.method === 'units' && <Field label={`Units per year (${dp.life ?? '?'} figures, comma-separated)`}><input className="input" value={dp.units} onChange={(e) => u({ units: e.target.value })} /></Field>}
    </div>}>
      {(d: DepRes) => <>
        <div className="grid cols-3">
          <Kpi label="Depreciable base" value={fmtNum(d.depreciable_base, 2)} />
          <Kpi label="Year 1 charge" value={fmtNum(d.schedule[0]?.depreciation, 2)} />
          <Kpi label="Final carrying amount" value={fmtNum(d.schedule[d.schedule.length - 1]?.closing_nbv, 2)} />
        </div>
        <Schedule title="Depreciation schedule" file="depreciation.csv" sub={d.standard} rows={d.schedule}
          cols={[['year', 'Year', 'i'], ['opening_nbv', 'Opening carrying amount'], ['depreciation', 'Depreciation'], ['accumulated', 'Accumulated'], ['closing_nbv', 'Closing carrying amount']]} />
      </>}
    </Layout>
  );
}

interface EPSRes { basic: number; diluted: number; numerator_basic: number; numerator_diluted: number; shares_basic: number; shares_diluted: number; notes: string[]; standard: string;
  securities: { name: string; kind: string; incremental_shares: number; numerator_effect: number; per_share: number | null; included: boolean; reason: string; working?: string }[] }
function EPS({ m, set }: { m: Model; set: (p: Partial<Model>) => void }) {
  const e = m.eps;
  const u = (p: Partial<Model['eps']>) => set({ eps: { ...e, ...p } });
  const us = (i: number, p: Partial<Model['eps']['securities'][number]>) => u({ securities: e.securities.map((s, j) => (j === i ? { ...s, ...p } : s)) });
  const r = useCalc<EPSRes>('/api/accounting/eps', filled(e, ['net_income', 'preferred_dividends', 'weighted_shares']) && e.securities.every((s) => isNum(s.shares)) ? e : null);
  return (
    <div className="stack">
      <Card title="Inputs" actions={<button className="btn sm" onClick={() => u({ securities: [...e.securities, { kind: 'options', name: 'New security', shares: null, exercise_price: null, preferred_dividends: null, interest_after_tax: null }] })}><Plus size={14} />Security</button>}>
        <div className="grid cols-4" style={{ gap: 10 }}>
          <NumberField label="Net income" value={e.net_income} onChange={(v) => u({ net_income: v })} />
          <NumberField label="Preferred dividends (non-convertible + convertible)" value={e.preferred_dividends} onChange={(v) => u({ preferred_dividends: v })} />
          <NumberField label="Weighted average ordinary shares" value={e.weighted_shares} onChange={(v) => u({ weighted_shares: v })} />
          <NumberField label="Average market price (for options)" value={e.average_price} onChange={(v) => u({ average_price: v })} />
        </div>
        <div className="table-wrap mt-sm"><table className="data">
          <thead><tr><th>Potential ordinary shares</th><th>Type</th><th>Options / shares on conversion</th><th>Exercise price</th><th>Dividends added back</th><th>After-tax interest added back</th><th /></tr></thead>
          <tbody>{e.securities.map((s, i) => (
            <tr key={i}>
              <td><input className="input compact" aria-label="Security name" value={s.name} onChange={(ev) => us(i, { name: ev.target.value })} /></td>
              <td><select className="input compact" aria-label="Security type" value={s.kind} onChange={(ev) => us(i, { kind: ev.target.value })}>
                <option value="options">Options / warrants</option><option value="convertible_debt">Convertible debt</option><option value="convertible_preferred">Convertible preferred</option></select></td>
              <td><NumberField compact ariaLabel="Shares" value={s.shares} onChange={(v) => us(i, { shares: v })} /></td>
              <td><NumberField compact ariaLabel="Exercise price" value={s.exercise_price} onChange={(v) => us(i, { exercise_price: v })} /></td>
              <td><NumberField compact ariaLabel="Preferred dividends" value={s.preferred_dividends} onChange={(v) => us(i, { preferred_dividends: v })} /></td>
              <td><NumberField compact ariaLabel="After-tax interest" value={s.interest_after_tax} onChange={(v) => us(i, { interest_after_tax: v })} /></td>
              <td><button className="btn sm ghost" aria-label="Remove" onClick={() => u({ securities: e.securities.filter((_, j) => j !== i) })}><Trash2 size={14} /></button></td>
            </tr>
          ))}</tbody>
        </table></div>
      </Card>
      {r.error ? <ErrorBox error={r.error} /> : r.data ? (() => { const d = r.data; return <>
        <div className="grid cols-4">
          <Kpi label="Basic EPS" value={fmtNum(d.basic, 4)} />
          <Kpi label="Diluted EPS" value={fmtNum(d.diluted, 4)} />
          <Kpi label="Diluted numerator" value={fmtNum(d.numerator_diluted, 0)} />
          <Kpi label="Diluted shares" value={fmtNum(d.shares_diluted, 0)} />
        </div>
        <Card title="Dilution sequence" subtitle={d.standard}>
          <div className="table-wrap"><table className="data">
            <thead><tr><th>Security</th><th className="r">Incremental shares</th><th className="r">Numerator effect</th><th className="r">Incremental EPS</th><th>Result</th></tr></thead>
            <tbody>{d.securities.map((s) => <tr key={s.name}><td>{s.name}{s.working && <div className="faint mono" style={{ fontSize: 11 }}>{s.working}</div>}</td><td className="r">{fmtNum(s.incremental_shares, 2)}</td><td className="r">{fmtNum(s.numerator_effect, 2)}</td><td className="r">{isNum(s.per_share) ? fmtNum(s.per_share, 4) : '—'}</td>
              <td><Badge tone={s.included ? 'accent' : 'warn'}>{s.included ? 'Included' : 'Excluded'}</Badge> <span className="faint" style={{ fontSize: 12 }}>{s.reason}</span></td></tr>)}</tbody>
          </table></div>
          {d.notes.map((n) => <p key={n} className="faint mt-sm">{n}</p>)}
        </Card>
      </>; })() : <Skeleton h={100} />}
    </div>
  );
}

interface DTRes { items: { name: string; kind: string; carrying_amount: number; tax_base: number; temporary_difference: number; type: string; deferred_tax: number; nature: string }[]; total_dta: number; total_dtl: number; net_dtl: number; deferred_tax_expense: number; income_tax_expense?: number; journal_entries?: JE[]; standard: string }
function DeferredTax({ m, set }: { m: Model; set: (p: Partial<Model>) => void }) {
  const t = m.dt;
  const u = (p: Partial<Model['dt']>) => set({ dt: { ...t, ...p } });
  const ui = (i: number, p: Partial<Model['dt']['items'][number]>) => u({ items: t.items.map((x, j) => (j === i ? { ...x, ...p } : x)) });
  const r = useCalc<DTRes>('/api/accounting/deferred-tax', isNum(t.tax_rate) && t.items.length && t.items.every((x) => isNum(x.carrying_amount) && isNum(x.tax_base)) ? { ...t, opening_net_dtl: t.opening_net_dtl ?? 0 } : null);
  return (
    <div className="stack">
      <Card title="Temporary differences" actions={<button className="btn sm" onClick={() => u({ items: [...t.items, { name: 'New item', kind: 'asset', carrying_amount: null, tax_base: null }] })}><Plus size={14} />Item</button>}>
        <div className="grid cols-3" style={{ gap: 10, marginBottom: 12 }}>
          <NumberField label="Enacted tax rate" percent value={t.tax_rate} onChange={(v) => u({ tax_rate: v })} />
          <NumberField label="Current tax for the year (optional)" value={t.current_tax} onChange={(v) => u({ current_tax: v })} />
          <NumberField label="Opening net deferred tax liability" value={t.opening_net_dtl} onChange={(v) => u({ opening_net_dtl: v })} hint="Negative for a net asset" />
        </div>
        <div className="table-wrap"><table className="data">
          <thead><tr><th>Item</th><th>Asset or liability</th><th>Carrying amount</th><th>Tax base</th><th /></tr></thead>
          <tbody>{t.items.map((x, i) => (
            <tr key={i}>
              <td><input className="input compact" aria-label="Item" value={x.name} onChange={(e) => ui(i, { name: e.target.value })} /></td>
              <td><select className="input compact" aria-label="Kind" value={x.kind} onChange={(e) => ui(i, { kind: e.target.value })}><option value="asset">Asset</option><option value="liability">Liability</option></select></td>
              <td><NumberField compact ariaLabel="Carrying amount" value={x.carrying_amount} onChange={(v) => ui(i, { carrying_amount: v })} /></td>
              <td><NumberField compact ariaLabel="Tax base" value={x.tax_base} onChange={(v) => ui(i, { tax_base: v })} /></td>
              <td><button className="btn sm ghost" aria-label="Remove" disabled={t.items.length <= 1} onClick={() => u({ items: t.items.filter((_, j) => j !== i) })}><Trash2 size={14} /></button></td>
            </tr>
          ))}</tbody>
        </table></div>
      </Card>
      {r.error ? <ErrorBox error={r.error} /> : r.data ? (() => { const d = r.data; return <>
        <div className="grid cols-4">
          <Kpi label="Deferred tax assets" value={fmtNum(d.total_dta, 2)} />
          <Kpi label="Deferred tax liabilities" value={fmtNum(d.total_dtl, 2)} />
          <Kpi label="Deferred tax expense / (benefit)" value={fmtNum(d.deferred_tax_expense, 2)} />
          <Kpi label="Total income tax expense" value={isNum(d.income_tax_expense) ? fmtNum(d.income_tax_expense, 2) : '—'} />
        </div>
        <Schedule title="Deferred tax computation" file="deferred-tax.csv" sub={d.standard} rows={d.items}
          cols={[['name', 'Item', 'i'], ['carrying_amount', 'Carrying amount'], ['tax_base', 'Tax base'], ['temporary_difference', 'Temporary difference'], ['type', 'Type', 'i'], ['deferred_tax', 'Deferred tax'], ['nature', 'DTA / DTL', 'i']]} />
        {d.journal_entries && <Journal jes={d.journal_entries} />}
      </>; })() : <Skeleton h={100} />}
    </div>
  );
}

const BENCH: [keyof Model['mat']['values'], string][] = [['profit_before_tax', 'Profit before tax'], ['revenue', 'Revenue'], ['total_assets', 'Total assets'], ['equity', 'Equity'], ['expenses', 'Total expenses']];
interface MatRes { overall: number; performance: number; clearly_trivial: number; ranges: { label: string; amount: number; low_pct: number; high_pct: number; low: number; high: number }[]; notes: string[]; standard: string }
function Materiality({ m, set }: { m: Model; set: (p: Partial<Model>) => void }) {
  const { settings } = useSettings();
  const t = m.mat;
  const u = (p: Partial<Model['mat']>) => set({ mat: { ...t, ...p } });
  const r = useCalc<MatRes>('/api/accounting/materiality', isNum(t.pct) && isNum(t.values[t.selected as keyof Model['mat']['values']]) ? { ...t, performance_pct: t.performance_pct ?? 0.75, trivial_pct: t.trivial_pct ?? 0.05 } : null);
  const money = (v: number) => fmtNum(v, 0, settings.currency);
  return (
    <Layout r={r} inputs={<div className="stack" style={{ gap: 10 }}>
      {BENCH.map(([k, l]) => <NumberField key={k} label={l} value={t.values[k]} onChange={(v) => u({ values: { ...t.values, [k]: v } })} />)}
      <Select label="Benchmark used" value={t.selected} options={BENCH.map(([k, l]) => [k, l])} onChange={(v) => u({ selected: v })} />
      <NumberField label="Percentage applied" percent value={t.pct} onChange={(v) => u({ pct: v })} />
      <NumberField label="Performance materiality (% of overall)" percent value={t.performance_pct} onChange={(v) => u({ performance_pct: v })} hint="Typically 50–75% depending on assessed risk" />
      <NumberField label="Clearly trivial threshold (% of overall)" percent value={t.trivial_pct} onChange={(v) => u({ trivial_pct: v })} hint="Typically 3–5%" />
    </div>}>
      {(d: MatRes) => <>
        <div className="grid cols-3">
          <Kpi label="Overall materiality" value={money(d.overall)} />
          <Kpi label="Performance materiality" value={money(d.performance)} />
          <Kpi label="Clearly trivial" value={money(d.clearly_trivial)} />
        </div>
        {d.notes.map((n) => <Callout key={n} tone="warn">{n}</Callout>)}
        <Card title="Benchmark ranges" subtitle={d.standard}>
          <div className="table-wrap"><table className="data">
            <thead><tr><th>Benchmark</th><th className="r">Amount</th><th className="r">Common range</th><th className="r">Materiality range</th></tr></thead>
            <tbody>{d.ranges.map((x) => <tr key={x.label}><td>{x.label}</td><td className="r">{money(x.amount)}</td><td className="r">{fmtPct(x.low_pct, 1)} – {fmtPct(x.high_pct, 1)}</td><td className="r">{money(x.low)} – {money(x.high)}</td></tr>)}</tbody>
          </table></div>
        </Card>
      </>}
    </Layout>
  );
}
