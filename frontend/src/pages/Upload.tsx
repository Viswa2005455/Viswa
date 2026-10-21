import { ArrowRight, FileCode2, FileSpreadsheet, FileText, FileUp, FolderArchive, RefreshCw, Trash2, UploadCloud, X } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { CodeView } from '../components/CodeView';
import { SheetPreview, type Sheet } from '../components/SheetPreview';
import { Badge, Callout, Card, EmptyState, ErrorBox, PageHeader, Skeleton, Tabs, Warnings } from '../components/ui';
import { api, uploadWithProgress } from '../lib/api';
import { fmtBytes } from '../lib/format';
import { useToast } from '../lib/toast';
import type { UploadSummary } from '../lib/types';
import { useAsync } from '../lib/useApi';
import { useProjects } from '../lib/project';
import { useAuth } from '../lib/auth';

interface Analysis {
  kind: string; warnings?: string[]; sheets?: Sheet[]; text?: string; page_count?: number;
  pages?: { page: number; chars: number; text: string; tables: number[] }[];
  context?: { currencies: Record<string, number>; units: Record<string, number>; periods: string[] };
  language?: string; extension?: string; line_count?: number; note?: string;
  outline?: Record<string, unknown> & { syntax_errors?: { line: number; message: string }[]; issues?: string[] };
  cells?: { index: number; type: string; source: string }[]; syntax_errors?: { cell: number; line: number; message: string }[];
  members?: { name: string; size: number; is_dir: boolean; blocked: string | null; note?: string }[];
  children?: { path: string; label: string; summary: string }[];
  valid?: boolean; error?: string | null; structure?: Record<string, unknown>; format?: string;
}
interface UploadRecord extends UploadSummary { sha256: string; analysis: Analysis; statement_mapping: unknown[]; variance_lines: { lines: unknown[] } | null }
interface Pending { key: string; file: File; progress: number; state: 'uploading' | 'processing' | 'error'; error?: string }

const ACCEPT = '.xlsx,.xlsm,.xls,.csv,.tsv,.pdf,.docx,.doc,.txt,.md,.json,.xml,.py,.ipynb,.sql,.java,.js,.jsx,.ts,.tsx,.html,.css,.r,.rmd,.sas,.do,.m,.mat,.yml,.yaml,.toml,.log,.zip';

function iconFor(cat: string) {
  if (cat === 'spreadsheet' || cat === 'table') return FileSpreadsheet;
  if (cat === 'code' || cat === 'notebook') return FileCode2;
  if (cat === 'archive') return FolderArchive;
  return FileText;
}

