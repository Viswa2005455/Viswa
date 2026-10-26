import { FileSearch, FileUp, Loader2 } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { api, uploadWithProgress } from '../lib/api';
import { fmtMoney, isNum } from '../lib/format';
import { useProjects } from '../lib/project';
import { loadRaw, save } from '../lib/storage';
import { useToast } from '../lib/toast';
import type { UploadSummary } from '../lib/types';
import { useAsync } from '../lib/useApi';
import { Badge, Callout, Card, ErrorBox } from './ui';

export interface DocFact { field: string; question: string; value: unknown; status: 'found' | 'suggested'; note: string; evidence: { file: string; where: string; text: string }[] }
export interface DocsResult {
  documents: { upload_id: string; file: string; label: string; lines_read: number; types: string[]; notes: string[] }[];
  facts: DocFact[]; unanswered: { field: string; question: string }[]; rules: string;
}
type Profile = Record<string, unknown>;

const ACCEPT = '.pdf,.xlsx,.xlsm,.xls,.csv,.tsv,.txt,.docx,.json';
const AMOUNTS = new Set(['total_income', 'ltcg_112a', 'agricultural_income']);
const LABEL: Record<string, Record<string, string>> = {
  taxpayer_type: { individual: 'Individual', huf: 'HUF', firm: 'Partnership firm', llp: 'LLP', company: 'Company', aop_boi: 'AOP / BOI', local_authority: 'Local authority', trust_or_institution: 'Trust / institution' },
  residential_status: { resident: 'Resident', rnor: 'Resident but not ordinarily resident', non_resident: 'Non-resident' },
};
const show = (f: DocFact) => (typeof f.value === 'boolean' ? (f.value ? 'Yes' : 'No') : AMOUNTS.has(f.field) && isNum(f.value) ? fmtMoney(f.value, 'INR')
  : LABEL[f.field]?.[String(f.value)] ?? String(f.value));

/** Upload tax documents; facts the documents state fill the ITR questions, each with its evidence.
 * "Found" facts are used at once; "suggested" ones only after the user ticks them. Questions no
 * document answers keep the user's own answers. */
