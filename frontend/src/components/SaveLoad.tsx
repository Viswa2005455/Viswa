import { FolderOpen, History, Save } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../lib/api';
import { useProjects } from '../lib/project';
import { useToast } from '../lib/toast';
import { Modal } from './Modal';
import { Badge, Callout, Field, Skeleton } from './ui';

export type SavedKind = 'dcf' | 'scenarios' | 'budget' | 'statements' | 'cash_budget' | 'variance' | 'ratios' | 'forecast' | 'investment'
  | 'costing' | 'accounting' | 'investments';
interface Item { id: string; kind: SavedKind; name: string; project_id: string | null; latest_version: number; updated_at: string }
interface Full extends Item { data: Record<string, unknown>; versions: { version: number; note: string; created_at: string; size: number }[] }

const fmtDate = (s: string) => new Date(s).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });

/**
 * Save the page's current model to the active project (each save adds a version) and reopen any
 * saved model or earlier version. Opening via a link with ?saved=<id> loads that model directly.
 */
export function SaveLoad<T extends object>({ kind, label, getData, onLoad }: { kind: SavedKind; label: string; getData: () => T; onLoad: (data: T) => void }) {
  const toast = useToast();
  const { active, projects } = useProjects();
  const [params, setParams] = useSearchParams();
  const [linked, setLinked] = useState<{ id: string; name: string; version: number; project_id: string | null } | null>(null);
  const [mode, setMode] = useState<null | 'save' | 'open'>(null);
  const [name, setName] = useState('');
  const [note, setNote] = useState('');
  const [asNew, setAsNew] = useState(false);
  const [busy, setBusy] = useState(false);
  const [items, setItems] = useState<Item[] | null>(null);
  const [expanded, setExpanded] = useState<Full | null>(null);
  const [scope, setScope] = useState<'project' | 'all'>('project');

  const load = async (id: string, version?: number) => {
    try {
      const r = version
        ? await api.get<Full & { version: number }>(`/api/saved/${id}/versions/${version}`)
        : await api.get<Full>(`/api/saved/${id}`);
      if (r.kind !== kind) { toast(`That saved item is a ${r.kind} model, not ${label}.`, 'error'); return; }
      onLoad(r.data as T);
      const v = version ?? r.latest_version;
      setLinked({ id: r.id, name: r.name, version: v, project_id: r.project_id });
      toast(`Opened "${r.name}" (version ${v})`);
      setMode(null);
    } catch (e) { toast((e as Error).message, 'error'); }
  };

  const savedParam = params.get('saved');
  useEffect(() => {
    if (savedParam) {
      load(savedParam);
      const next = new URLSearchParams(params);
      next.delete('saved');
      setParams(next, { replace: true });
    }
  }, [savedParam]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (mode !== 'open') return;
    setItems(null);
    setExpanded(null);
    const q = scope === 'project' && active ? `&project_id=${active.id}` : '';
    api.get<{ items: Item[] }>(`/api/saved?kind=${kind}${q}`).then((r) => setItems(r.items)).catch((e) => toast((e as Error).message, 'error'));
  }, [mode, scope, active, kind, toast]);

  const save = async () => {
    setBusy(true);
    try {
      const data = getData();
      if (linked && !asNew) {
        const r = await api.put<Item>(`/api/saved/${linked.id}`, { data, note });
        setLinked({ ...linked, version: r.latest_version });
        toast(`Saved "${linked.name}" as version ${r.latest_version}`);
      } else {
        const r = await api.post<Item>('/api/saved', { kind, name: name.trim(), project_id: active?.id ?? null, data, note });
        setLinked({ id: r.id, name: r.name, version: 1, project_id: r.project_id });
        toast(`Saved "${r.name}"${active ? ` to ${active.name}` : ''}`);
      }
      setMode(null);
      setNote('');
    } catch (e) {
      toast((e as Error).message, 'error');
    } finally {
      setBusy(false);
    }
  };

  const projectName = (id: string | null) => (id ? projects.find((p) => p.id === id)?.name ?? 'Project' : 'No project');

  return (
    <>
      {linked && <Badge tone="info"><History size={12} />{linked.name} · v{linked.version}</Badge>}
      <button className="btn" onClick={() => { setMode('open'); setScope(active ? 'project' : 'all'); }}><FolderOpen size={15} />Open</button>
      <button className="btn" onClick={() => { setAsNew(!linked); setName(linked?.name ?? `${label} ${new Date().toLocaleDateString()}`); setMode('save'); }}><Save size={15} />Save</button>

      <Modal open={mode === 'save'} onClose={() => setMode(null)} title={`Save ${label}`}
        footer={<><button className="btn" onClick={() => setMode(null)}>Cancel</button>
          <button className="btn primary" onClick={save} disabled={busy || ((asNew || !linked) && !name.trim())}>{busy ? 'Saving…' : linked && !asNew ? `Save version ${linked.version + 1}` : 'Save'}</button></>}>
        <div className="stack">
          {linked && (
            <div className="row">
              <label className="row" style={{ fontSize: 13 }}><input type="radio" checked={!asNew} onChange={() => setAsNew(false)} />New version of "{linked.name}"</label>
              <label className="row" style={{ fontSize: 13 }}><input type="radio" checked={asNew} onChange={() => setAsNew(true)} />Save as a new model</label>
            </div>
          )}
          {(asNew || !linked) && (
            <Field label="Name"><input className="input" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} autoFocus /></Field>
          )}
          <Field label="Version note (optional)" hint="e.g. 'Raised WACC after board review'"><input className="input" value={note} maxLength={200} onChange={(e) => setNote(e.target.value)} /></Field>
          {(asNew || !linked) && (
            <Callout tone={active ? 'info' : 'warn'}>
              {active ? <>Saves to project <b>{active.name}</b>.</> : <>No project is selected, so this is saved without a project. <Link to="/projects">Create or choose a project</Link>.</>}
            </Callout>
          )}
        </div>
      </Modal>

      <Modal open={mode === 'open'} onClose={() => setMode(null)} title={`Open a saved ${label}`}>
        <div className="stack">
          {active && (
            <div className="tabs" role="tablist" aria-label="Scope">
              <button type="button" role="tab" className="tab" aria-selected={scope === 'project'} onClick={() => setScope('project')}>{active.name}</button>
              <button type="button" role="tab" className="tab" aria-selected={scope === 'all'} onClick={() => setScope('all')}>All projects</button>
            </div>
          )}
          {!items ? <Skeleton h={80} /> : items.length === 0 ? <p className="muted">Nothing saved yet. Use <b>Save</b> to store the current {label}.</p> : (
            <div className="list">
              {items.map((it) => (
                <div key={it.id} className="list-item" style={{ display: 'block' }}>
                  <div className="row between">
                    <div>
                      <b>{it.name}</b> <span className="faint" style={{ fontSize: 12 }}>· v{it.latest_version} · {projectName(it.project_id)} · {fmtDate(it.updated_at)}</span>
                    </div>
                    <div className="row">
                      <button className="btn sm ghost" onClick={async () => { setExpanded(expanded?.id === it.id ? null : await api.get<Full>(`/api/saved/${it.id}`)); }}>
                        <History size={14} />Versions
                      </button>
                      <button className="btn sm primary" onClick={() => load(it.id)}>Open latest</button>
                    </div>
                  </div>
                  {expanded?.id === it.id && (
                    <ul className="timeline" style={{ marginTop: 8 }}>
                      {expanded.versions.map((v) => (
                        <li key={v.version}><div className="row between">
                          <span>v{v.version} · {fmtDate(v.created_at)}{v.note && <span className="faint"> — {v.note}</span>}</span>
                          <button className="btn sm" onClick={() => load(it.id, v.version)}>Restore</button>
                        </div></li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          )}
          <p className="faint" style={{ fontSize: 12 }}>Opening replaces what is on screen. Save first if you want to keep it.</p>
        </div>
      </Modal>
    </>
  );
}
