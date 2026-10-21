import { CalendarClock, Download, ExternalLink, FileCheck2, Landmark } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { SaveLoad } from '../components/SaveLoad';
import { Badge, Callout, Card, ErrorBox, Field, Kpi, NumberField, PageHeader, Skeleton, Tabs } from '../components/ui';
import { api } from '../lib/api';
import { downloadFile, fmtMoney, fmtPct, isNum, toCSV } from '../lib/format';
import { loadRaw, save } from '../lib/storage';
import { useAsync, useDebounced } from '../lib/useApi';

type Tab = 'form' | 'individual' | 'entity' | 'dates' | 'file';
type N = number | null;
const inr = (v: N | undefined) => fmtMoney(v ?? null, 'INR');

interface Excl { form: string; why: string[] }
interface ItrRes { form: string; name: string; reasons: string[]; simpler_forms_excluded: Excl[]; due_date_category: string; source: string; note: string }
interface SpecialRow { income: number; exemption_used: number; rate: number; tax: number; exempt_1_25_lakh?: number }
interface Regime {
  regime: 'new' | 'old'; standard_deduction: number; gross_slab_income: number; deductions: Record<string, number>; deductions_allowed: number;
  slab_income: number; special_income: number; total_income: number; slab_rows: { from: number; to: number | null; amount: number; rate: number; tax: number }[];
  slab_tax: number; special_rate_tax: Record<string, SpecialRow>; rebate_87a: number; tax_after_rebate: number; surcharge_rate: number; surcharge: number;
  marginal_relief: number; cess: number; total_tax: number; tds_and_advance_tax: number; balance: number; effective_rate: number | null; notes: string[];
}
interface IndRes { new: Regime; old: Regime; better_regime: 'new' | 'old'; saving: number; rebate_note: string; notes: string[]; sources: Record<string, string> }
interface EntOpt { code: string; label: string; tax: number; surcharge_rate: number; surcharge: number; marginal_relief: number; cess: number; total_tax: number; effective_rate: number | null; mat_credit?: number }
interface EntRes { options: EntOpt[]; lowest: string; notes: string[]; source: string }
interface DueRes {
  due_dates: { category: string; label: string; due_date: string; statutory_due_date: string }[]; belated_return_last_date: string; revised_return_last_date: string;
  updated_return: string; notes: string[]; sources: Record<string, string>;
  late_filing?: { due_date: string; late: boolean; fee_234f: number; interest_234a: number; interest_months: number; allowed: boolean; message: string };
}
interface Info { year: { financial_year: string; assessment_year: string; law: string }; sources: Record<string, string>; filing_steps: string[]; filing_note: string }

const PROFILE = {
  taxpayer_type: 'individual', residential_status: 'resident', total_income: 900000 as N, salary_or_pension: true, house_properties: 1 as N,
  business_income: false, presumptive: 'none', partner_remuneration: false, stcg: false, ltcg_112a: 0 as N, other_capital_gains: false,
  agricultural_income: 0 as N, director: false, unlisted_equity: false, foreign_assets_or_income: false, tds_194n: false, esop_tax_deferred: false,
  losses_to_carry_forward: false, files_under_139_4a_to_4d: false, claims_section_11: false,
};
const INCOME = {
  taxpayer_type: 'individual', age: 'below_60', resident: true, salary: 1500000 as N, house_property: 0 as N, business: 0 as N, other_sources: 50000 as N,
  stcg_111a: 0 as N, ltcg_112a: 0 as N, ltcg_112: 0 as N, winnings_115bb: 0 as N, employer_nps_80ccd2: 0 as N, tds_and_advance_tax: 0 as N,
  count_special_income_for_rebate: true,
  deductions_old: { '80C': 150000 as N, '80CCD(1B)': 0 as N, '80D': 25000 as N, '80TTA': 10000 as N, '80TTB': 0 as N, '80G': 0 as N, other: 0 as N } as Record<string, N>,
};
const ENTITY = { entity: 'company', total_income: 50000000 as N, turnover_fy_2023_24: 1500000000 as N, book_profit: null as N, total_income_115baa: null as N,
  manufacturing_115bab_eligible: false, adjusted_total_income_amt: null as N };
