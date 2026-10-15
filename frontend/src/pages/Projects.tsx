import { Archive, ArchiveRestore, CheckCircle2, Download, FileText, FolderKanban, FolderPlus, Layers, Pencil, Trash2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Modal } from '../components/Modal';
import { Badge, Callout, Card, EmptyState, ErrorBox, Field, PageHeader, Skeleton } from '../components/ui';
import { api } from '../lib/api';
import { CURRENCIES, UNIT_SCALES, downloadFile, fmtBytes } from '../lib/format';
import { useAuth } from '../lib/auth';
import { useProjects, type Project } from '../lib/project';
import { useToast } from '../lib/toast';
import { useAsync } from '../lib/useApi';

interface Detail extends Project {
  upload_list: { id: string; name: string; label: string; size: number; uploaded_at: string; expires_at: string; status: string; summary: string }[];
  saved_list: { id: string; kind: string; name: string; latest_version: number; updated_at: string }[];
}
interface ActivityRow { action: string; label: string; entity_type: string | null; detail: Record<string, unknown>; created_at: string }

const KIND_ROUTE: Record<string, [string, string]> = {
  dcf: ['/dcf', 'DCF model'], scenarios: ['/scenarios', 'Scenarios'], budget: ['/budgeting', 'Budget'], statements: ['/statements', 'Statements'],
  cash_budget: ['/cash-flow', 'Cash budget'], variance: ['/variance', 'Variance'], ratios: ['/ratios', 'Ratios'], forecast: ['/forecasting', 'Forecast'],
  investment: ['/investment', 'Appraisal'],
};
const when = (s: string) => new Date(s).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });

export function Projects() {
  const { projects, activeId, setActive, reload } = useProjects();
  const { user } = useAuth();
  const toast = useToast();
  const [selected, setSelected] = useState<string | null>(activeId);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: '', description: '', currency: 'INR', units: 'lakhs' });
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (!selected && projects.length) setSelected(activeId ?? projects[0].id); }, [projects, selected, activeId]);

  const create = async () => {
    setBusy(true);
    try {
      const p = await api.post<Project>('/api/projects', form);
      await reload();
      setActive(p.id);
      setSelected(p.id);
      setCreating(false);
      setForm({ name: '', description: '', currency: 'INR', units: 'lakhs' });
      toast(`Project "${p.name}" created and selected`);
    } catch (e) { toast((e as Error).message, 'error'); } finally { setBusy(false); }
  };

  const live = projects.filter((p) => !p.archived);
  const archived = projects.filter((p) => p.archived);

  return (
    <div className="page">
      <PageHeader title="My Projects" subtitle={<>Group files, saved models and their version history by company or assignment. The <b>active project</b> (top bar) is where new uploads and saves go.</>}
        actions={<button className="btn primary" onClick={() => setCreating(true)}><FolderPlus size={16} />New project</button>} />

      {projects.length === 0 ? (
        <Card>
          <EmptyState icon={<FolderKanban size={22} />} title="Create your first project" action={<button className="btn primary" onClick={() => setCreating(true)}><FolderPlus size={16} />New project</button>}>
            For example "Tata Motors valuation", "FY27 budget" or "CMA Part 2 practice". Uploads and saved models made while it is active are stored inside it.
          </EmptyState>
        </Card>
      ) : (
        <div className="grid cols-3">
          <div className="stack">
            <Card title={`Projects (${live.length})`}>
              <ProjectList items={live} selected={selected} activeId={activeId} onSelect={setSelected} />
            </Card>
            {archived.length > 0 && <Card title={`Archived (${archived.length})`}><ProjectList items={archived} selected={selected} activeId={activeId} onSelect={setSelected} /></Card>}
            <Callout tone="info">Uploaded files are deleted automatically {user?.retention_days ?? 90} days after upload. Saved models are kept until you delete them.</Callout>
          </div>
          <div className="span-2">{selected && <ProjectDetail key={selected} id={selected} onDeleted={() => { setSelected(null); reload(); }} />}</div>
        </div>
      )}

      <Modal open={creating} onClose={() => setCreating(false)} title="New project"
        footer={<><button className="btn" onClick={() => setCreating(false)}>Cancel</button><button className="btn primary" disabled={busy || !form.name.trim()} onClick={create}>Create</button></>}>
        <div className="stack">
          <Field label="Name"><input className="input" autoFocus maxLength={80} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Infosys valuation FY26" /></Field>
          <Field label="Description (optional)"><textarea className="input" rows={3} maxLength={2000} style={{ fontFamily: 'var(--font-sans)' }} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
          <div className="grid cols-2">
            <Field label="Currency"><select className="input" value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })}>{CURRENCIES.map((c) => <option key={c}>{c}</option>)}</select></Field>
            <Field label="Units"><select className="input" value={form.units} onChange={(e) => setForm({ ...form, units: e.target.value })}>{UNIT_SCALES.map((u) => <option key={u}>{u}</option>)}</select></Field>
          </div>
        </div>
      </Modal>
    </div>
  );
}

