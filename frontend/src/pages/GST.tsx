import { Download, ExternalLink, FileSpreadsheet, Upload } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { SaveLoad } from '../components/SaveLoad';
import { Badge, Callout, Card, ErrorBox, Field, Kpi, NumberField, PageHeader, Skeleton, Tabs } from '../components/ui';
import { api } from '../lib/api';
import { downloadFile, fmtMoney, isNum, toCSV } from '../lib/format';
import { loadRaw, save } from '../lib/storage';
import { useAsync, useDebounced } from '../lib/useApi';

type Tab = 'returns' | 'gstr3b' | 'gstr1' | 'recon' | 'file';
type N = number | null;
type HeadKey = 'igst' | 'cgst' | 'sgst' | 'cess';
type HeadsN = Record<HeadKey, N>;
const HEADS: HeadKey[] = ['igst', 'cgst', 'sgst', 'cess'];
const inr = (v: N | undefined) => fmtMoney(v ?? null, 'INR', 2);
const blank = (): HeadsN => ({ igst: null, cgst: null, sgst: null, cess: null });
const zero = (h: HeadsN) => Object.fromEntries(HEADS.map((k) => [k, isNum(h[k]) ? h[k] : 0]));

interface Info { states: Record<string, string>; sources: Record<string, string>; filing_steps: Record<string, string[]>; filing_note: string }
interface RetRow { form: string; what: string; frequency: string; due: string; next_due: string | null; optional: boolean; source: string }
interface RetRes { returns: RetRow[]; state: string; period?: string; financial_year?: string; warnings: string[]; notes: string[]; registration_required?: boolean; threshold?: number; message?: string }
interface B3Res {
  table_6_1: { head: string; tax_payable: number; paid_through_itc: Record<string, number>; paid_in_cash: number }[];
  cash: Record<HeadKey, number>; total_cash: number; credit_used: number; closing_credit: Record<HeadKey, number>; utilisation: Record<string, number>;
  itc: { net: Record<HeadKey, number>; total: Record<HeadKey, number> };
  interest: { days: number; amount: number } | null; late_fee: { days: number; fee: number; cap: number } | null; warnings: string[]; notes: string[];
}
interface InvRow { number: string; date: string | null; gstin: string | null; state: string; rate: number | null; taxable_value: number; igst: number; cgst: number; sgst: number; cess: number; invoice_value: number; note_type?: string; row: number | null }
interface G1Res {
  tables: { b2b: InvRow[]; b2cl: InvRow[]; exp: InvRow[]; sez: InvRow[]; cdnr: InvRow[]; cdnur: InvRow[]; b2cs: { state: string; rate: number; taxable_value: number; igst: number; cgst: number; sgst: number; cess: number; count: number }[];
    nil: Record<string, Record<string, number>>; hsn: { section: string; hsn: string; rate: number | null; taxable_value: number; igst: number; cgst: number; sgst: number; cess: number; count: number }[];
    documents: { document: string; count: number; from: string; to: string }[] };
  summary: Record<string, { taxable_value: number; igst: number; cgst: number; sgst: number; cess: number; count: number }>;
  liability: Record<HeadKey, number>; issues: { row: number | null; invoice: string; level: string; message: string }[]; errors: number; warnings: number; notes: string[];
  file: { name: string; sheet: string; rows: number; skipped: number; columns: Record<string, string> };
}
interface RecSide { gstin: string; number: string; date: string | null; taxable_value: number; tax: number; row: number | null }
interface RecRes {
  summary: Record<string, { count: number; tax?: number; tax_books?: number; tax_2b?: number }> & { credit_safe_to_claim: number };
  rows: { status: string; books: RecSide | null; gstr2b: RecSide | null; note: string; tax_difference: number }[]; notes: string[];
}

const PROFILE = { registration: 'regular', state_code: '27', aggregate_turnover_prev_fy: 30000000 as N, supplies: 'goods', composition_kind: 'trader', qrmp: false, year: 2026, month: 9 };
const B3 = { outward_tax: { igst: 180000, cgst: 90000, sgst: 90000, cess: 0 } as HeadsN, reverse_charge_tax: blank(), eco_9_5_tax: blank(),
  itc_available: { igst: 150000, cgst: 60000, sgst: 50000, cess: 0 } as HeadsN, itc_reversed: blank(), opening_credit: blank(),
  taxable_value_month: 2000000 as N, rule_86b_applies: false, due_date: '', filing_date: '', nil_return: false, aggregate_turnover: 30000000 as N };