type Model = { profile: typeof PROFILE; income: typeof INCOME; entity: typeof ENTITY };
const EXAMPLE: Model = { profile: PROFILE, income: INCOME, entity: ENTITY };

function Select<T extends string>({ label, value, onChange, options }: { label: string; value: T; onChange: (v: T) => void; options: [T, string][] }) {
  return (
    <Field label={label}>
      <select className="input" value={value} onChange={(e) => onChange(e.target.value as T)}>
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </Field>
  );
}
function Check({ label, checked, onChange }: { label: ReactNode; checked: boolean; onChange: (v: boolean) => void }) {
  return <label className="row" style={{ gap: 8, fontSize: 13 }}><input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />{label}</label>;
}
function useCalc<T>(path: string, body: unknown) {
  const req = useDebounced(body, 300);
  return useAsync(() => api.post<T>(path, req), [JSON.stringify(req)], !!req);
}
const numbersOnly = (o: Record<string, unknown>) => Object.fromEntries(Object.entries(o).map(([k, v]) => [k, v === null ? 0 : v]));

export function IncomeTax() {
  const [tab, setTab] = useState<Tab>(() => loadRaw('fis.itax.tab', 'form'));
  const [state, setState] = useState<{ m: Model; example: boolean }>(() => loadRaw('fis.itax', { m: EXAMPLE, example: true }));
  const m = state.m;
  const set = (p: Partial<Model>) => { const s = { m: { ...m, ...p }, example: false }; setState(s); save('fis.itax', s); };
  const info = useAsync(() => api.get<Info>('/api/tax/info'), []);
  return (
    <div className="page">
      <PageHeader title="Income Tax" badge={state.example ? <Badge tone="sample">Example figures</Badge> : <Badge tone="accent">Your figures</Badge>}
        subtitle={<>Which ITR form to file, old vs new regime, firm and company tax, due dates and late fees for <b>FY 2025-26 (AY 2026-27)</b> under the Income-tax Act, 1961 — each rule linked to the official page it comes from.</>}
        actions={<>
          <SaveLoad kind="income_tax" label="tax computation" getData={() => m} onLoad={(d: Model) => { const s = { m: { ...EXAMPLE, ...d }, example: false }; setState(s); save('fis.itax', s); }} />
          <button className="btn" onClick={() => { setState({ m: EXAMPLE, example: true }); save('fis.itax', { m: EXAMPLE, example: true }); }}>Example</button>
        </>} />
      <Callout tone="info" title="Prepares the return; does not file it">
        Only e-Return Intermediaries registered with the Income Tax Department may submit returns through its systems. Use these figures on the
        {' '}<a href="https://www.incometax.gov.in/iec/foportal/" target="_blank" rel="noreferrer">e-filing portal</a> or in the official offline utility. Always check against Form 26AS / AIS.
      </Callout>
      <div className="mt">
        <Tabs label="Section" value={tab} onChange={(t) => { setTab(t); save('fis.itax.tab', t); }} options={[
          { value: 'form', label: 'Which ITR form' }, { value: 'individual', label: 'Individual / HUF tax' }, { value: 'entity', label: 'Firm & company tax' },
          { value: 'dates', label: 'Due dates & late fee' }, { value: 'file', label: 'How to file' }]} />
      </div>
      <div className="mt">
        {tab === 'form' && <ItrForm m={m} set={set} />}
        {tab === 'individual' && <Individual m={m} set={set} />}
        {tab === 'entity' && <Entity m={m} set={set} />}
        {tab === 'dates' && <DueDates />}
        {tab === 'file' && <HowToFile info={info.data} />}
      </div>
    </div>
  );
}