function ProjectList({ items, selected, activeId, onSelect }: { items: Project[]; selected: string | null; activeId: string | null; onSelect: (id: string) => void }) {
  return (
    <div className="list">
      {items.map((p) => (
        <button key={p.id} className="list-item" onClick={() => onSelect(p.id)}
          style={{ background: selected === p.id ? 'var(--accent-soft)' : 'transparent', border: 0, borderBottom: '1px solid var(--border)', width: '100%', textAlign: 'left', cursor: 'pointer', color: 'inherit', padding: '10px 8px', borderRadius: 8 }}>
          <FolderKanban size={18} className="pos" />
          <div className="grow">
            <div className="truncate" style={{ fontWeight: 600 }}>{p.name}</div>
            <div className="faint" style={{ fontSize: 12 }}>{p.uploads} files · {p.saved_items} saved models · {p.currency} {p.units}</div>
          </div>
          {activeId === p.id && <Badge tone="accent">Active</Badge>}
        </button>
      ))}
    </div>
  );
}

function ProjectDetail({ id, onDeleted }: { id: string; onDeleted: () => void }) {
  const toast = useToast();
  const { activeId, setActive, reload } = useProjects();
  const d = useAsync(() => api.get<Detail>(`/api/projects/${id}`), [id]);
  const act = useAsync(() => api.get<{ activity: ActivityRow[] }>(`/api/activity?project_id=${id}&limit=50`), [id]);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ name: '', description: '', currency: 'INR', units: 'lakhs' });
  const [confirmName, setConfirmName] = useState<string | null>(null);

  if (d.loading && !d.data) return <Card><Skeleton h={160} /></Card>;
  if (d.error || !d.data) return <ErrorBox error={d.error ?? 'Not found'} onRetry={d.reload} />;
  const p = d.data;

  const patch = async (body: Partial<Project>, msg: string) => {
    try { await api.patch(`/api/projects/${id}`, body); await reload(); d.reload(); act.reload(); toast(msg); setEditing(false); }
    catch (e) { toast((e as Error).message, 'error'); }
  };
  const exportJson = async () => {
    try {
      const data = await api.get<unknown>(`/api/projects/${id}/export`);
      downloadFile(`${p.name.replace(/\W+/g, '-')}-export.json`, JSON.stringify(data, null, 2), 'application/json');
      act.reload();
    } catch (e) { toast((e as Error).message, 'error'); }
  };
  const del = async () => {
    try {
      const r = await api.del<{ uploads_deleted: number }>(`/api/projects/${id}`);
      if (activeId === id) setActive(null);
      toast(`Project deleted (${r.uploads_deleted} files removed)`);
      setConfirmName(null);
      onDeleted();
    } catch (e) { toast((e as Error).message, 'error'); }
  };

  return (
    <div className="stack">
      <Card title={<span className="row">{p.name}{p.archived && <Badge>Archived</Badge>}{activeId === id && <Badge tone="accent">Active</Badge>}</span>}
        subtitle={`Created ${when(p.created_at)} · ${p.currency} in ${p.units}`}
        actions={<>
          {activeId !== id && !p.archived && <button className="btn sm primary" onClick={() => { setActive(id); toast(`"${p.name}" is now the active project`); }}><CheckCircle2 size={14} />Make active</button>}
          <button className="btn sm" onClick={() => { setForm({ name: p.name, description: p.description, currency: p.currency, units: p.units }); setEditing(true); }}><Pencil size={14} />Edit</button>
          <button className="btn sm" onClick={exportJson}><Download size={14} />Export</button>
          <button className="btn sm" onClick={() => patch({ archived: !p.archived }, p.archived ? 'Project restored' : 'Project archived')}>{p.archived ? <ArchiveRestore size={14} /> : <Archive size={14} />}{p.archived ? 'Restore' : 'Archive'}</button>
          <button className="btn sm danger" onClick={() => setConfirmName('')}><Trash2 size={14} />Delete</button>
        </>}>
        {p.description ? <p style={{ whiteSpace: 'pre-wrap' }}>{p.description}</p> : <p className="faint">No description.</p>}
      </Card>

      <div className="grid cols-2">
        <Card title={`Saved models (${p.saved_list.length})`} subtitle="Every save keeps a version you can restore">
          {p.saved_list.length === 0 ? <p className="muted">Use <b>Save</b> on the DCF, Scenarios, Budgeting, Statements, Cash Flow, Variance or Ratios pages while this project is active.</p> : (
            <div className="list">
              {p.saved_list.map((s) => {
                const [route, label] = KIND_ROUTE[s.kind] ?? ['/', s.kind];
                return (
                  <Link key={s.id} to={`${route}?saved=${s.id}`} className="list-item" style={{ color: 'inherit', textDecoration: 'none' }} onClick={() => activeId !== id && setActive(id)}>
                    <Layers size={16} className="pos" />
                    <div className="grow"><div className="truncate" style={{ fontWeight: 550 }}>{s.name}</div><div className="faint" style={{ fontSize: 12 }}>{label} · v{s.latest_version} · {when(s.updated_at)}</div></div>
                    <span className="pos" style={{ fontSize: 12.5 }}>Open</span>
                  </Link>
                );
              })}
            </div>
          )}
        </Card>
        <Card title={`Files (${p.upload_list.length})`} subtitle="Uploaded while this project was active">
          {p.upload_list.length === 0 ? <p className="muted">No files yet. <Link to="/upload" onClick={() => activeId !== id && setActive(id)}>Upload to this project</Link>.</p> : (
            <div className="list">
              {p.upload_list.map((u) => (
                <Link key={u.id} to={`/upload?file=${u.id}`} className="list-item" style={{ color: 'inherit', textDecoration: 'none' }} onClick={() => activeId !== id && setActive(id)}>
                  <FileText size={16} className={u.status === 'failed' ? 'neg' : 'pos'} />
                  <div className="grow"><div className="truncate" style={{ fontWeight: 550 }}>{u.name}</div>
                    <div className="faint" style={{ fontSize: 12 }}>{fmtBytes(u.size)} · deleted automatically on {new Date(u.expires_at).toLocaleDateString()}</div></div>
                </Link>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Card title="History" subtitle="Analysis and file activity in this project">
        {act.loading && !act.data ? <Skeleton h={60} /> : act.data?.activity.length ? (
          <ul className="timeline">
            {act.data.activity.map((a, i) => (
              <li key={i}><div><b>{a.label}</b>{typeof a.detail.name === 'string' && <> — {a.detail.name}</>}{typeof a.detail.version === 'number' && <> (v{a.detail.version})</>}
                <div className="faint" style={{ fontSize: 12 }}>{when(a.created_at)}</div></div></li>
            ))}
          </ul>
        ) : <p className="muted">No activity yet.</p>}
      </Card>

      <Modal open={editing} onClose={() => setEditing(false)} title="Edit project"
        footer={<><button className="btn" onClick={() => setEditing(false)}>Cancel</button><button className="btn primary" disabled={!form.name.trim()} onClick={() => patch(form, 'Project updated')}>Save</button></>}>
        <div className="stack">
          <Field label="Name"><input className="input" maxLength={80} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <Field label="Description"><textarea className="input" rows={3} style={{ fontFamily: 'var(--font-sans)' }} maxLength={2000} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
          <div className="grid cols-2">
            <Field label="Currency"><select className="input" value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })}>{CURRENCIES.map((c) => <option key={c}>{c}</option>)}</select></Field>
            <Field label="Units"><select className="input" value={form.units} onChange={(e) => setForm({ ...form, units: e.target.value })}>{UNIT_SCALES.map((u) => <option key={u}>{u}</option>)}</select></Field>
          </div>
        </div>
      </Modal>

      <Modal open={confirmName !== null} onClose={() => setConfirmName(null)} title="Delete project"
        footer={<><button className="btn" onClick={() => setConfirmName(null)}>Cancel</button><button className="btn primary" style={{ background: 'var(--negative)', borderColor: 'var(--negative)' }} disabled={confirmName !== p.name} onClick={del}>Delete permanently</button></>}>
        <div className="stack">
          <Callout tone="error">This permanently deletes <b>{p.saved_list.length} saved models</b> (all versions) and <b>{p.upload_list.length} uploaded files</b> in this project. History entries are kept without the project link. Consider <b>Export</b> first.</Callout>
          <Field label={<>Type <b>{p.name}</b> to confirm</>}><input className="input" value={confirmName ?? ''} onChange={(e) => setConfirmName(e.target.value)} /></Field>
        </div>
      </Modal>
    </div>
  );
}