export function ItrDocuments({ profile, defaults, onApply }: { profile: Profile; defaults: Profile; onApply: (patch: Profile, fromDocs: string[]) => void }) {
  const toast = useToast();
  const { activeId } = useProjects();
  const inputRef = useRef<HTMLInputElement>(null);
  const uploads = useAsync((signal) => api.get<{ uploads: UploadSummary[] }>('/api/uploads', { signal }), []);
  const [picked, setPicked] = useState<string[]>(() => loadRaw('fis.itax.docs.picked', []));
  const [result, setResult] = useState<DocsResult | null>(() => loadRaw('fis.itax.docs.result', null));
  const [use, setUse] = useState<Record<string, boolean>>(() => loadRaw('fis.itax.docs.use', {}));
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const read = async (ids: string[]) => {
    if (!ids.length) return;
    setBusy('Reading your documents…'); setError(null);
    try {
      const r = await api.post<DocsResult>('/api/tax/itr-from-uploads', { upload_ids: ids });
      const u = Object.fromEntries(r.facts.map((f) => [f.field, f.status === 'found']));
      setResult(r); setUse(u);
      save('fis.itax.docs.result', r); save('fis.itax.docs.use', u);
      apply(r, u);
    } catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  };

  /** Ticked facts overwrite their question; an unticked fact puts its question back to the default. */
  const apply = (r: DocsResult, u: Record<string, boolean>) => {
    const patch: Profile = {};
    const from: string[] = [];
    for (const f of r.facts) {
      if (u[f.field]) { patch[f.field] = f.value; from.push(f.field); }
      else if (profile[f.field] === f.value) patch[f.field] = defaults[f.field];
    }
    if (patch.presumptive && patch.presumptive !== 'none' && !('business_income' in patch)) patch.business_income = true;
    onApply(patch, from);
  };

  const toggle = (field: string, on: boolean) => {
    const u = { ...use, [field]: on };
    setUse(u); save('fis.itax.docs.use', u);
    if (result) apply(result, u);
  };

  const pick = (ids: string[]) => { setPicked(ids); save('fis.itax.docs.picked', ids); };

  const send = async (files: File[]) => {
    const ids: string[] = [];
    for (const [i, file] of files.entries()) {
      setBusy(`Uploading ${file.name} (${i + 1} of ${files.length})…`);
      try {
        const res = await uploadWithProgress<{ results: ({ ok: true; upload: { id: string } } | { ok: false; error: string })[] }>('/api/uploads', [file], () => {}, { project_id: activeId });
        const r = res.results[0];
        if (r.ok) ids.push(r.upload.id); else toast(`${file.name}: ${r.error}`, 'error');
      } catch (e) { toast(`${file.name}: ${(e as Error).message}`, 'error'); }
    }
    setBusy(null);
    uploads.reload();
    if (ids.length) {
      const all = [...new Set([...picked, ...ids])];
      pick(all);
      await read(all);
    }
  };

  useEffect(() => { // forget picks of files that were deleted
    if (uploads.data) { const have = new Set(uploads.data.uploads.map((u) => u.id)); if (picked.some((p) => !have.has(p))) pick(picked.filter((p) => have.has(p))); }
  }, [uploads.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const files = (uploads.data?.uploads ?? []).filter((u) => u.status === 'processed' && u.category !== 'code' && u.category !== 'archive').slice(0, 20);
  const found = result?.facts.filter((f) => use[f.field]).length ?? 0;

  return (
    <Card title={<span className="row"><FileSearch size={17} className="pos" />Find your ITR form from your documents</span>}
      subtitle="Upload Form 16, Form 26AS, AIS/TIS, capital-gains statements, a P&L or a tax audit report. The app reads them on this server (nothing is sent elsewhere), fills the questions below and shows where each answer came from.">
      <div className="grid cols-2" style={{ alignItems: 'start' }}>
        <div className="stack">
          <div className="dropzone" role="button" tabIndex={0} aria-label="Upload tax documents: drop here or press Enter to browse"
            onClick={() => inputRef.current?.click()}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); inputRef.current?.click(); } }}
            onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); send(Array.from(e.dataTransfer.files)); }}>
            <FileUp size={26} className="pos" />
            <div style={{ fontWeight: 650, marginTop: 6 }}>Drop tax documents here or click to browse</div>
            <div className="faint" style={{ fontSize: 12, marginTop: 4 }}>PDF, Excel, CSV, Word, text or JSON · scanned PDFs need text (OCR is not available)</div>
            <input ref={inputRef} type="file" multiple accept={ACCEPT} hidden onChange={(e) => { send(Array.from(e.target.files ?? [])); e.target.value = ''; }} />
          </div>
          {busy && <div className="row faint" style={{ fontSize: 13 }}><Loader2 size={15} className="spin" />{busy}</div>}
          {error && <ErrorBox error={error} />}
        </div>
        <div>
          <div className="field-label" style={{ marginBottom: 6 }}>Or choose files you uploaded before</div>
          {files.length ? (
            <div className="stack" style={{ gap: 4, maxHeight: 190, overflow: 'auto' }}>
              {files.map((u) => (
                <label key={u.id} className="row" style={{ gap: 8, fontSize: 13, minHeight: 32 }}>
                  <input type="checkbox" checked={picked.includes(u.id)} onChange={(e) => pick(e.target.checked ? [...picked, u.id] : picked.filter((x) => x !== u.id))} />
                  <span className="truncate">{u.name}</span>
                </label>
              ))}
            </div>
          ) : <p className="faint" style={{ fontSize: 13 }}>No files yet.</p>}
          <button className="btn primary mt-sm" disabled={!picked.length || !!busy} onClick={() => read(picked)}>Read {picked.length || ''} selected document{picked.length === 1 ? '' : 's'}</button>
        </div>
      </div>

      {result && (
        <div className="stack mt">
          <div className="table-wrap" tabIndex={0}>
            <table className="data">
              <thead><tr><th>Document</th><th>Recognised as</th><th className="r">Lines read</th><th>Notes</th></tr></thead>
              <tbody>{result.documents.map((d) => (
                <tr key={d.upload_id}><td>{d.file}</td><td>{d.types.length ? d.types.join(', ') : <span className="faint">Not a recognised tax form</span>}</td>
                  <td className="r">{d.lines_read}</td><td style={{ whiteSpace: 'normal', fontSize: 12.5 }}>{d.notes[0] ?? ''}</td></tr>
              ))}</tbody>
            </table>
          </div>

          {result.facts.length ? (
            <>
              <div className="field-label">What your documents say ({found} answer{found === 1 ? '' : 's'} in use)</div>
              <div className="table-wrap" tabIndex={0}>
                <table className="data calc-table">
                  <thead><tr><th>Use</th><th>Question</th><th>Answer</th><th>Status</th><th>Where it was found</th></tr></thead>
                  <tbody>{result.facts.map((f) => (
                    <tr key={f.field}>
                      <td><input type="checkbox" checked={!!use[f.field]} aria-label={`Use the answer for ${f.question}`} onChange={(e) => toggle(f.field, e.target.checked)} /></td>
                      <td>{f.question}{f.note && <div className="faint" style={{ fontSize: 11.5 }}>{f.note}</div>}</td>
                      <td className="num"><b>{show(f)}</b></td>
                      <td>{f.status === 'found' ? <Badge tone="pos">Found</Badge> : <Badge tone="warn">Please confirm</Badge>}</td>
                      <td style={{ fontSize: 12 }}>{f.evidence.slice(0, 2).map((e, i) => (
                        <div key={i}><span className="mono">{e.file} · {e.where}</span><div className="faint">“{e.text}”</div></div>
                      ))}{f.evidence.length > 2 && <div className="faint">+{f.evidence.length - 2} more</div>}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            </>
          ) : <Callout tone="warn">None of the facts that decide the ITR form were found in these documents. Answer the questions below yourself.</Callout>}

          {result.unanswered.length > 0 && (
            <Callout tone="info" title="Not mentioned in your documents — answer these below yourself">
              {result.unanswered.map((u) => u.question).join(' · ')}. Unticked questions count as "No".
            </Callout>
          )}
        </div>
      )}
    </Card>
  );
}