function ItrForm({ m, set }: { m: Model; set: (p: Partial<Model>) => void }) {
  const p = m.profile;
  const up = (x: Partial<typeof PROFILE>) => set({ profile: { ...p, ...x } });
  const r = useCalc<ItrRes>('/api/tax/itr-form', numbersOnly(p));
  const person = p.taxpayer_type === 'individual' || p.taxpayer_type === 'huf';
  return (
    <div className="grid cols-2">
      <Card title="Taxpayer" subtitle="Answer for the financial year 2025-26">
        <div className="grid cols-2" style={{ gap: 10 }}>
          <Select label="Taxpayer type" value={p.taxpayer_type} onChange={(v) => up({ taxpayer_type: v })} options={[['individual', 'Individual'], ['huf', 'HUF'], ['firm', 'Partnership firm'], ['llp', 'LLP'], ['company', 'Company'], ['aop_boi', 'AOP / BOI'], ['cooperative', 'Co-operative society'], ['local_authority', 'Local authority'], ['trust_or_institution', 'Trust / institution / political party']]} />
          <Select label="Residential status" value={p.residential_status} onChange={(v) => up({ residential_status: v })} options={[['resident', 'Resident (ordinarily)'], ['rnor', 'Resident but not ordinarily resident'], ['non_resident', 'Non-resident']]} />
          <NumberField label="Total income (₹)" value={p.total_income} onChange={(v) => up({ total_income: v })} />
          <NumberField label="Number of house properties" value={p.house_properties} onChange={(v) => up({ house_properties: v })} />
          <NumberField label="LTCG under 112A (₹)" value={p.ltcg_112a} onChange={(v) => up({ ltcg_112a: v })} />
          <NumberField label="Agricultural income (₹)" value={p.agricultural_income} onChange={(v) => up({ agricultural_income: v })} />
          {p.business_income && person && <Select label="Business income computed under" value={p.presumptive} onChange={(v) => up({ presumptive: v })} options={[['none', 'Regular books (not presumptive)'], ['44AD', '44AD (business)'], ['44ADA', '44ADA (profession)'], ['44AE', '44AE (goods carriages)']]} />}
          {p.taxpayer_type === 'firm' && <Select label="Firm income computed under" value={p.presumptive} onChange={(v) => up({ presumptive: v, business_income: v !== 'none' })} options={[['none', 'Regular books'], ['44AD', '44AD'], ['44ADA', '44ADA'], ['44AE', '44AE']]} />}
        </div>
        <div className="stack mt" style={{ gap: 6 }}>
          {person && <>
            <Check label="Salary or pension" checked={p.salary_or_pension} onChange={(v) => up({ salary_or_pension: v })} />
            <Check label="Income from business or profession" checked={p.business_income} onChange={(v) => up({ business_income: v })} />
            <Check label="Interest, salary, bonus or commission from a partnership firm" checked={p.partner_remuneration} onChange={(v) => up({ partner_remuneration: v })} />
            <Check label="Short-term capital gains" checked={p.stcg} onChange={(v) => up({ stcg: v })} />
            <Check label="Other capital gains (property, debt funds, unlisted shares…)" checked={p.other_capital_gains} onChange={(v) => up({ other_capital_gains: v })} />
            <Check label="Director of a company" checked={p.director} onChange={(v) => up({ director: v })} />
            <Check label="Held unlisted equity shares during the year" checked={p.unlisted_equity} onChange={(v) => up({ unlisted_equity: v })} />
            <Check label="Foreign assets, foreign income or signing authority abroad" checked={p.foreign_assets_or_income} onChange={(v) => up({ foreign_assets_or_income: v })} />
            <Check label="TDS under 194N (cash withdrawals)" checked={p.tds_194n} onChange={(v) => up({ tds_194n: v })} />
            <Check label="Tax on ESOPs deferred" checked={p.esop_tax_deferred} onChange={(v) => up({ esop_tax_deferred: v })} />
            <Check label="Losses to carry forward or brought-forward losses" checked={p.losses_to_carry_forward} onChange={(v) => up({ losses_to_carry_forward: v })} />
          </>}
          {p.taxpayer_type === 'company' && <Check label="Claims exemption under section 11 (charitable company)" checked={p.claims_section_11} onChange={(v) => up({ claims_section_11: v })} />}
          <Check label="Must file under section 139(4A)–(4D) (trust, political party, research body, university)" checked={p.files_under_139_4a_to_4d} onChange={(v) => up({ files_under_139_4a_to_4d: v })} />
        </div>
      </Card>
      <Card title="Form to file" subtitle="Assessment year 2026-27">
        {r.error ? <ErrorBox error={r.error} /> : !r.data ? <Skeleton h={120} /> : (
          <div className="stack">
            <div className="row" style={{ gap: 14 }}>
              <div className="icon-ring" style={{ width: 52, height: 52, borderRadius: 16, display: 'grid', placeItems: 'center', background: 'var(--accent-soft)', color: 'var(--accent-strong)' }}><FileCheck2 size={26} /></div>
              <div><div style={{ fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 800 }}>{r.data.name}</div>
                <div className="muted" style={{ fontSize: 13 }}>Due date category: {DUE_LABEL[r.data.due_date_category]}</div></div>
            </div>
            <ul style={{ margin: 0, paddingLeft: 18 }}>{r.data.reasons.map((x) => <li key={x}>{x}</li>)}</ul>
            {r.data.simpler_forms_excluded.map((e) => (
              <Callout key={e.form} tone="warn" title={`Why not ${e.form}`}><ul>{e.why.map((w) => <li key={w}>{w}</li>)}</ul></Callout>
            ))}
            <div className="faint" style={{ fontSize: 12 }}>{r.data.note} <a href={r.data.source} target="_blank" rel="noreferrer">Official rules <ExternalLink size={11} /></a></div>
          </div>
        )}
      </Card>
    </div>
  );
}
const DUE_LABEL: Record<string, string> = { no_business: '31 July 2026 (no business income, no audit)', business_no_audit: '31 August 2026 (business, no audit)', audit: '21 November 2026 (audit cases, extended)', transfer_pricing: '30 November 2026 (transfer pricing)' };

