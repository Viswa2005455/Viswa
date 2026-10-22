import { Download, KeyRound, LogOut, MonitorSmartphone, Trash2, UserX } from 'lucide-react';
import { useState } from 'react';
import { Modal } from '../components/Modal';
import { useAuth } from '../lib/auth';
import { useProjects } from '../lib/project';
import { downloadFile } from '../lib/format';
import { Callout, Card, Field, PageHeader, Skeleton, Tabs } from '../components/ui';
import { api } from '../lib/api';
import { CURRENCIES, UNIT_SCALES, type Currency, type NumberStyle, type UnitScale } from '../lib/format';
import { useSettings, type ThemePref } from '../lib/settings';
import { useToast } from '../lib/toast';
import { useAsync } from '../lib/useApi';

export function SettingsPage() {
  const { settings, update } = useSettings();
  const ai = useAsync((signal) => api.get<{ configured: boolean; provider: string; message: string }>('/api/ai/status', { signal }), []);
  const health = useAsync((signal) => api.get<{ version: string; environment: string }>('/api/health', { signal }), []);
  const { user } = useAuth();

  return (
    <div className="page">
      <PageHeader title="Settings" subtitle="Account and security, privacy and data controls, appearance and display defaults." />
      <div className="grid cols-2">
        <Card title="Appearance">
          <div className="stack">
            <Field label="Theme">
              <Tabs label="Theme" value={settings.theme} onChange={(v: ThemePref) => update({ theme: v })}
                options={[{ value: 'system', label: 'System' }, { value: 'dark', label: 'Dark' }, { value: 'light', label: 'Light' }]} />
            </Field>
            <label className="row" style={{ fontSize: 13 }}>
              <input type="checkbox" checked={settings.reduceMotion} onChange={(e) => update({ reduceMotion: e.target.checked })} />
              Reduce motion (animations are also reduced automatically when your OS asks for it)
            </label>
            <label className="row" style={{ fontSize: 13 }}>
              <input type="checkbox" checked={settings.learningMode} onChange={(e) => update({ learningMode: e.target.checked })} />
              Learning mode — show formula explanations on analysis pages
            </label>
          </div>
        </Card>
        <Card title="Display defaults">
          <div className="form-grid">
            <Field label="Currency">
              <select className="input" value={settings.currency} onChange={(e) => update({ currency: e.target.value as Currency })}>
                {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
              </select>
            </Field>
            <Field label="Unit label for your models">
              <select className="input" value={settings.units} onChange={(e) => update({ units: e.target.value as UnitScale })}>
                {UNIT_SCALES.map((u) => <option key={u}>{u}</option>)}
              </select>
            </Field>
            <Field label="Number style" hint="How digits are grouped">
              <select className="input" value={settings.numberStyle} onChange={(e) => update({ numberStyle: e.target.value as NumberStyle })}>
                <option value="auto">Automatic (Indian for INR)</option>
                <option value="indian">Indian — 1,23,45,678</option>
                <option value="international">International — 12,345,678</option>
              </select>
            </Field>
          </div>
          <p className="faint mt" style={{ fontSize: 12.5 }}>The currency setting changes labels only. It never converts values — no exchange rates are applied.</p>
        </Card>
        <Card title="AI provider">
          {ai.loading ? <Skeleton h={40} /> : ai.data && (
            <Callout tone={ai.data.configured ? 'success' : 'info'} title={ai.data.configured ? `Configured: ${ai.data.provider}` : 'Not configured'}>{ai.data.message}</Callout>
          )}
          <p className="faint mt" style={{ fontSize: 12.5 }}>Configure on the server in <code>backend/.env</code>. Keys are never stored in the browser.</p>
        </Card>
        <AccountCard />
        <SessionsCard />
        <DataCard retentionDays={user?.retention_days ?? 90} />
        <Card title="About" className="span-all">
          <div className="metric-row"><span>Backend</span><span className="v">{health.data ? `v${health.data.version} · ${health.data.environment}` : health.error ? 'offline' : '…'}</span></div>
          <div className="metric-row"><span>Calculation conventions</span><span className="v" style={{ fontWeight: 400 }}>Rates as decimals internally · CF₀ undiscounted · end-of-period discounting unless mid-year is chosen</span></div>
          <div className="metric-row"><span>Disclaimer</span><span className="v" style={{ fontWeight: 400 }}>Educational and analytical tool — not investment advice.</span></div>
        </Card>
      </div>
    </div>
  );
}

function AccountCard() {
  const { user } = useAuth();
  const toast = useToast();
  const [cur, setCur] = useState('');
  const [next, setNext] = useState('');
  const [busy, setBusy] = useState(false);
  const change = async () => {
    setBusy(true);
    try {
      await api.post('/api/auth/change-password', { current_password: cur, new_password: next });
      toast('Password changed. Other devices were signed out.');
      setCur(''); setNext('');
    } catch (e) { toast((e as Error).message, 'error'); } finally { setBusy(false); }
  };
  return (
    <Card title="Account" actions={<KeyRound size={17} className="faint" />}>
      <div className="metric-row"><span>Name</span><span className="v">{user?.display_name}</span></div>
      <div className="metric-row"><span>Email</span><span className="v">{user?.email}</span></div>
      <div className="metric-row"><span>Member since</span><span className="v">{user ? new Date(user.created_at).toLocaleDateString() : ''}</span></div>
      <div className="stack mt" style={{ gap: 10 }}>
        <div className="field-label">Change password</div>
        <input className="input" type="password" autoComplete="current-password" placeholder="Current password" aria-label="Current password" value={cur} onChange={(e) => setCur(e.target.value)} />
        <input className="input" type="password" autoComplete="new-password" placeholder="New password (10+ characters)" aria-label="New password" value={next} onChange={(e) => setNext(e.target.value)} />
        <button className="btn" disabled={busy || !cur || next.length < 10} onClick={change}>Change password</button>
      </div>
    </Card>
  );
}

interface SessionRow { id: string; created_at: string; last_seen_at: string; expires_at: string; user_agent: string | null; current: boolean }

function describeAgent(ua: string | null) {
  if (!ua) return 'Unknown device';
  const browser = /Edg\//.test(ua) ? 'Edge' : /Chrome\//.test(ua) ? 'Chrome' : /Firefox\//.test(ua) ? 'Firefox' : /Safari\//.test(ua) ? 'Safari' : 'Browser';
  const os = /Windows/.test(ua) ? 'Windows' : /Mac OS X/.test(ua) ? 'macOS' : /Android/.test(ua) ? 'Android' : /iPhone|iPad/.test(ua) ? 'iOS' : /Linux/.test(ua) ? 'Linux' : '';
  return `${browser}${os ? ` on ${os}` : ''}`;
}

function SessionsCard() {
  const toast = useToast();
  const { logout } = useAuth();
  const s = useAsync((signal) => api.get<{ sessions: SessionRow[] }>('/api/auth/sessions', { signal }), []);
  const others = (s.data?.sessions ?? []).filter((x) => !x.current).length;
  return (
    <Card title="Signed-in devices" actions={<MonitorSmartphone size={17} className="faint" />}>
      {s.loading && !s.data ? <Skeleton h={60} /> : (
        <div className="list">
          {s.data?.sessions.map((x) => (
            <div key={x.id} className="list-item">
              <div className="grow"><div style={{ fontWeight: 550 }}>{describeAgent(x.user_agent)} {x.current && <span className="badge accent">This device</span>}</div>
                <div className="faint" style={{ fontSize: 12 }}>Last active {new Date(x.last_seen_at).toLocaleString()} · expires {new Date(x.expires_at).toLocaleDateString()}</div></div>
            </div>
          ))}
        </div>
      )}
      <div className="row mt">
        <button className="btn sm" disabled={!others} onClick={async () => { const r = await api.post<{ revoked: number }>('/api/auth/sessions/revoke-others', {}); toast(`Signed out ${r.revoked} other device(s)`); s.reload(); }}>Sign out other devices</button>
        <button className="btn sm" onClick={logout}><LogOut size={14} />Sign out</button>
      </div>
    </Card>
  );
}

function DataCard({ retentionDays }: { retentionDays: number }) {
  const toast = useToast();
  const { reload, setActive } = useProjects();
  const [confirm, setConfirm] = useState<null | 'data' | 'account'>(null);
  const [password, setPassword] = useState('');
  const [typed, setTyped] = useState('');
  const [busy, setBusy] = useState(false);

  const exportAll = async () => {
    try {
      const data = await api.get<unknown>('/api/account/export');
      downloadFile(`finance-studio-export-${new Date().toISOString().slice(0, 10)}.json`, JSON.stringify(data, null, 2), 'application/json');
    } catch (e) { toast((e as Error).message, 'error'); }
  };
  const run = async () => {
    setBusy(true);
    try {
      if (confirm === 'data') {
        const r = await api.post<{ deleted_uploads: number }>('/api/account/delete-data', { password });
        toast(`All data deleted (${r.deleted_uploads} files)`);
        setActive(null);
        reload();
      } else {
        await api.post('/api/account/delete', { password });
        try { localStorage.clear(); } catch { /* ignore */ }
        location.assign('/');
      }
      setConfirm(null); setPassword(''); setTyped('');
    } catch (e) { toast((e as Error).message, 'error'); } finally { setBusy(false); }
  };

  return (
    <Card title="Privacy & your data" className="span-all">
      <div className="grid cols-2">
        <div className="stack" style={{ fontSize: 13 }}>
          <p><b>What is stored:</b> your account (email, name, scrypt password hash), projects, saved models with every version, uploaded files with their extracted analysis, and an activity history. Everything is private to your account.</p>
          <p><b>Retention:</b> uploaded files are deleted automatically <b>{retentionDays} days</b> after upload. Saved models and history are kept until you delete them. Expired sign-in sessions are removed automatically.</p>
          <p><b>External services:</b> nothing is sent to any AI or third-party service in this version.</p>
          <p><b>This browser:</b> unsaved working drafts are kept locally and cleared when you sign out.</p>
        </div>
        <div className="stack">
          <button className="btn" onClick={exportAll}><Download size={15} />Export all my data (JSON)</button>
          <button className="btn danger" onClick={() => setConfirm('data')}><Trash2 size={15} />Delete all my data (keep account)</button>
          <button className="btn danger" onClick={() => setConfirm('account')}><UserX size={15} />Delete my account permanently</button>
        </div>
      </div>
      <Modal open={confirm !== null} onClose={() => setConfirm(null)} title={confirm === 'account' ? 'Delete account' : 'Delete all data'}
        footer={<><button className="btn" onClick={() => setConfirm(null)}>Cancel</button>
          <button className="btn primary" style={{ background: 'var(--negative)', borderColor: 'var(--negative)' }} disabled={busy || !password || typed !== 'DELETE'} onClick={run}>Delete permanently</button></>}>
        <div className="stack">
          <Callout tone="error">{confirm === 'account'
            ? 'Your account, all projects, saved models, uploaded files and history will be permanently deleted. This cannot be undone.'
            : 'All projects, saved models, uploaded files and history will be permanently deleted. Your account stays.'} Export first if you want a copy.</Callout>
          <Field label="Your password"><input className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
          <Field label={<>Type <b>DELETE</b> to confirm</>}><input className="input" value={typed} onChange={(e) => setTyped(e.target.value)} /></Field>
        </div>
      </Modal>
    </Card>
  );
}
