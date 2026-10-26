import { Menu, Moon, Sun, Activity, LogOut } from 'lucide-react';
import { Suspense, useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { NAV } from '../nav';
import { CURRENCIES, type Currency } from '../lib/format';
import { useSettings } from '../lib/settings';
import { api } from '../lib/api';
import { SkeletonCards } from './ui';
import { Background3D } from './Background3D';
import { useAuth } from '../lib/auth';
import { useProjects } from '../lib/project';

export function Layout() {
  const [open, setOpen] = useState(false);
  const { settings, update, resolvedTheme } = useSettings();
  const loc = useLocation();
  const current = NAV.find((n) => (n.to === '/' ? loc.pathname === '/' : loc.pathname === n.to || loc.pathname.startsWith(`${n.to}/`)));
  const [apiOk, setApiOk] = useState<boolean | null>(null);
  const { user, logout } = useAuth();
  const { projects, activeId, setActive } = useProjects();
  const navigate = useNavigate();

  useEffect(() => { setOpen(false); window.scrollTo(0, 0); }, [loc.pathname]);
  useEffect(() => {
    document.title = `${current?.label ?? 'Not found'} · Finance Intelligence Studio`;
  }, [current]);
  useEffect(() => {
    let alive = true;
    const check = () => api.get('/api/health').then(() => alive && setApiOk(true)).catch(() => alive && setApiOk(false));
    check();
    const t = setInterval(check, 30000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  let lastGroup = '';
  return (
    <div className={`shell ${open ? 'nav-open' : ''}`}>
      <Background3D />
      <aside className="sidebar" aria-label="Main navigation">
        <div className="brand">
          <div className="brand-mark"><Activity size={19} strokeWidth={2.5} /></div>
          <div>
            <div className="brand-name">Finance Intelligence</div>
            <div className="brand-sub">Studio</div>
          </div>
        </div>
        <nav className="nav">
          {NAV.map((n) => {
            const header = n.group !== lastGroup ? <div className="nav-group" key={`g-${n.group}`}>{n.group}</div> : null;
            lastGroup = n.group;
            return [
              header,
              <NavLink key={n.to} to={n.to} end={n.to === '/'} title={n.ready ? undefined : 'Under development'}>
                <n.icon size={17} />
                <span>{n.label}</span>
                {!n.ready && <span className="dev-dot" aria-label="under development" />}
              </NavLink>,
            ];
          })}
        </nav>
        <div className="sidebar-foot">
          <div className="api-pill">
            <span className={`status-dot ${apiOk ? 'ok' : apiOk === false ? 'bad' : ''}`} />
            {apiOk === null ? 'Checking API…' : apiOk ? 'API connected' : 'API offline'}
          </div>
          {user && (
            <div className="user-chip">
              <div className="avatar" aria-hidden="true">{user.display_name.slice(0, 1).toUpperCase()}</div>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div className="truncate who">{user.display_name}</div>
                <div className="truncate mail">{user.email}</div>
              </div>
              <button className="btn icon sm ghost" aria-label="Sign out" title="Sign out" onClick={logout}><LogOut size={16} /></button>
            </div>
          )}
        </div>
      </aside>
      <div className="scrim" onClick={() => setOpen(false)} />
      <div className="main">
        <header className="topbar">
          <button className="btn icon ghost menu-btn" aria-label="Open navigation" onClick={() => setOpen(true)}><Menu size={20} /></button>
          <div className="topbar-title">
            {current && <><span className="crumb hide-sm">{current.group}</span><span className="crumb-sep hide-sm" aria-hidden="true">/</span></>}
            <span className="here">{current?.label ?? 'Not found'}</span>
          </div>
          <div className="topbar-spacer" />
          <div className="topbar-controls">
            <select className="input compact project-select" aria-label="Active project" value={activeId ?? ''}
              onChange={(e) => { if (e.target.value === '__manage') navigate('/projects'); else setActive(e.target.value || null); }}>
              <option value="">No project selected</option>
              {projects.filter((p) => !p.archived || p.id === activeId).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              <option value="__manage">Manage projects…</option>
            </select>
            <label className="hide-md row" style={{ gap: 6 }}>
              <span className="sr-only">Reporting period</span>
              <input className="input compact" type="month" style={{ width: 132 }} value={settings.periodFrom} aria-label="Period from"
                onChange={(e) => update({ periodFrom: e.target.value })} />
              <span className="faint">–</span>
              <input className="input compact" type="month" style={{ width: 132 }} value={settings.periodTo} aria-label="Period to"
                onChange={(e) => update({ periodTo: e.target.value })} />
            </label>
            <select className="input compact" style={{ width: 88 }} aria-label="Display currency" value={settings.currency}
              onChange={(e) => update({ currency: e.target.value as Currency })}>
              {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
            </select>
            <button className="btn icon sm ghost" aria-label={`Switch to ${resolvedTheme === 'dark' ? 'light' : 'dark'} mode`}
              onClick={() => update({ theme: resolvedTheme === 'dark' ? 'light' : 'dark' })}>
              {resolvedTheme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
            </button>
          </div>
        </header>
        <main className="content" id="main">
          {settings.periodFrom > settings.periodTo && (
            <div className="callout error" style={{ marginBottom: 16 }}>The reporting period start is after its end. Please correct the date range.</div>
          )}
          <Suspense fallback={<SkeletonCards n={4} />}><Outlet /></Suspense>
        </main>
      </div>
    </div>
  );
}
