import { Trash2 } from 'lucide-react';
import { Callout, Card, Field, PageHeader, Skeleton, Tabs } from '../components/ui';
import { api } from '../lib/api';
import { CURRENCIES, UNIT_SCALES, type Currency, type UnitScale } from '../lib/format';
import { useSettings, type ThemePref } from '../lib/settings';
import { useToast } from '../lib/toast';
import type { UploadSummary } from '../lib/types';
import { useAsync } from '../lib/useApi';

export function SettingsPage() {
  const { settings, update } = useSettings();
  const toast = useToast();
  const ai = useAsync(() => api.get<{ configured: boolean; provider: string; message: string }>('/api/ai/status'), []);
  const health = useAsync(() => api.get<{ version: string; environment: string }>('/api/health'), []);
  const uploads = useAsync(() => api.get<{ uploads: UploadSummary[] }>('/api/uploads'), []);

  const deleteAll = async () => {
    const list = uploads.data?.uploads ?? [];
    if (!list.length || !confirm(`Delete all ${list.length} uploaded files and their analyses? This cannot be undone.`)) return;
    await Promise.all(list.map((u) => api.del(`/api/uploads/${u.id}`).catch(() => null)));
    uploads.reload();
    toast('All uploads deleted');
  };
  const clearLocal = () => {
    if (!confirm('Reset saved DCF assumptions, scenarios and preferences stored in this browser?')) return;
    try { ['fis.dcf', 'fis.scenarios', 'fis.settings'].forEach((k) => localStorage.removeItem(k)); } catch { /* ignore */ }
    location.reload();
  };

  return (
    <div className="page">
      <PageHeader title="Settings" subtitle="Appearance, display defaults, accessibility, AI provider status and data controls." />
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
          </div>
          <p className="faint mt" style={{ fontSize: 12.5 }}>The currency setting changes labels only. It never converts values — no exchange rates are applied.</p>
        </Card>
        <Card title="AI provider">
          {ai.loading ? <Skeleton h={40} /> : ai.data && (
            <Callout tone={ai.data.configured ? 'success' : 'info'} title={ai.data.configured ? `Configured: ${ai.data.provider}` : 'Not configured'}>{ai.data.message}</Callout>
          )}
          <p className="faint mt" style={{ fontSize: 12.5 }}>Configure on the server in <code>backend/.env</code>. Keys are never stored in the browser.</p>
        </Card>
        <Card title="Your data">
          <div className="stack">
            <p style={{ fontSize: 13 }}>
              Uploads are stored on the server running this app (<code>backend/storage/</code>) until you delete them. Models, scenarios and
              preferences are stored in this browser only. Accounts and per-user isolation arrive in Phase 7.
            </p>
            <div className="row">
              <button className="btn danger" onClick={deleteAll} disabled={!uploads.data?.uploads.length}><Trash2 size={15} />Delete all uploads ({uploads.data?.uploads.length ?? 0})</button>
              <button className="btn" onClick={clearLocal}>Reset browser data</button>
            </div>
          </div>
        </Card>
        <Card title="About" className="span-all">
          <div className="metric-row"><span>Backend</span><span className="v">{health.data ? `v${health.data.version} · ${health.data.environment}` : health.error ? 'offline' : '…'}</span></div>
          <div className="metric-row"><span>Calculation conventions</span><span className="v" style={{ fontWeight: 400 }}>Rates as decimals internally · CF₀ undiscounted · end-of-period discounting unless mid-year is chosen</span></div>
          <div className="metric-row"><span>Disclaimer</span><span className="v" style={{ fontWeight: 400 }}>Educational and analytical tool — not investment advice.</span></div>
        </Card>
      </div>
    </div>
  );
}
