import { ClipboardCheck, Download, FileUp, Loader2 } from 'lucide-react';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { api, downloadPost, uploadWithProgress } from '../lib/api';
import { fmtMoney } from '../lib/format';
import { useProjects } from '../lib/project';
import { loadRaw, save } from '../lib/storage';
import { useToast } from '../lib/toast';
import type { UploadSummary } from '../lib/types';
import { useAsync, useDebounced } from '../lib/useApi';
import { Badge, Callout, Card, Disclosure, ErrorBox, Field, NumberField, Skeleton } from './ui';

type N = number | null;
interface Test { clause: string; rule: string; working: string; result: boolean | null; source: string }
interface CalcRow { metric: string; formula: string; substituted: string; result: string; source: string }
interface Clause {
  no: string; part: 'A' | 'B'; title: string; status: 'filled' | 'review' | 'needs_input' | 'not_applicable' | 'omitted';
  answer: string | null; rows: CalcRow[]; evidence: { file: string; where: string; text?: string }[]; needed: string; note: string | null;
}
interface AuditRes {
  applicability: { required: boolean | null; clauses: string[]; tests: Test[]; missing: string[]; form: string | null; forms: string | null;
    form_reason: string | null; max_not_chargeable: number; penalty_271b: number | null; penalty_note: string };
  due: { report_due: string; itr_due: string; report_overdue: boolean; message: string; source: string };
  inputs_from_files: { field: string; value: number; source: string }[];
  documents: { upload_id: string; file: string; used_for: string[]; notes: string[] }[];
  ledgers: { file: string; rows: number; sheet: string; direction_rule: string; mode_source: string | null; contra_excluded: number }[];
  report_3cb: { title: string; applies: boolean; note: string; paragraphs: string[]; auditor_fields: string[]; auditor_note: string };
  clauses: Clause[]; counts: Record<string, number>; status_labels: Record<string, string>; sources: Record<string, string>; notes: string[];
}

const Q = {
  taxpayer_type: 'firm', activity: 'business', presumptive: 'none', profit_below_presumptive: false, opted_out_of_44ad: false,
  business_turnover: null as N, professional_receipts: null as N, total_income: null as N,
  cash_receipts: null as N, total_receipts: null as N, cash_payments: null as N, total_payments: null as N,
  regime: 'new', age: 'below_60', resident: true, audited_under_other_law: null as boolean | null,
  name: '', address: '', pan: '', gstin: '', nature: '',
};
type QT = typeof Q;
const FIELD: Record<string, string> = {
  business_turnover: 'Business turnover', professional_receipts: 'Professional receipts', total_income: 'Total income',
  cash_receipts: 'Cash receipts', total_receipts: 'Total receipts', cash_payments: 'Cash payments', total_payments: 'Total payments',
};
const TONE: Record<Clause['status'], 'pos' | 'warn' | 'neg' | 'info' | undefined> = { filled: 'pos', review: 'warn', needs_input: 'neg', not_applicable: undefined, omitted: undefined };
const ACCEPT = '.xlsx,.xlsm,.csv,.tsv,.txt,.pdf,.docx';
const inr = (v: N | undefined) => fmtMoney(v ?? null, 'INR');
const fmtDate = (s: string) => new Date(s + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });

function Sel({ label, value, onChange, options }: { label: ReactNode; value: string; onChange: (v: string) => void; options: [string, string][] }) {
  return <Field label={label}><select className="input" value={value} onChange={(e) => onChange(e.target.value)}>{options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>;
}
function Text({ label, value, onChange, placeholder, max }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string; max?: number }) {
  return <Field label={label}><input className="input" value={value} maxLength={max} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} /></Field>;
}
const Tick = ({ label, checked, onChange }: { label: ReactNode; checked: boolean; onChange: (v: boolean) => void }) =>
  <label className="row" style={{ gap: 8, fontSize: 13, alignItems: 'flex-start' }}><input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} style={{ marginTop: 3 }} />{label}</label>;

/** Tax audit (s.44AB): applicability, Form 3CB wording and a Form 3CD draft filled from the user's books.
 * Recomputed on every change, so uploading a P&L or cash book fills the clauses at once. */