export function UploadPage() {
  const toast = useToast();
  const { active, activeId } = useProjects();
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const selected = params.get('file');
  const list = useAsync(() => api.get<{ uploads: UploadSummary[]; }>(`/api/uploads${activeId ? `?project_id=${activeId}` : ''}`), [activeId]);
  const formats = useAsync(() => api.get<{ max_upload_mb: number; max_files_per_request: number }>('/api/uploads/formats'), []);
  const [pending, setPending] = useState<Pending[]>([]);
  const [over, setOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const maxMb = formats.data?.max_upload_mb ?? 25;

  const send = useCallback(async (files: File[]) => {
    const tooBig = files.filter((f) => f.size > maxMb * 1024 * 1024);
    tooBig.forEach((f) => toast(`${f.name} is larger than ${maxMb} MB`, 'error'));
    const ok = files.filter((f) => f.size <= maxMb * 1024 * 1024);
    for (const file of ok) {
      const key = `${file.name}-${file.size}-${Date.now()}-${Math.random()}`;
      setPending((p) => [...p, { key, file, progress: 0, state: 'uploading' }]);
      try {
        const res = await uploadWithProgress<{ results: ({ ok: true; upload: UploadSummary } | { ok: false; error: string })[] }>(
          '/api/uploads', [file], (f) => setPending((p) => p.map((x) => x.key === key ? { ...x, progress: f, state: f >= 1 ? 'processing' : 'uploading' } : x)), { project_id: activeId });
        const r = res.results[0];
        if (r.ok) {
          setPending((p) => p.filter((x) => x.key !== key));
          toast(`${file.name} analysed`);
          setParams({ file: r.upload.id });
        } else {
          setPending((p) => p.map((x) => x.key === key ? { ...x, state: 'error', error: r.error } : x));
        }
      } catch (e) {
        setPending((p) => p.map((x) => x.key === key ? { ...x, state: 'error', error: (e as Error).message } : x));
      }
      list.reload();
    }
  }, [list, maxMb, setParams, toast, activeId]);

  const retry = (p: Pending) => { setPending((all) => all.filter((x) => x.key !== p.key)); send([p.file]); };

  return (
    <div className="page">
      <PageHeader title="Upload & Analyse"
        subtitle="Upload financial files, documents or code. Each file is validated, previewed with source references and routed to a suitable analysis. Code is never executed on upload." />

      <div className="grid cols-3">
        <div className="stack">
          <div
            className={`dropzone ${over ? 'over' : ''}`}
            role="button" tabIndex={0} aria-label="Upload files: drop here or press Enter to browse"
            onClick={() => inputRef.current?.click()}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); inputRef.current?.click(); } }}
            onDragOver={(e) => { e.preventDefault(); setOver(true); }}
            onDragLeave={() => setOver(false)}
            onDrop={(e) => { e.preventDefault(); setOver(false); send(Array.from(e.dataTransfer.files)); }}
          >
            <UploadCloud size={30} className="pos" />
            <div style={{ fontWeight: 650, marginTop: 8 }}>Drop files here or click to browse</div>
            <div className="faint" style={{ fontSize: 12, marginTop: 4 }}>
              Excel, CSV, PDF, Word, text, JSON/XML, Python, notebooks, SQL, Java and more · up to {maxMb} MB each · ZIP archives inspected safely
            </div>
            <input ref={inputRef} type="file" multiple accept={ACCEPT} hidden onChange={(e) => { send(Array.from(e.target.files ?? [])); e.target.value = ''; }} />
          </div>

          {pending.length > 0 && (
            <Card title="Processing">
              <div className="list">
                {pending.map((p) => (
                  <div key={p.key} className="list-item" style={{ display: 'block' }}>
                    <div className="row between">
                      <span className="truncate" style={{ fontWeight: 550, maxWidth: '70%' }}>{p.file.name}</span>
                      <span className="faint" style={{ fontSize: 12 }}>
                        {p.state === 'uploading' ? `Uploading ${Math.round(p.progress * 100)}%` : p.state === 'processing' ? 'Analysing…' : 'Failed'}
                      </span>
                    </div>
                    {p.state !== 'error' ? (
                      <div className={`progress mt-sm ${p.state === 'processing' ? 'indeterminate' : ''}`}><i style={{ width: `${p.progress * 100}%` }} /></div>
                    ) : (
                      <div className="mt-sm">
                        <div className="neg" style={{ fontSize: 12.5 }}>{p.error}</div>
                        <div className="row mt-sm">
                          <button className="btn sm" onClick={() => retry(p)}><RefreshCw size={14} />Retry</button>
                          <button className="btn sm ghost" onClick={() => setPending((all) => all.filter((x) => x.key !== p.key))}><X size={14} />Dismiss</button>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </Card>
          )}

          <Card title={active ? `Files in ${active.name}` : 'All your files'}
            subtitle={<>{active ? 'New uploads go into this project. ' : 'No project selected: showing every file; new uploads are not assigned to a project. '}
              Files are private to your account and deleted automatically after {user?.retention_days ?? 90} days.</>}>
            {list.loading && !list.data ? <Skeleton h={80} /> : list.error ? <ErrorBox error={list.error} onRetry={list.reload} /> :
              !list.data?.uploads.length ? <EmptyState icon={<FileUp size={22} />} title="No files yet">Upload a file to get started.</EmptyState> : (
                <div className="list">
                  {list.data.uploads.map((u) => {
                    const Icon = iconFor(u.category);
                    return (
                      <button key={u.id} className="list-item" onClick={() => setParams({ file: u.id })}
                        style={{ background: selected === u.id ? 'var(--accent-soft)' : 'transparent', border: 0, borderBottom: '1px solid var(--border)', width: '100%', textAlign: 'left', cursor: 'pointer', color: 'inherit', padding: '10px 8px', borderRadius: 8 }}>
                        <Icon size={18} className={u.status === 'failed' ? 'neg' : 'pos'} />
                        <div className="grow">
                          <div className="truncate" style={{ fontWeight: 550 }}>{u.name}</div>
                          <div className="faint truncate" style={{ fontSize: 12 }}>{fmtBytes(u.size)} · {u.summary}</div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
          </Card>
        </div>

        <div className="span-2">
          {selected ? <FileDetail id={selected} onDeleted={() => { setParams({}); list.reload(); }} onReplace={(f) => send([f])} onMoved={list.reload} /> : (
            <Card>
              <EmptyState icon={<FileSpreadsheet size={22} />} title="Select or upload a file">
                You'll see a preview with worksheet and cell references, detected currencies, units and periods, data-quality warnings and
                recommended analyses. Uncertain mappings always ask for your confirmation.
              </EmptyState>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function FileDetail({ id, onDeleted, onReplace, onMoved }: { id: string; onDeleted: () => void; onReplace: (f: File) => void; onMoved: () => void }) {
  const toast = useToast();
  const { projects, reload: reloadProjects } = useProjects();
  const rec = useAsync(() => api.get<UploadRecord>(`/api/uploads/${id}`), [id]);
  const [tab, setTab] = useState<'preview' | 'details'>('preview');
  const replaceRef = useRef<HTMLInputElement>(null);
  useEffect(() => setTab('preview'), [id]);

  if (rec.loading && !rec.data) return <Card><Skeleton h={22} w="40%" /><div className="mt"><Skeleton h={260} /></div></Card>;
  if (rec.error) return <ErrorBox error={rec.error} onRetry={rec.reload} />;
  const u = rec.data!;
  const a = u.analysis;

  const del = async () => {
    if (!confirm(`Delete ${u.name} and its analysis? This cannot be undone.`)) return;
    try {
      await api.del(`/api/uploads/${u.id}`);
      toast('File deleted');
      onDeleted();
    } catch (e) {
      toast((e as Error).message, 'error');
    }
  };

  const errorLines = a.outline?.syntax_errors?.map((e) => e.line) ?? [];
  return (
    <div className="stack">
      <Card title={<span className="row">{u.name}<Badge tone="accent">{u.label}</Badge>{u.status === 'failed' && <Badge tone="neg">Failed</Badge>}</span>}
        subtitle={`${fmtBytes(u.size)} · uploaded ${new Date(u.uploaded_at).toLocaleString()}${u.expires_at ? ` · auto-deletes ${new Date(u.expires_at).toLocaleDateString()}` : ''} · SHA-256 ${u.sha256.slice(0, 12)}…`}
        actions={<>
          <button className="btn sm" onClick={() => replaceRef.current?.click()}><RefreshCw size={14} />Replace</button>
          <input ref={replaceRef} type="file" hidden onChange={async (e) => {
            const f = e.target.files?.[0];
            e.target.value = '';
            if (!f) return;
            await api.del(`/api/uploads/${u.id}`).catch(() => {});
            onReplace(f);
          }} />
          <select className="input compact" style={{ width: 170 }} aria-label="Project for this file" value={u.project_id ?? ''}
            onChange={async (e) => {
              try { await api.patch(`/api/uploads/${u.id}`, { project_id: e.target.value || null }); toast('File moved'); rec.reload(); reloadProjects(); onMoved(); }
              catch (err) { toast((err as Error).message, 'error'); }
            }}>
            <option value="">No project</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <button className="btn sm danger" onClick={del}><Trash2 size={14} />Delete</button>
        </>}>
        {u.error && <Callout tone="error" title="Could not process this file">{u.error}</Callout>}
        {u.recommendations.length > 0 && (
          <div>
            <div className="field-label" style={{ marginBottom: 8 }}>Recommended analyses (please confirm they fit your file)</div>
            <div className="grid cols-2">
              {u.recommendations.map((r) => (
                <Link key={r.module} to={`${r.route}?file=${u.id}`} className="card interactive" style={{ padding: 12, textDecoration: 'none', color: 'inherit' }}>
                  <div className="row between"><b>{r.module}</b><Badge tone={r.confidence === 'high' ? 'accent' : r.confidence === 'medium' ? 'info' : undefined}>{r.confidence}</Badge></div>
                  <div className="faint" style={{ fontSize: 12.5, marginTop: 4 }}>{r.reason}</div>
                  <div className="row pos" style={{ fontSize: 12.5, marginTop: 6 }}>Open <ArrowRight size={13} /></div>
                </Link>
              ))}
            </div>
          </div>
        )}
        {a.context && (Object.keys(a.context.currencies).length > 0 || Object.keys(a.context.units).length > 0 || a.context.periods.length > 0) && (
          <div className="mt">
            <Callout tone="info" title="Detected in the document — please confirm">
              <div>Currencies: {Object.keys(a.context.currencies).join(', ') || 'none found'} · Units: {Object.keys(a.context.units).join(', ') || 'not stated'}</div>
              {a.context.periods.length > 0 && <div>Periods: {a.context.periods.slice(0, 12).join(', ')}</div>}
            </Callout>
          </div>
        )}
        {a.warnings && a.warnings.length > 0 && <div className="mt"><Warnings items={a.warnings} /></div>}
      </Card>

      {u.status === 'processed' && (
        <Card actions={<Tabs label="View" value={tab} onChange={setTab} options={[{ value: 'preview', label: 'Preview' }, { value: 'details', label: 'Details' }]} />}
          title="Contents">
          {tab === 'preview' ? <Preview a={a} ext={u.extension} errorLines={errorLines} /> : <Details a={a} />}
        </Card>
      )}
    </div>
  );
}

function Preview({ a, ext, errorLines }: { a: Analysis; ext: string; errorLines: number[] }) {
  if (a.kind === 'tabular' && a.sheets?.length) return <SheetPreview sheets={a.sheets} excel={['.xlsx', '.xlsm', '.xls'].includes(ext)} />;
  if (a.kind === 'code' && a.cells) {
    return (
      <div className="stack">
        {a.syntax_errors?.length ? <Callout tone="error" title="Syntax errors">{a.syntax_errors.map((e) => <div key={`${e.cell}-${e.line}`}>Cell {e.cell}, line {e.line}: {e.message}</div>)}</Callout> : null}
        {a.cells.slice(0, 40).map((c) => (
          <div key={c.index}>
            <div className="faint" style={{ fontSize: 12, marginBottom: 4 }}>Cell {c.index} · {c.type}</div>
            {c.type === 'code' ? <CodeView text={c.source} ext=".py" /> : <div className="formula" style={{ fontFamily: 'var(--font-sans)', borderStyle: 'solid' }}>{c.source}</div>}
          </div>
        ))}
      </div>
    );
  }
  if (a.kind === 'code') {
    return (
      <div className="stack">
        <Callout tone="info">{a.note}</Callout>
        {a.outline?.syntax_errors?.length ? <Callout tone="error" title="Syntax error">{a.outline.syntax_errors.map((e) => <div key={e.line}>Line {e.line}: {e.message}</div>)}</Callout> : null}
        {a.outline?.issues?.length ? <Warnings items={a.outline.issues} /> : null}
        <CodeView text={a.text ?? ''} ext={ext} errorLines={errorLines} />
      </div>
    );
  }
  if (a.kind === 'archive') {
    return (
      <div className="table-wrap">
        <table className="data">
          <thead><tr><th>Entry</th><th className="r">Size</th><th>Status</th></tr></thead>
          <tbody>
            {a.members?.map((m) => {
              const child = a.children?.find((c) => c.path === m.name);
              return (
                <tr key={m.name}>
                  <td className="mono">{m.name}</td><td className="r">{m.is_dir ? '' : fmtBytes(m.size)}</td>
                  <td>{m.blocked ? <Badge tone="neg">Blocked: {m.blocked}</Badge> : child ? <Badge tone="accent">{child.label} · {child.summary}</Badge> : <span className="faint">{m.note ?? (m.is_dir ? 'folder' : 'not analysed')}</span>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  }
  return (
    <div className="stack">
      {a.sheets && a.sheets.length > 0 && <><div className="field-label">Tables extracted</div><SheetPreview sheets={a.sheets} excel={false} /></>}
      {a.pages ? (
        a.pages.slice(0, 10).map((p) => (
          <details key={p.page} className="disclosure" open={p.page === 1}>
            <summary>Page {p.page} <span className="faint" style={{ fontWeight: 400 }}>· {p.chars.toLocaleString()} characters{p.tables.length ? ` · ${p.tables.length} table(s)` : ''}</span></summary>
            <div className="body"><pre className="formula" style={{ maxHeight: 320, overflow: 'auto' }}>{p.text || '(no extractable text)'}</pre></div>
          </details>
        ))
      ) : a.text !== undefined ? (
        <>
          {a.valid === false && <Callout tone="error" title={`Invalid ${a.format}`}>{a.error}</Callout>}
          <CodeView text={a.text} ext={ext} />
        </>
      ) : <span className="faint">No preview available.</span>}
    </div>
  );
}

function Details({ a }: { a: Analysis }) {
  const rows: [string, string][] = [['Kind', a.kind]];
  if (a.language) rows.push(['Language', a.language]);
  if (a.line_count) rows.push(['Lines', a.line_count.toLocaleString()]);
  if (a.page_count) rows.push(['Pages', String(a.page_count)]);
  if (a.sheets) rows.push(['Tables / worksheets', String(a.sheets.length)]);
  const outline = a.outline ?? a.structure;
  return (
    <div className="stack">
      <div>{rows.map(([k, v]) => <div key={k} className="metric-row"><span className="muted">{k}</span><span className="v">{v}</span></div>)}</div>
      {outline && <pre className="formula" style={{ maxHeight: 360, overflow: 'auto' }}>{JSON.stringify(outline, null, 2)}</pre>}
    </div>
  );
}