function Row({ label, n, o, strong, hint }: { label: ReactNode; n: ReactNode; o: ReactNode; strong?: boolean; hint?: string }) {
  return <tr style={strong ? { fontWeight: 700 } : undefined} title={hint}><td>{label}</td><td className="r">{n}</td><td className="r">{o}</td></tr>;
}

function Individual({ m, set }: { m: Model; set: (p: Partial<Model>) => void }) {
  const x = m.income;
  const up = (p: Partial<typeof INCOME>) => set({ income: { ...x, ...p } });
  const body = { ...numbersOnly({ ...x, deductions_old: undefined }), deductions_old: Object.fromEntries(Object.entries(x.deductions_old).filter(([, v]) => isNum(v) && v > 0)) };
  const r = useCalc<IndRes>('/api/tax/individual', body);
  const num = (k: keyof typeof INCOME, label: string, hint?: string) => <NumberField label={label} hint={hint} value={x[k] as N} onChange={(v) => up({ [k]: v } as Partial<typeof INCOME>)} />;
  const exportCsv = () => {
    if (!r.data) return;
    const { new: a, old: b } = r.data;
    const rows: unknown[][] = [['Item', 'New regime', 'Old regime'], ['Gross income at slab rates', a.gross_slab_income, b.gross_slab_income], ['Standard deduction', a.standard_deduction, b.standard_deduction],
      ['Deductions allowed', a.deductions_allowed, b.deductions_allowed], ['Income at slab rates', a.slab_income, b.slab_income], ['Special-rate income', a.special_income, b.special_income],
      ['Total income (rounded)', a.total_income, b.total_income], ['Tax at slab rates', a.slab_tax, b.slab_tax],
      ['Tax at special rates', Object.values(a.special_rate_tax).reduce((s, t) => s + t.tax, 0), Object.values(b.special_rate_tax).reduce((s, t) => s + t.tax, 0)],
      ['Rebate 87A', a.rebate_87a, b.rebate_87a], ['Surcharge', a.surcharge, b.surcharge], ['Marginal relief', a.marginal_relief, b.marginal_relief], ['Cess 4%', a.cess, b.cess],
      ['Total tax', a.total_tax, b.total_tax], ['TDS and advance tax', a.tds_and_advance_tax, b.tds_and_advance_tax], ['Balance payable (refund if negative)', a.balance, b.balance]];
    downloadFile('income-tax-computation-AY2026-27.csv', toCSV(rows));
  };
  return (
    <div className="stack">
      <div className="grid cols-2">
        <Card title="Income" subtitle="Amounts for FY 2025-26 in rupees. Leave blank for none.">
          <div className="grid cols-2" style={{ gap: 10 }}>
            <Select label="Taxpayer" value={x.taxpayer_type} onChange={(v) => up({ taxpayer_type: v })} options={[['individual', 'Individual'], ['huf', 'HUF']]} />
            <Select label="Age" value={x.age} onChange={(v) => up({ age: v })} options={[['below_60', 'Below 60'], ['60_to_79', '60 to 79 (senior)'], ['80_plus', '80 or more (super senior)']]} />
            {num('salary', 'Salary / pension (after exempt allowances)')}
            {num('house_property', 'House property (net; loss as negative)', 'After 30% standard deduction and interest')}
            {num('business', 'Business / profession')}
            {num('other_sources', 'Other sources (interest, dividends…)')}
            {num('stcg_111a', 'Short-term gains on listed equity (111A)')}
            {num('ltcg_112a', 'Long-term gains on listed equity (112A)', 'Before the ₹1.25 lakh exemption')}
            {num('ltcg_112', 'Other long-term gains (112)', 'At 12.5% without indexation')}
            {num('winnings_115bb', 'Lottery / online game winnings (115BB)')}
            {num('employer_nps_80ccd2', "Employer's NPS contribution (80CCD(2))")}
            {num('tds_and_advance_tax', 'TDS, TCS and advance tax paid')}
          </div>
          <div className="stack mt-sm" style={{ gap: 6 }}>
            <Check label="Resident in India" checked={x.resident} onChange={(v) => up({ resident: v })} />
            <Check label="Count capital gains towards the ₹12 lakh rebate limit (cautious reading)" checked={x.count_special_income_for_rebate} onChange={(v) => up({ count_special_income_for_rebate: v })} />
          </div>
        </Card>
        <Card title="Deductions (old regime only)" subtitle="Enter the eligible amount; limits are applied automatically">
          <div className="grid cols-2" style={{ gap: 10 }}>
            {Object.entries({ '80C': '80C (PF, ELSS, LIC… max 1.5 lakh)', '80CCD(1B)': '80CCD(1B) NPS (max 50,000)', '80D': '80D health insurance', '80TTA': '80TTA savings interest (max 10,000)', '80TTB': '80TTB senior interest (max 50,000)', '80G': '80G donations (eligible amount)', other: 'Other Chapter VI-A' }).map(([k, label]) => (
              <NumberField key={k} label={label} value={x.deductions_old[k] ?? null} onChange={(v) => up({ deductions_old: { ...x.deductions_old, [k]: v } })} />
            ))}
          </div>
          <p className="faint mt-sm" style={{ fontSize: 12 }}>The new regime allows only a few deductions (such as 80CCD(2)); these are ignored there.</p>
        </Card>
      </div>
      {r.error ? <ErrorBox error={r.error} /> : !r.data ? <Skeleton h={200} /> : <IndResult d={r.data} onExport={exportCsv} />}
    </div>
  );
}