export function TaxAudit() {
  const toast = useToast();
  const { activeId } = useProjects();
  const inputRef = useRef<HTMLInputElement>(null);
  const [q, setQ] = useState<QT>(() => ({ ...Q, ...loadRaw('fis.itax.audit', {}) }));
  const [picked, setPicked] = useState<string[]>(() => loadRaw('fis.itax.audit.files', []));
  const [busy, setBusy] = useState<string | null>(null);
  const [filter, setFilter] = useState<'all' | Clause['status']>('all');
  const uploads = useAsync((signal) => api.get<{ uploads: UploadSummary[] }>('/api/uploads', { signal }), []);
  const upd = (p: Partial<QT>) => { const s = { ...q, ...p }; setQ(s); save('fis.itax.audit', s); };
  const pick = (ids: string[]) => { setPicked(ids); save('fis.itax.audit.files', ids); };

  const panOk = !q.pan || /^[A-Za-z]{5}\d{4}[A-Za-z]$/.test(q.pan);
  const gstinOk = !q.gstin || /^\d{2}[A-Za-z]{5}\d{4}[A-Za-z][0-9A-Za-z][Zz][0-9A-Za-z]$/.test(q.gstin);
  const body = { ...q, pan: panOk ? q.pan : '', gstin: gstinOk ? q.gstin : '', upload_ids: picked };
  const req = useDebounced(body, 250);
  const r = useAsync((signal) => api.post<AuditRes>('/api/tax/audit', req, { signal }), [JSON.stringify(req)]);

  useEffect(() => { // forget picks of files that were deleted
    if (uploads.data) { const have = new Set(uploads.data.uploads.map((u) => u.id)); if (picked.some((p) => !have.has(p))) pick(picked.filter((p) => have.has(p))); }
  }, [uploads.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const send = async (files: File[]) => {
    const ids: string[] = [];
    for (const [i, file] of files.entries()) {
      setBusy(`Uploading ${file.name} (${i + 1} of ${files.length})…`);
      try {
        const res = await uploadWithProgress<{ results: ({ ok: true; upload: { id: string } } | { ok: false; error: string })[] }>('/api/uploads', [file], () => {}, { project_id: activeId });
        const x = res.results[0];
        if (x.ok) ids.push(x.upload.id); else toast(`${file.name}: ${x.error}`, 'error');
      } catch (e) { toast(`${file.name}: ${(e as Error).message}`, 'error'); }
    }
    setBusy(null);
    uploads.reload();
    if (ids.length) pick([...new Set([...picked, ...ids])].slice(-10));
  };

  const files = (uploads.data?.uploads ?? []).filter((u) => u.status === 'processed' && u.category !== 'code' && u.category !== 'archive').slice(0, 25);
  const d = r.data;
  const shown = d ? d.clauses.filter((c) => filter === 'all' || c.status === filter) : [];
  const download = async () => {
    try { await downloadPost('/api/tax/audit/draft.docx', body, 'tax-audit-draft-AY2026-27.docx'); } catch (e) { toast((e as Error).message, 'error'); }
  };

  return (
    <div className="stack">
      <Callout tone="info" title="A draft for your chartered accountant">
        Upload your P&amp;L, balance sheet and cash book or ledger. The app checks whether a tax audit is needed under section 44AB for FY 2025-26,
        and fills the Form 3CD clauses it can from your files, showing the working and the cell each figure came from. Only a CA in practice can sign
        the report and upload it with a UDIN, so the auditor's details are left blank.
      </Callout>

      <div className="grid cols-2" style={{ alignItems: 'start' }}>
        <Card title={<span className="row"><FileUp size={17} className="pos" />Your books</span>}
          subtitle="P&L and balance sheet (Excel/CSV), cash book or ledger with a payment-mode column. Read on this server only.">
          <div className="dropzone" role="button" tabIndex={0} aria-label="Upload books of account: drop here or press Enter to browse"
            onClick={() => inputRef.current?.click()}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); inputRef.current?.click(); } }}
            onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); send(Array.from(e.dataTransfer.files)); }}>
            <FileUp size={26} className="pos" />
            <div style={{ fontWeight: 650, marginTop: 6 }}>Drop files here or click to browse</div>
            <div className="faint" style={{ fontSize: 12, marginTop: 4 }}>Excel, CSV, PDF or Word · up to 10 files per draft</div>
            <input ref={inputRef} type="file" multiple accept={ACCEPT} hidden onChange={(e) => { send(Array.from(e.target.files ?? [])); e.target.value = ''; }} />
          </div>
          {busy && <div className="row faint mt-sm" style={{ fontSize: 13 }}><Loader2 size={15} className="spin" />{busy}</div>}
          <div className="field-label mt" style={{ marginBottom: 6 }}>Files used for this draft</div>
          {files.length ? (
            <div className="stack" style={{ gap: 4, maxHeight: 180, overflow: 'auto' }}>
              {files.map((u) => (
                <label key={u.id} className="row" style={{ gap: 8, fontSize: 13, minHeight: 32 }}>
                  <input type="checkbox" checked={picked.includes(u.id)} disabled={!picked.includes(u.id) && picked.length >= 10}
                    onChange={(e) => pick(e.target.checked ? [...picked, u.id] : picked.filter((x) => x !== u.id))} />
                  <span className="truncate">{u.name}</span>
                </label>
              ))}
            </div>
          ) : <p className="faint" style={{ fontSize: 13 }}>No files yet.</p>}
          <a className="btn mt-sm" href="/api/tax/audit/ledger-template" download><Download size={15} />Cash book template (CSV)</a>
        </Card>

        <Card title="About the assessee" subtitle="Figures you leave empty are taken from your files when they are there; nothing is assumed.">
          <div className="grid cols-2" style={{ gap: 10 }}>
            <Sel label="Taxpayer type" value={q.taxpayer_type} onChange={(v) => upd({ taxpayer_type: v })} options={[['individual', 'Individual'], ['huf', 'HUF'], ['firm', 'Partnership firm'], ['llp', 'LLP'], ['company', 'Company'], ['aop_boi', 'AOP / BOI'], ['cooperative', 'Co-operative society'], ['trust_or_institution', 'Trust / institution']]} />
            <Sel label="Business or profession" value={q.activity} onChange={(v) => upd({ activity: v })} options={[['business', 'Business'], ['profession', 'Profession'], ['both', 'Both']]} />
            {q.activity !== 'profession' && <NumberField label="Business turnover (₹)" value={q.business_turnover} onChange={(v) => upd({ business_turnover: v })} hint="Empty = from your P&L" />}
            {q.activity !== 'business' && <NumberField label="Professional receipts (₹)" value={q.professional_receipts} onChange={(v) => upd({ professional_receipts: v })} hint={q.activity === 'profession' ? 'Empty = from your P&L' : undefined} />}
            <Sel label="Presumptive scheme" value={q.presumptive} onChange={(v) => upd({ presumptive: v })} options={[['none', 'None (regular books)'], ['44AD', '44AD (business)'], ['44ADA', '44ADA (profession)'], ['44AE', '44AE (goods carriages)'], ['44BB', '44BB'], ['44BBB', '44BBB']]} />
            <NumberField label="Total income (₹)" value={q.total_income} onChange={(v) => upd({ total_income: v })} hint="Needed for 44ADA / 44AD(4) cases" />
          </div>
          <div className="stack mt-sm" style={{ gap: 6 }}>
            {q.presumptive !== 'none' && <Tick label={`Profit declared is lower than the ${q.presumptive} presumptive rate`} checked={q.profit_below_presumptive} onChange={(v) => upd({ profit_below_presumptive: v })} />}
            <Tick label="Left 44AD in one of the last five years after opting in (section 44AD(4))" checked={q.opted_out_of_44ad} onChange={(v) => upd({ opted_out_of_44ad: v })} />
            <Tick label="Accounts are audited under another law (e.g. the Companies Act) → Form 3CA" checked={q.audited_under_other_law ?? q.taxpayer_type === 'company'} onChange={(v) => upd({ audited_under_other_law: v })} />
          </div>
          <Disclosure title="Cash test figures (filled from your cash book when uploaded)">
            <div className="grid cols-2" style={{ gap: 10 }}>
              <NumberField label="Cash receipts (₹)" value={q.cash_receipts} onChange={(v) => upd({ cash_receipts: v })} />
              <NumberField label="Total receipts (₹)" value={q.total_receipts} onChange={(v) => upd({ total_receipts: v })} />
              <NumberField label="Cash payments (₹)" value={q.cash_payments} onChange={(v) => upd({ cash_payments: v })} />
              <NumberField label="Total payments (₹)" value={q.total_payments} onChange={(v) => upd({ total_payments: v })} />
            </div>
            <p className="faint mt-sm" style={{ fontSize: 12 }}>A cheque or draft that is not account-payee counts as cash.</p>
          </Disclosure>
          <Disclosure title="Name, PAN and GSTIN for Form 3CB / 3CD Part A">
            <div className="grid cols-2" style={{ gap: 10 }}>
              <Text label="Name of the assessee" value={q.name} max={200} onChange={(v) => upd({ name: v })} />
              <Text label="Nature of business" value={q.nature} max={300} placeholder="e.g. Wholesale trading of steel" onChange={(v) => upd({ nature: v })} />
              <Text label={panOk ? 'PAN' : 'PAN (format AAAAA9999A)'} value={q.pan} max={10} onChange={(v) => upd({ pan: v.toUpperCase() })} />
              <Text label={gstinOk ? 'GSTIN' : 'GSTIN (15 characters)'} value={q.gstin} max={15} onChange={(v) => upd({ gstin: v.toUpperCase() })} />
            </div>
            <div className="mt-sm"><Text label="Address" value={q.address} max={500} onChange={(v) => upd({ address: v })} /></div>
            <p className="faint mt-sm" style={{ fontSize: 12 }}>PAN and GSTIN are shown masked in the draft; enter the full numbers in the e-filing utility.</p>
          </Disclosure>
          {q.taxpayer_type !== 'firm' && q.taxpayer_type !== 'llp' && q.taxpayer_type !== 'company' && (
            <div className="grid cols-2 mt-sm" style={{ gap: 10 }}>
              <Sel label="Tax regime (for the exemption limit)" value={q.regime} onChange={(v) => upd({ regime: v })} options={[['new', 'New regime'], ['old', 'Old regime']]} />
              <Sel label="Age" value={q.age} onChange={(v) => upd({ age: v })} options={[['below_60', 'Below 60'], ['60_to_79', '60 to 79'], ['80_plus', '80 or more']]} />
            </div>
          )}
        </Card>
      </div>

      {r.error ? <ErrorBox error={r.error} onRetry={r.reload} /> : !d ? <Skeleton h={200} /> : (
        <>
          <Card title={<span className="row"><ClipboardCheck size={17} className="pos" />Is a tax audit required?</span>}
            actions={<button className="btn primary" onClick={download}><Download size={15} />Word draft (3CB + 3CD)</button>}>
            <Callout tone={d.applicability.required ? 'warn' : d.applicability.required === false ? 'success' : 'info'}
              title={d.applicability.required ? `Yes — ${d.applicability.clauses.join(', ')} · ${d.applicability.forms}`
                : d.applicability.required === false ? 'No tax audit is needed on these figures' : 'Not decided yet — a few figures are missing'}>
              {d.applicability.form_reason}
              {d.applicability.missing.length > 0 && <div>Missing: {d.applicability.missing.map((m) => FIELD[m] ?? m).join(', ')}.</div>}
            </Callout>
            <div className="table-wrap mt-sm" tabIndex={0}>
              <table className="data fixed-cols">
                <colgroup><col style={{ width: 90 }} /><col style={{ width: '32%' }} /><col /><col style={{ width: 140 }} /></colgroup>
                <thead><tr><th>Test</th><th>Rule</th><th>Working</th><th>Result</th></tr></thead>
                <tbody>{d.applicability.tests.map((t) => (
                  <tr key={t.clause + t.working}>
                    <td><a href={t.source} target="_blank" rel="noreferrer">{t.clause}</a></td>
                    <td style={{ fontSize: 12.5 }}>{t.rule}</td>
                    <td style={{ fontSize: 12.5 }}>{t.working}</td>
                    <td>{t.result ? <Badge tone="warn">Audit required</Badge> : t.result === false ? <Badge tone="pos">Not required</Badge> : <Badge tone="info">Need figures</Badge>}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
            {d.inputs_from_files.length > 0 && (
              <p className="faint mt-sm" style={{ fontSize: 12.5 }}>Taken from your files: {d.inputs_from_files.map((x) => `${FIELD[x.field] ?? x.field} ${inr(x.value)} (${x.source})`).join(' · ')}</p>
            )}
            <Callout tone={d.due.report_overdue && d.applicability.required ? 'error' : 'info'} title={`Report due ${fmtDate(d.due.report_due)} · return due ${fmtDate(d.due.itr_due)}`}>
              {d.due.message} <a href={d.due.source} target="_blank" rel="noreferrer">Circular 07/2026</a>
              {d.applicability.penalty_271b != null && <div className="mt-sm">Maximum penalty under section 271B: <b>{inr(d.applicability.penalty_271b)}</b>. {d.applicability.penalty_note}</div>}
            </Callout>
          </Card>

          {d.documents.length > 0 && (
            <Card title="What was read from each file">
              <div className="table-wrap" tabIndex={0}>
                <table className="data">
                  <thead><tr><th>File</th><th>Used for</th><th>Notes</th></tr></thead>
                  <tbody>{d.documents.map((x) => (
                    <tr key={x.upload_id}><td>{x.file}</td><td style={{ whiteSpace: 'normal' }}>{x.used_for.join(' · ')}</td>
                      <td style={{ whiteSpace: 'normal', fontSize: 12.5 }}>{x.notes.join(' ')}</td></tr>
                  ))}</tbody>
                </table>
              </div>
              {d.ledgers.map((l) => <p key={l.file} className="faint mt-sm" style={{ fontSize: 12 }}>{l.file} › {l.sheet}: {l.rows} transactions; {l.direction_rule}; {l.contra_excluded} contra entr{l.contra_excluded === 1 ? 'y' : 'ies'} (cash deposited / withdrawn) left out.</p>)}
            </Card>
          )}

          <Card title="Form 3CD — statement of particulars (draft)"
            subtitle={Object.entries(d.counts).map(([k, n]) => `${d.status_labels[k] ?? k}: ${n}`).join(' · ')}
            actions={<select className="input" aria-label="Show clauses" value={filter} onChange={(e) => setFilter(e.target.value as typeof filter)} style={{ width: 'auto' }}>
              <option value="all">All clauses</option>
              {Object.keys(d.counts).map((k) => <option key={k} value={k}>{d.status_labels[k]} ({d.counts[k]})</option>)}
            </select>}>
            <div className="table-wrap" tabIndex={0}>
              <table className="data fixed-cols">
                <colgroup><col style={{ width: 84 }} /><col style={{ width: "30%" }} /><col /><col style={{ width: 176 }} /></colgroup>
                <thead><tr><th>Clause</th><th>Particulars</th><th>Draft answer and working</th><th>Status</th></tr></thead>
                <tbody>{shown.map((c) => (
                  <tr key={c.no}>
                    <td className="mono"><b>{c.no}</b></td>
                    <td style={{ fontSize: 12.5 }}>{c.title}</td>
                    <td style={{ fontSize: 12.5 }}>
                      {c.answer && <div><b>{c.answer}</b></div>}
                      {c.rows.slice(0, 10).map((x, i) => (
                        <div key={i} className="mt-sm"><div>{x.metric}: <span className="mono">{x.substituted}</span> = <b>{x.result}</b></div>
                          <div className="faint" style={{ fontSize: 11.5 }}>{x.formula}{x.source ? ` · ${x.source}` : ''}</div></div>
                      ))}
                      {c.rows.length > 10 && <div className="faint">+{c.rows.length - 10} more in the Word draft</div>}
                      {c.evidence.filter((e) => e.where).slice(0, 2).map((e, i) => <div key={i} className="faint" style={{ fontSize: 11.5 }}>{e.file} · {e.where}</div>)}
                      {c.status === 'needs_input' && !c.answer && <div className="faint">Needs: {c.needed}</div>}
                      {c.note && <div className="faint mt-sm" style={{ fontSize: 11.5 }}>{c.note}</div>}
                    </td>
                    <td><Badge tone={TONE[c.status]}>{d.status_labels[c.status]}</Badge></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
            <p className="faint mt-sm" style={{ fontSize: 12 }}>Short plain-English titles; the e-filing utility has the official wording. Form 3CD as amended by Notification 23/2025 (from 1 April 2025): clauses 28 and 29 omitted, 22 substituted (MSME / 43B(h)), 36B added. <a href={d.sources.form_3cd_changes} target="_blank" rel="noreferrer">Summary of the changes</a></p>
          </Card>

          <Card title={d.report_3cb.title} subtitle={d.report_3cb.note}>
            <div className="stack" style={{ gap: 8, fontSize: 13.5, maxWidth: 860 }}>
              {d.report_3cb.paragraphs.map((p) => <p key={p} style={{ margin: 0 }}>{p}</p>)}
            </div>
            <div className="grid cols-3 mt" style={{ gap: 8 }}>
              {d.report_3cb.auditor_fields.map((f) => <div key={f} className="faint" style={{ fontSize: 12.5 }}>{f}: <span style={{ borderBottom: '1px dashed currentColor', display: 'inline-block', minWidth: 90 }}>&nbsp;</span></div>)}
            </div>
            <p className="faint mt-sm" style={{ fontSize: 12 }}>{d.report_3cb.auditor_note}</p>
          </Card>

          <Card title="Rules used">
            <ul style={{ paddingLeft: 18, margin: 0, fontSize: 13 }}>
              {d.notes.map((n) => <li key={n}>{n}</li>)}
            </ul>
            <div className="row mt-sm" style={{ flexWrap: 'wrap', gap: 12, fontSize: 12.5 }}>
              <a href={d.sources.s44ab} target="_blank" rel="noreferrer">Section 44AB</a>
              <a href={d.sources.s44ad} target="_blank" rel="noreferrer">Presumptive taxation (44AD)</a>
              <a href={d.sources.cash_limits} target="_blank" rel="noreferrer">Cash limits (40A(3), 269SS/ST/T)</a>
              <a href={d.sources.s271b} target="_blank" rel="noreferrer">Penalty 271B</a>
              <a href={d.sources.circular_7_2026} target="_blank" rel="noreferrer">Circular 07/2026</a>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