type Model = { profile: typeof PROFILE; b3: typeof B3; gstin: string; aato: N };
const EXAMPLE: Model = { profile: PROFILE, b3: B3, gstin: '', aato: null };

function Select<T extends string>({ label, value, onChange, options }: { label: string; value: T; onChange: (v: T) => void; options: [T, string][] }) {
  return <Field label={label}><select className="input" value={value} onChange={(e) => onChange(e.target.value as T)}>{options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>;
}
function Check({ label, checked, onChange }: { label: ReactNode; checked: boolean; onChange: (v: boolean) => void }) {
  return <label className="row" style={{ gap: 8, fontSize: 13 }}><input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />{label}</label>;
}
function useCalc<T>(path: string, body: unknown) {
  const req = useDebounced(body, 300);
  return useAsync(() => api.post<T>(path, req), [JSON.stringify(req)], !!req);
}

export function GST() {
  const [tab, setTab] = useState<Tab>(() => loadRaw('fis.gst.tab', 'returns'));
  const [state, setState] = useState<{ m: Model; example: boolean }>(() => loadRaw('fis.gst', { m: EXAMPLE, example: true }));
  const m = state.m;
  const set = (p: Partial<Model>) => { const s = { m: { ...m, ...p }, example: false }; setState(s); save('fis.gst', s); };
  const info = useAsync(() => api.get<Info>('/api/gst/info'), []);
  return (
    <div className="page">
      <PageHeader title="GST Returns" badge={state.example ? <Badge tone="sample">Example figures</Badge> : <Badge tone="accent">Your figures</Badge>}
        subtitle="Which returns apply and when they are due, GSTR-3B credit set-off in the order the law requires, GSTR-1 tables built from your sales register, and purchase register vs GSTR-2B matching."
        actions={<>
          <SaveLoad kind="gst" label="GST working" getData={() => m} onLoad={(d: Model) => { const s = { m: { ...EXAMPLE, ...d }, example: false }; setState(s); save('fis.gst', s); }} />
          <button className="btn" onClick={() => { setState({ m: EXAMPLE, example: true }); save('fis.gst', { m: EXAMPLE, example: true }); }}>Example</button>
        </>} />
      <Callout tone="info" title="Prepares returns; does not file them">
        Filing through software needs a licensed GST Suvidha Provider and the taxpayer's API consent. File on the <a href="https://www.gst.gov.in/" target="_blank" rel="noreferrer">GST portal</a> with EVC or DSC using these figures. Your sales and purchase files are read in memory and not stored.
      </Callout>
      <div className="mt">
        <Tabs label="Section" value={tab} onChange={(t) => { setTab(t); save('fis.gst.tab', t); }} options={[
          { value: 'returns', label: 'Which returns' }, { value: 'gstr3b', label: 'GSTR-3B' }, { value: 'gstr1', label: 'GSTR-1 from sales register' },
          { value: 'recon', label: 'GSTR-2B reconciliation' }, { value: 'file', label: 'How to file' }]} />
      </div>
      <div className="mt">
        {tab === 'returns' && <Returns m={m} set={set} states={info.data?.states} />}
        {tab === 'gstr3b' && <GSTR3B m={m} set={set} />}
        {tab === 'gstr1' && <GSTR1 m={m} set={set} />}
        {tab === 'recon' && <Recon />}
        {tab === 'file' && <HowToFile info={info.data} />}
      </div>
    </div>
  );
}

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const fmtDate = (s: string | null) => (s ? new Date(s + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '—');

function Returns({ m, set, states }: { m: Model; set: (p: Partial<Model>) => void; states?: Record<string, string> }) {
  const p = m.profile;
  const up = (x: Partial<typeof PROFILE>) => set({ profile: { ...p, ...x } });
  const r = useCalc<RetRes>('/api/gst/returns', { ...p, aggregate_turnover_prev_fy: p.aggregate_turnover_prev_fy ?? 0 });
  return (
    <div className="grid cols-2">
      <Card title="Business" subtitle="Registration and turnover">
        <div className="grid cols-2" style={{ gap: 10 }}>
          <Select label="Registration" value={p.registration} onChange={(v) => up({ registration: v })} options={[['regular', 'Regular taxpayer'], ['composition', 'Composition scheme'], ['not_registered', 'Not registered yet'], ['non_resident', 'Non-resident taxable person'], ['oidar', 'OIDAR (online services from abroad)'], ['isd', 'Input Service Distributor'], ['tds_deductor', 'TDS deductor (s.51)'], ['tcs_operator', 'E-commerce operator (TCS, s.52)'], ['uin', 'UIN holder (embassy, UN body)']]} />
          <Field label="State of registration"><select className="input" value={p.state_code} onChange={(e) => up({ state_code: e.target.value })}>
            {Object.entries(states ?? { '27': 'Maharashtra' }).map(([c, n]) => <option key={c} value={c}>{c} – {n}</option>)}</select></Field>
          <NumberField label="Aggregate turnover, previous year (₹)" value={p.aggregate_turnover_prev_fy} onChange={(v) => up({ aggregate_turnover_prev_fy: v })} />
          <Select label="Supplies" value={p.supplies} onChange={(v) => up({ supplies: v })} options={[['goods', 'Goods only'], ['services', 'Services only'], ['both', 'Goods and services']]} />
          {p.registration === 'composition' && <Select label="Composition type" value={p.composition_kind} onChange={(v) => up({ composition_kind: v })} options={[['trader', 'Trader (1%)'], ['manufacturer', 'Manufacturer (1%)'], ['restaurant', 'Restaurant (5%)'], ['services', 'Services (6%)']]} />}
          <Field label="Tax period"><div className="row" style={{ flexWrap: 'nowrap' }}>
            <select className="input" value={p.month} onChange={(e) => up({ month: Number(e.target.value) })}>{MONTHS.map((n, i) => <option key={n} value={i + 1}>{n}</option>)}</select>
            <input className="input" style={{ width: 90 }} type="number" value={p.year} onChange={(e) => up({ year: Number(e.target.value) || 2026 })} /></div></Field>
        </div>
        {p.registration === 'regular' && <div className="mt-sm"><Check label="Opted for QRMP (quarterly returns, monthly payment)" checked={p.qrmp} onChange={(v) => up({ qrmp: v })} /></div>}
      </Card>
      <Card title="Returns for this period" subtitle={r.data?.period ? `${MONTHS[p.month - 1]} ${p.year} · FY ${r.data.financial_year} · ${r.data.state}` : undefined}>
        {r.error ? <ErrorBox error={r.error} /> : !r.data ? <Skeleton h={120} /> : r.data.message ? (
          <Callout tone={r.data.registration_required ? 'warn' : 'success'} title={r.data.registration_required ? 'Registration required' : 'Registration not required on turnover'}>{r.data.message}</Callout>
        ) : (
          <>
            {r.data.warnings.map((w) => <Callout key={w} tone="warn">{w}</Callout>)}
            <div className="table-wrap mt-sm"><table className="data">
              <thead><tr><th>Return</th><th>What</th><th>Due</th><th>Next due</th></tr></thead>
              <tbody>{r.data.returns.map((x) => (
                <tr key={x.form}><td><b>{x.form}</b>{x.optional && <div><Badge>optional</Badge></div>}</td><td style={{ whiteSpace: 'normal', minWidth: 160 }}>{x.what}<div className="faint" style={{ fontSize: 11 }}>{x.frequency}</div></td>
                  <td style={{ whiteSpace: 'normal', minWidth: 120, fontSize: 12 }}>{x.due}</td><td>{fmtDate(x.next_due)}</td></tr>))}</tbody></table></div>
            <ul className="faint mt-sm" style={{ fontSize: 12, paddingLeft: 18 }}>{r.data.notes.map((n) => <li key={n}>{n}</li>)}</ul>
          </>
        )}
      </Card>
    </div>
  );
}

function HeadsGrid({ label, value, onChange, hint }: { label: string; value: HeadsN; onChange: (h: HeadsN) => void; hint?: string }) {
  return (
    <tr>
      <td style={{ whiteSpace: 'normal', minWidth: 170 }}>{label}{hint && <div className="faint" style={{ fontSize: 11 }}>{hint}</div>}</td>
      {HEADS.map((h) => <td key={h} style={{ minWidth: 110 }}><NumberField compact ariaLabel={`${label} ${h}`} value={value[h]} onChange={(v) => onChange({ ...value, [h]: v })} /></td>)}
    </tr>
  );
}

function GSTR3B({ m, set }: { m: Model; set: (p: Partial<Model>) => void }) {
  const b = m.b3;
  const up = (x: Partial<typeof B3>) => set({ b3: { ...b, ...x } });
  const body = { outward_tax: zero(b.outward_tax), reverse_charge_tax: zero(b.reverse_charge_tax), eco_9_5_tax: zero(b.eco_9_5_tax), itc_available: zero(b.itc_available),
    itc_reversed: zero(b.itc_reversed), opening_credit: zero(b.opening_credit), taxable_value_month: b.taxable_value_month, rule_86b_applies: b.rule_86b_applies,
    due_date: b.due_date || null, filing_date: b.filing_date || null, nil_return: b.nil_return, aggregate_turnover: b.aggregate_turnover };
  const r = useCalc<B3Res>('/api/gst/gstr3b', body);
  return (
    <div className="stack">
      <Card title="Liability and input tax credit" subtitle="Tax amounts in rupees. Outward liability comes from GSTR-1; credit from GSTR-2B (Table 4A)">
        <div className="table-wrap"><table className="data">
          <thead><tr><th /><th>IGST</th><th>CGST</th><th>SGST / UTGST</th><th>Cess</th></tr></thead>
          <tbody>
            <HeadsGrid label="Outward taxable supplies (3.1 a, b)" value={b.outward_tax} onChange={(h) => up({ outward_tax: h })} />
            <HeadsGrid label="Reverse charge (3.1 d)" hint="Paid in cash only" value={b.reverse_charge_tax} onChange={(h) => up({ reverse_charge_tax: h })} />
            <HeadsGrid label="E-commerce operator, s.9(5) (3.1.1 i)" hint="Paid in cash only" value={b.eco_9_5_tax} onChange={(h) => up({ eco_9_5_tax: h })} />
            <HeadsGrid label="ITC available (4A)" value={b.itc_available} onChange={(h) => up({ itc_available: h })} />
            <HeadsGrid label="ITC reversed (4B)" hint="Rules 42/43, s.17(5), others" value={b.itc_reversed} onChange={(h) => up({ itc_reversed: h })} />
            <HeadsGrid label="Opening credit ledger balance" value={b.opening_credit} onChange={(h) => up({ opening_credit: h })} />
          </tbody></table></div>
        <div className="grid cols-4 mt" style={{ gap: 10 }}>
          <NumberField label="Taxable value this month (₹)" hint="Above ₹50 lakh → Rule 86B check" value={b.taxable_value_month} onChange={(v) => up({ taxable_value_month: v })} />
          <NumberField label="Aggregate turnover (₹)" hint="For the late-fee cap" value={b.aggregate_turnover} onChange={(v) => up({ aggregate_turnover: v })} />
          <Field label="Due date"><input className="input" type="date" value={b.due_date} onChange={(e) => up({ due_date: e.target.value })} /></Field>
          <Field label="Filing / payment date"><input className="input" type="date" value={b.filing_date} onChange={(e) => up({ filing_date: e.target.value })} /></Field>
        </div>
        <div className="row mt-sm" style={{ gap: 18 }}>
          <Check label="Rule 86B applies regardless of the monthly value" checked={b.rule_86b_applies} onChange={(v) => up({ rule_86b_applies: v })} />
          <Check label="Nil return" checked={b.nil_return} onChange={(v) => up({ nil_return: v })} />
        </div>
      </Card>
      {r.error ? <ErrorBox error={r.error} /> : !r.data ? <Skeleton h={160} /> : (
        <>
          <div className="grid cols-4">
            <Kpi label="Cash to pay (all heads)" value={inr(r.data.total_cash)} />
            <Kpi label="Credit used" value={inr(r.data.credit_used)} />
            <Kpi label="Interest (18% a year)" value={inr(r.data.interest?.amount ?? 0)} delta={r.data.interest ? `${r.data.interest.days} days late` : 'On time'} deltaTone={r.data.interest ? 'neg' : 'pos'} />
            <Kpi label="Late fee" value={inr(r.data.late_fee?.fee ?? 0)} delta={r.data.late_fee ? `cap ${inr(r.data.late_fee.cap)}` : undefined} deltaTone="muted" />
          </div>
          <Card title="Payment of tax (Table 6.1)" subtitle="Credit applied in the order of section 49, 49A and Rule 88A, keeping cash to the minimum">
            <div className="table-wrap"><table className="data">
              <thead><tr><th>Head</th><th className="r">Tax payable</th><th className="r">Paid by IGST credit</th><th className="r">CGST credit</th><th className="r">SGST credit</th><th className="r">Cess credit</th><th className="r">Paid in cash</th></tr></thead>
              <tbody>{r.data.table_6_1.map((t) => (
                <tr key={t.head}><td><b>{t.head}</b></td><td className="r">{inr(t.tax_payable)}</td>
                  {['IGST', 'CGST', 'SGST', 'CESS'].map((c) => <td key={c} className="r">{t.paid_through_itc[c] ? inr(t.paid_through_itc[c]) : '—'}</td>)}
                  <td className="r"><b>{inr(t.paid_in_cash)}</b></td></tr>))}</tbody></table></div>
            <div className="grid cols-4 mt-sm">{HEADS.map((h) => <div key={h} className="metric-row"><span>Closing {h.toUpperCase()} credit</span><span className="v">{inr(r.data!.closing_credit[h])}</span></div>)}</div>
            {r.data.warnings.map((w) => <div key={w} className="mt-sm"><Callout tone="warn">{w}</Callout></div>)}
            <ul className="faint mt-sm" style={{ fontSize: 12, paddingLeft: 18 }}>{r.data.notes.map((n) => <li key={n}>{n}</li>)}
              <li>Order: IGST credit → IGST, then CGST/SGST; CGST credit → CGST, then IGST; SGST credit → SGST, then IGST. CGST credit never pays SGST, or the reverse.</li></ul>
          </Card>
        </>
      )}
    </div>
  );
}

function FilePick({ label, file, onFile }: { label: string; file: File | null; onFile: (f: File | null) => void }) {
  return (
    <Field label={label}>
      <label className="btn" style={{ justifyContent: 'flex-start', overflow: 'hidden' }}>
        <Upload size={15} /><span className="truncate">{file ? file.name : 'Choose .xlsx or .csv'}</span>
        <input type="file" accept=".xlsx,.xlsm,.csv" hidden onChange={(e) => onFile(e.target.files?.[0] ?? null)} />
      </label>
    </Field>
  );
}
function csvOf(name: string, header: string[], rows: unknown[][]) { downloadFile(name, toCSV([header, ...rows])); }

function GSTR1({ m, set }: { m: Model; set: (p: Partial<Model>) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [res, setRes] = useState<G1Res | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    if (!file) return;
    setBusy(true); setErr(null);
    try { setRes(await api.form<G1Res>('/api/gst/gstr1', { file, supplier_gstin: m.gstin.trim().toUpperCase(), aggregate_turnover: isNum(m.aato) ? String(m.aato) : null })); }
    catch (e) { setErr((e as Error).message); setRes(null); } finally { setBusy(false); }
  };
  const inv = (rows: InvRow[]) => rows.map((r) => [r.number, r.date, r.gstin ?? '', r.state, r.rate, r.taxable_value, r.igst, r.cgst, r.sgst, r.cess, r.invoice_value]);
  const invHead = ['Invoice', 'Date', 'GSTIN', 'Place of supply', 'Rate %', 'Taxable value', 'IGST', 'CGST', 'SGST', 'Cess', 'Invoice value'];
  return (
    <div className="stack">
      <Card title="Sales register" subtitle="One row per invoice or note. Column names are recognised automatically (invoice number, date, customer GSTIN, place of supply, taxable value, rate or tax amounts, HSN)."
        actions={<a className="btn sm" href="/api/gst/template/sales"><Download size={14} />Template</a>}>
        <div className="grid cols-4" style={{ gap: 10, alignItems: 'end' }}>
          <Field label="Your GSTIN"><input className="input" value={m.gstin} maxLength={15} placeholder="27AAPFU0939F1ZV" onChange={(e) => set({ gstin: e.target.value })} /></Field>
          <NumberField label="Last year's turnover (₹, sets HSN digits)" value={m.aato} onChange={(v) => set({ aato: v })} />
          <FilePick label="Sales register" file={file} onFile={setFile} />
          <button className="btn primary" disabled={!file || m.gstin.trim().length !== 15 || busy} onClick={run}><FileSpreadsheet size={15} />{busy ? 'Reading…' : 'Build GSTR-1'}</button>
        </div>
        {err && <div className="mt-sm"><ErrorBox error={err} /></div>}
      </Card>
      {res && (
        <>
          <div className="grid cols-4">
            <Kpi label="IGST liability" value={inr(res.liability.igst)} />
            <Kpi label="CGST liability" value={inr(res.liability.cgst)} />
            <Kpi label="SGST liability" value={inr(res.liability.sgst)} />
            <Kpi label="Errors / warnings" value={`${res.errors} / ${res.warnings}`} delta={`${res.file.rows} rows read from ${res.file.sheet}`} deltaTone={res.errors ? 'neg' : 'pos'} />
          </div>
          <Card title="Summary by table" subtitle="Negative notes reduce liability">
            <div className="table-wrap"><table className="data">
              <thead><tr><th>Table</th><th className="r">Documents</th><th className="r">Taxable value</th><th className="r">IGST</th><th className="r">CGST</th><th className="r">SGST</th><th className="r">Cess</th></tr></thead>
              <tbody>{Object.entries(res.summary).map(([k, s]) => <tr key={k}><td>{TABLE_NAMES[k] ?? k}</td><td className="r">{s.count}</td><td className="r">{inr(s.taxable_value)}</td><td className="r">{inr(s.igst)}</td><td className="r">{inr(s.cgst)}</td><td className="r">{inr(s.sgst)}</td><td className="r">{inr(s.cess)}</td></tr>)}</tbody>
            </table></div>
            <div className="row mt-sm">
              {(['b2b', 'b2cl', 'exp', 'cdnr', 'cdnur'] as const).filter((k) => res.tables[k].length).map((k) => <button key={k} className="btn sm" onClick={() => csvOf(`gstr1-${k}.csv`, invHead, inv(res.tables[k]))}><Download size={13} />{k.toUpperCase()}</button>)}
              {res.tables.b2cs.length > 0 && <button className="btn sm" onClick={() => csvOf('gstr1-b2cs.csv', ['Place of supply', 'Rate %', 'Taxable value', 'IGST', 'CGST', 'SGST', 'Cess'], res.tables.b2cs.map((b) => [b.state, b.rate, b.taxable_value, b.igst, b.cgst, b.sgst, b.cess]))}><Download size={13} />B2CS</button>}
              {res.tables.hsn.length > 0 && <button className="btn sm" onClick={() => csvOf('gstr1-hsn.csv', ['Section', 'HSN', 'Rate %', 'Taxable value', 'IGST', 'CGST', 'SGST', 'Cess', 'Lines'], res.tables.hsn.map((h) => [h.section, h.hsn, h.rate, h.taxable_value, h.igst, h.cgst, h.sgst, h.cess, h.count]))}><Download size={13} />HSN (Table 12)</button>}
            </div>
          </Card>
          {res.issues.length > 0 && (
            <Card title="Problems found" subtitle="Fix these in your books before filing">
              <div className="table-wrap" style={{ maxHeight: 360 }}><table className="data">
                <thead><tr><th>Row</th><th>Document</th><th>Level</th><th>Message</th></tr></thead>
                <tbody>{res.issues.map((i, k) => <tr key={k}><td>{i.row ?? '—'}</td><td>{i.invoice}</td><td><Badge tone={i.level === 'error' ? 'neg' : 'warn'}>{i.level}</Badge></td><td style={{ whiteSpace: 'normal' }}>{i.message}</td></tr>)}</tbody>
              </table></div>
            </Card>
          )}
          <div className="grid cols-2">
            <Card title="B2C small (Table 7)" subtitle="By place of supply and rate">
              {res.tables.b2cs.length === 0 ? <p className="faint">None.</p> : <div className="table-wrap"><table className="data">
                <thead><tr><th>Place of supply</th><th className="r">Rate</th><th className="r">Taxable value</th><th className="r">Tax</th></tr></thead>
                <tbody>{res.tables.b2cs.map((b) => <tr key={b.state + b.rate}><td>{b.state}</td><td className="r">{b.rate}%</td><td className="r">{inr(b.taxable_value)}</td><td className="r">{inr(b.igst + b.cgst + b.sgst)}</td></tr>)}</tbody></table></div>}
            </Card>
            <Card title="HSN summary (Table 12)" subtitle="Split into B2B and B2C">
              <div className="table-wrap" style={{ maxHeight: 300 }}><table className="data">
                <thead><tr><th>Section</th><th>HSN / SAC</th><th className="r">Rate</th><th className="r">Taxable value</th><th className="r">Tax</th></tr></thead>
                <tbody>{res.tables.hsn.map((h, i) => <tr key={i}><td>{h.section}</td><td>{h.hsn}</td><td className="r">{h.rate ?? '—'}%</td><td className="r">{inr(h.taxable_value)}</td><td className="r">{inr(h.igst + h.cgst + h.sgst)}</td></tr>)}</tbody></table></div>
            </Card>
          </div>
          <ul className="faint" style={{ fontSize: 12, paddingLeft: 18 }}>{res.notes.map((n) => <li key={n}>{n}</li>)}</ul>
        </>
      )}
    </div>
  );
}
const TABLE_NAMES: Record<string, string> = { '4A_b2b': '4A – B2B invoices', '5_b2cl': '5 – B2C large (inter-state, over ₹1 lakh)', '6A_exports': '6A – Exports', '6B_sez': '6B/6C – SEZ and deemed exports', '7_b2cs': '7 – B2C small (groups)', '9B_cdnr': '9B – Credit/debit notes (registered)', '9B_cdnur': '9B – Credit/debit notes (unregistered)' };

const STATUS: Record<string, [string, 'accent' | 'warn' | 'neg' | 'info']> = {
  matched: ['Matched', 'accent'], mismatch: ['Amount differs', 'warn'], probable: ['Probable match', 'info'], missing_in_2b: ['Not in GSTR-2B', 'neg'], missing_in_books: ['Not in books', 'warn'],
};

function Recon() {
  const [books, setBooks] = useState<File | null>(null);
  const [portal, setPortal] = useState<File | null>(null);
  const [res, setRes] = useState<RecRes | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState('all');
  const run = async () => {
    if (!books || !portal) return;
    setBusy(true); setErr(null);
    try { setRes(await api.form<RecRes>('/api/gst/reconcile', { books, gstr2b: portal })); } catch (e) { setErr((e as Error).message); setRes(null); } finally { setBusy(false); }
  };
  const rows = res ? res.rows.filter((r) => filter === 'all' || r.status === filter) : [];
  return (
    <div className="stack">
      <Card title="Purchase register vs GSTR-2B" subtitle="Download GSTR-2B (Excel) from the portal and upload it with your purchase register"
        actions={<a className="btn sm" href="/api/gst/template/purchases"><Download size={14} />Template</a>}>
        <div className="grid cols-3" style={{ gap: 10, alignItems: 'end' }}>
          <FilePick label="Purchase register (your books)" file={books} onFile={setBooks} />
          <FilePick label="GSTR-2B (from the portal)" file={portal} onFile={setPortal} />
          <button className="btn primary" disabled={!books || !portal || busy} onClick={run}><FileSpreadsheet size={15} />{busy ? 'Matching…' : 'Reconcile'}</button>
        </div>
        {err && <div className="mt-sm"><ErrorBox error={err} /></div>}
      </Card>
      {res && (
        <>
          <div className="grid cols-5">
            {Object.entries(STATUS).map(([k, [label]]) => { const s = res.summary[k]; return <Kpi key={k} label={label} value={String(s.count)} delta={inr(s.tax ?? s.tax_books ?? 0)} deltaTone="muted" />; })}
          </div>
          <Callout tone="success" title={`Credit safe to claim now: ${inr(res.summary.credit_safe_to_claim)}`}>{res.notes[0]}</Callout>
          <Card title="Line by line" actions={<>
            <select className="input compact" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter"><option value="all">All</option>{Object.entries(STATUS).map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}</select>
            <button className="btn sm" onClick={() => csvOf('gstr2b-reconciliation.csv', ['Status', 'Supplier GSTIN', 'Invoice (books)', 'Invoice (2B)', 'Taxable (books)', 'Taxable (2B)', 'Tax (books)', 'Tax (2B)', 'Difference', 'Note'],
              res.rows.map((r) => [STATUS[r.status][0], (r.books ?? r.gstr2b)?.gstin, r.books?.number ?? '', r.gstr2b?.number ?? '', r.books?.taxable_value ?? '', r.gstr2b?.taxable_value ?? '', r.books?.tax ?? '', r.gstr2b?.tax ?? '', r.tax_difference, r.note]))}><Download size={13} />CSV</button></>}>
            <div className="table-wrap" style={{ maxHeight: 460 }}><table className="data">
              <thead><tr><th>Status</th><th>Supplier GSTIN</th><th>Invoice (books / 2B)</th><th className="r">Tax (books)</th><th className="r">Tax (2B)</th><th>Note</th></tr></thead>
              <tbody>{rows.map((r, i) => (
                <tr key={i}><td><Badge tone={STATUS[r.status][1]}>{STATUS[r.status][0]}</Badge></td><td className="mono" style={{ fontSize: 12 }}>{(r.books ?? r.gstr2b)?.gstin}</td>
                  <td>{r.books?.number ?? '—'}{r.gstr2b && r.books && r.gstr2b.number !== r.books.number ? <div className="faint" style={{ fontSize: 11 }}>2B: {r.gstr2b.number}</div> : !r.books ? <div className="faint" style={{ fontSize: 11 }}>2B: {r.gstr2b?.number}</div> : null}</td>
                  <td className="r">{r.books ? inr(r.books.tax) : '—'}</td><td className="r">{r.gstr2b ? inr(r.gstr2b.tax) : '—'}</td><td style={{ whiteSpace: 'normal', fontSize: 12, minWidth: 220 }}>{r.note}</td></tr>))}</tbody></table></div>
          </Card>
        </>
      )}
    </div>
  );
}

function HowToFile({ info }: { info: Info | null }) {
  return (
    <div className="grid cols-2">
      {(['gstr1', 'gstr3b'] as const).map((k) => (
        <Card key={k} title={k === 'gstr1' ? 'Filing GSTR-1' : 'Filing GSTR-3B'}>
          <ol style={{ paddingLeft: 18, display: 'grid', gap: 8, margin: 0 }}>{(info?.filing_steps[k] ?? []).map((s) => <li key={s}>{s}</li>)}</ol>
        </Card>
      ))}
      <Card title="Official tools">
        <div className="row">
          <a className="btn primary" href="https://www.gst.gov.in/" target="_blank" rel="noreferrer"><ExternalLink size={15} />GST portal</a>
          <a className="btn" href="https://www.gst.gov.in/download/returns" target="_blank" rel="noreferrer"><Download size={15} />Returns Offline Tool</a>
        </div>
        <p className="mt-sm">{info?.filing_note}</p>
      </Card>
      <Card title="Rates in force">
        <p>Since 22 September 2025 ("GST 2.0") the main rates are <b>5%</b> and <b>18%</b>, with <b>40%</b> on luxury and sin goods; 12% and 28% were removed. Special rates remain (3% gold and silver, 1.5% / 0.25% diamonds). Compensation cess ended on 1 February 2026.</p>
        <a href="https://www.pib.gov.in/PressReleasePage.aspx?PRID=2163560" target="_blank" rel="noreferrer">Press release <ExternalLink size={11} /></a>
      </Card>
    </div>
  );
}