function IndResult({ d, onExport }: { d: IndRes; onExport: () => void }) {
  const a = d.new, b = d.old;
  const sp = (g: Regime) => Object.values(g.special_rate_tax).reduce((s, t) => s + t.tax, 0);
  return (
    <>
      <div className="grid cols-4">
        <Kpi label="Tax under the new regime" value={inr(a.total_tax)} delta={d.better_regime === 'new' ? 'Lower' : undefined} deltaTone="pos" />
        <Kpi label="Tax under the old regime" value={inr(b.total_tax)} delta={d.better_regime === 'old' ? 'Lower' : undefined} deltaTone="pos" />
        <Kpi label="Better regime" value={d.better_regime === 'new' ? 'New regime' : 'Old regime'} delta={`Saves ${inr(d.saving)}`} deltaTone="pos" />
        <Kpi label={`Balance payable (${d.better_regime})`} value={inr(d[d.better_regime].balance)} delta={d[d.better_regime].balance < 0 ? 'Refund due' : undefined} deltaTone="pos" />
      </div>
      <Card title="Computation" subtitle="Side by side, with the sections applied" actions={<button className="btn sm" onClick={onExport}><Download size={14} />CSV</button>}>
        <div className="table-wrap">
          <table className="data">
            <thead><tr><th>Item</th><th className="r">New regime (115BAC)</th><th className="r">Old regime</th></tr></thead>
            <tbody>
              <Row label="Gross income taxed at slab rates" n={inr(a.gross_slab_income)} o={inr(b.gross_slab_income)} />
              <Row label="Standard deduction (salary)" n={inr(a.standard_deduction)} o={inr(b.standard_deduction)} />
              <Row label="Chapter VI-A deductions allowed" n={inr(a.deductions_allowed)} o={inr(b.deductions_allowed)} />
              <Row label="Income at slab rates" n={inr(a.slab_income)} o={inr(b.slab_income)} />
              <Row label="Income at special rates (111A, 112, 112A, 115BB)" n={inr(a.special_income)} o={inr(b.special_income)} />
              <Row label="Total income (rounded, s.288A)" n={inr(a.total_income)} o={inr(b.total_income)} strong />
              <Row label="Tax at slab rates" n={inr(a.slab_tax)} o={inr(b.slab_tax)} />
              <Row label="Tax at special rates" n={inr(sp(a))} o={inr(sp(b))} />
              <Row label="Rebate under section 87A" n={`− ${inr(a.rebate_87a)}`} o={`− ${inr(b.rebate_87a)}`} />
              <Row label="Surcharge" n={`${inr(a.surcharge)} (${fmtPct(a.surcharge_rate, 0)})`} o={`${inr(b.surcharge)} (${fmtPct(b.surcharge_rate, 0)})`} />
              {(a.marginal_relief > 0 || b.marginal_relief > 0) && <Row label="of which marginal relief" n={inr(a.marginal_relief)} o={inr(b.marginal_relief)} />}
              <Row label="Health & education cess (4%)" n={inr(a.cess)} o={inr(b.cess)} />
              <Row label="Total tax (rounded, s.288B)" n={inr(a.total_tax)} o={inr(b.total_tax)} strong />
              <Row label="Less: TDS, TCS and advance tax" n={inr(a.tds_and_advance_tax)} o={inr(b.tds_and_advance_tax)} />
              <Row label="Balance payable / (refund)" n={inr(a.balance)} o={inr(b.balance)} strong />
              <Row label="Effective rate on total income" n={fmtPct(a.effective_rate, 2)} o={fmtPct(b.effective_rate, 2)} />
            </tbody>
          </table>
        </div>
      </Card>
      <div className="grid cols-2">
        {[a, b].map((g) => (
          <Card key={g.regime} title={`${g.regime === 'new' ? 'New' : 'Old'} regime: slab working`}>
            <div className="table-wrap"><table className="data">
              <thead><tr><th>Slab</th><th className="r">Income</th><th className="r">Rate</th><th className="r">Tax</th></tr></thead>
              <tbody>{g.slab_rows.map((s) => <tr key={s.from}><td>{inr(s.from)} – {s.to === null ? 'above' : inr(s.to)}</td><td className="r">{inr(s.amount)}</td><td className="r">{fmtPct(s.rate, 0)}</td><td className="r">{inr(s.tax)}</td></tr>)}
                {Object.entries(g.special_rate_tax).filter(([, t]) => t.income > 0).map(([sec, t]) => (
                  <tr key={sec}><td>Section {sec}{t.exemption_used > 0 ? ` (exemption used ${inr(t.exemption_used)})` : ''}{t.exempt_1_25_lakh ? ` (₹1.25 lakh exempt)` : ''}</td><td className="r">{inr(t.income)}</td><td className="r">{fmtPct(t.rate, 1)}</td><td className="r">{inr(t.tax)}</td></tr>))}
              </tbody></table></div>
            {g.notes.length > 0 && <ul className="faint mt-sm" style={{ fontSize: 12, paddingLeft: 18 }}>{g.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
          </Card>
        ))}
      </div>
      <Callout tone="info" title="Points to note"><ul><li>{d.rebate_note}</li>{d.notes.map((n) => <li key={n}>{n}</li>)}</ul>
        <div className="mt-sm" style={{ fontSize: 12 }}>Sources: {Object.entries(d.sources).map(([k, u]) => <a key={k} href={u} target="_blank" rel="noreferrer" style={{ marginRight: 10 }}>{k.replace('_', ' ')} <ExternalLink size={11} /></a>)}</div></Callout>
    </>
  );
}

function Entity({ m, set }: { m: Model; set: (p: Partial<Model>) => void }) {
  const e = m.entity;
  const up = (p: Partial<typeof ENTITY>) => set({ entity: { ...e, ...p } });
  const body = { ...e, total_income: e.total_income ?? 0 };
  const r = useCalc<EntRes>('/api/tax/entity', body);
  return (
    <div className="grid cols-2">
      <Card title="Entity" subtitle="Domestic company, partnership firm, LLP or co-operative society">
        <div className="grid cols-2" style={{ gap: 10 }}>
          <Select label="Entity" value={e.entity} onChange={(v) => up({ entity: v })} options={[['company', 'Domestic company'], ['firm', 'Partnership firm'], ['llp', 'LLP'], ['cooperative', 'Co-operative society']]} />
          <NumberField label="Total income (₹)" value={e.total_income} onChange={(v) => up({ total_income: v })} />
          {e.entity === 'company' && <>
            <NumberField label="Turnover / gross receipts FY 2023-24 (₹)" hint="₹400 crore or less → 25%, else 30%" value={e.turnover_fy_2023_24} onChange={(v) => up({ turnover_fy_2023_24: v })} />
            <NumberField label="Book profit for MAT (₹, optional)" value={e.book_profit} onChange={(v) => up({ book_profit: v })} />
            <NumberField label="Total income under 115BAA (₹, if different)" hint="Without the deductions 115BAA disallows" value={e.total_income_115baa} onChange={(v) => up({ total_income_115baa: v })} />
          </>}
          {e.entity === 'cooperative' && <NumberField label="Adjusted total income for AMT (₹, optional)" value={e.adjusted_total_income_amt} onChange={(v) => up({ adjusted_total_income_amt: v })} />}
        </div>
        {e.entity === 'company' && <div className="mt-sm"><Check label="New manufacturing company eligible for 115BAB" checked={e.manufacturing_115bab_eligible} onChange={(v) => up({ manufacturing_115bab_eligible: v })} /></div>}
      </Card>
      <Card title="Tax by option" subtitle="Lowest option highlighted">
        {r.error ? <ErrorBox error={r.error} /> : !r.data ? <Skeleton h={120} /> : (
          <>
            <div className="table-wrap"><table className="data">
              <thead><tr><th>Option</th><th className="r">Tax</th><th className="r">Surcharge</th><th className="r">Cess</th><th className="r">Total</th><th className="r">Effective</th></tr></thead>
              <tbody>{r.data.options.map((o) => (
                <tr key={o.code} style={o.code === r.data!.lowest ? { background: 'var(--accent-soft)', fontWeight: 650 } : undefined}>
                  <td style={{ whiteSpace: 'normal', minWidth: 180 }}>{o.label}{o.mat_credit ? <div className="faint" style={{ fontSize: 11.5 }}>MAT credit {inr(o.mat_credit)}</div> : null}</td>
                  <td className="r">{inr(o.tax)}</td><td className="r">{inr(o.surcharge)}{o.marginal_relief > 0 ? <div className="faint" style={{ fontSize: 11 }}>after relief {inr(o.marginal_relief)}</div> : null}</td>
                  <td className="r">{inr(o.cess)}</td><td className="r">{inr(o.total_tax)}</td><td className="r">{fmtPct(o.effective_rate, 2)}</td>
                </tr>))}</tbody></table></div>
            {r.data.notes.length > 0 && <ul className="faint mt-sm" style={{ fontSize: 12, paddingLeft: 18 }}>{r.data.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
          </>
        )}
      </Card>
    </div>
  );
}

function DueDates() {
  const [q, setQ] = useState<{ category: string; filing_date: string; total_income: N; tax_unpaid: N }>(() => loadRaw('fis.itax.due', { category: 'no_business', filing_date: '', total_income: null, tax_unpaid: null }));
  const upd = (p: Partial<typeof q>) => { const s = { ...q, ...p }; setQ(s); save('fis.itax.due', s); };
  const body = q.filing_date ? { category: q.category, filing_date: q.filing_date, total_income: q.total_income ?? 0, tax_unpaid: q.tax_unpaid } : {};
  const r = useCalc<DueRes>('/api/tax/due-dates', body);
  return (
    <div className="grid cols-2">
      <Card title="Due dates for AY 2026-27" subtitle="Returns of income for FY 2025-26">
        {r.error ? <ErrorBox error={r.error} /> : !r.data ? <Skeleton h={120} /> : (
          <>
            <div className="table-wrap"><table className="data">
              <thead><tr><th>Who</th><th>Due date</th></tr></thead>
              <tbody>{r.data.due_dates.map((d) => <tr key={d.category}><td style={{ whiteSpace: 'normal' }}>{d.label}</td><td>{fmtDate(d.due_date)}{d.statutory_due_date !== d.due_date && <div className="faint" style={{ fontSize: 11 }}>statutory {fmtDate(d.statutory_due_date)}</div>}</td></tr>)}
                <tr><td>Belated return (139(4))</td><td>{fmtDate(r.data.belated_return_last_date)}</td></tr>
                <tr><td>Revised return (139(5))</td><td>{fmtDate(r.data.revised_return_last_date)}</td></tr></tbody></table></div>
            <ul className="faint mt-sm" style={{ fontSize: 12, paddingLeft: 18 }}><li>{r.data.updated_return}</li>{r.data.notes.map((n) => <li key={n}>{n}</li>)}</ul>
          </>
        )}
      </Card>
      <Card title="Late filing: fee and interest" subtitle="Section 234F fee and 234A interest (1% a month or part)">
        <div className="grid cols-2" style={{ gap: 10 }}>
          <Select label="Category" value={q.category} onChange={(v) => upd({ category: v })} options={[['no_business', 'No business income'], ['business_no_audit', 'Business, no audit'], ['audit', 'Audit case'], ['transfer_pricing', 'Transfer pricing']]} />
          <Field label="Date of filing"><input className="input" type="date" value={q.filing_date} onChange={(e) => upd({ filing_date: e.target.value })} /></Field>
          <NumberField label="Total income (₹)" value={q.total_income} onChange={(v) => upd({ total_income: v })} />
          <NumberField label="Tax unpaid on the due date (₹)" value={q.tax_unpaid} onChange={(v) => upd({ tax_unpaid: v })} />
        </div>
        {r.data?.late_filing ? (
          <div className="mt">
            <Callout tone={r.data.late_filing.late ? (r.data.late_filing.allowed ? 'warn' : 'error') : 'success'} title={r.data.late_filing.message}>
              {r.data.late_filing.late && <div className="grid cols-2 mt-sm"><Kpi label="Late fee (234F)" value={inr(r.data.late_filing.fee_234f)} /><Kpi label={`Interest (234A, ${r.data.late_filing.interest_months} months)`} value={inr(r.data.late_filing.interest_234a)} /></div>}
            </Callout>
          </div>
        ) : <p className="faint mt">Choose a filing date to see the fee and interest.</p>}
      </Card>
    </div>
  );
}
const fmtDate = (s: string) => new Date(s + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });

function HowToFile({ info }: { info: Info | null }) {
  return (
    <div className="grid cols-2">
      <Card title="Filing the return" subtitle="On the Income Tax Department's portal">
        <ol style={{ paddingLeft: 18, display: 'grid', gap: 8, margin: 0 }}>{(info?.filing_steps ?? []).map((s) => <li key={s}>{s}</li>)}</ol>
        <div className="row mt">
          <a className="btn primary" href="https://www.incometax.gov.in/iec/foportal/" target="_blank" rel="noreferrer"><Landmark size={15} />Open the e-filing portal</a>
          <a className="btn" href="https://www.incometax.gov.in/iec/foportal/downloads" target="_blank" rel="noreferrer"><Download size={15} />Offline utility & schemas</a>
        </div>
      </Card>
      <Card title="Why the app cannot press 'Submit' for you">
        <p>{info?.filing_note}</p>
        <p className="mt-sm">A software company can become a <b>Type 2 e-Return Intermediary</b> to file through the department's APIs, with each taxpayer's consent and OTP. That needs registration with the department, which this app does not have.</p>
        <p className="mt-sm faint" style={{ fontSize: 12 }}><CalendarClock size={12} /> {info ? `${info.year.law}; financial year ${info.year.financial_year}, assessment year ${info.year.assessment_year}. Income from 1 April 2026 falls under the Income-tax Act, 2025 ("tax year 2026-27"), whose return forms are not yet notified.` : ''}</p>
        <a href="https://www.incometax.gov.in/iec/foportal/help/eri/registration" target="_blank" rel="noreferrer">About e-Return Intermediaries <ExternalLink size={11} /></a>
      </Card>
    </div>
  );
}
