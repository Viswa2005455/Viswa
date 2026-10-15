import { Activity, LockKeyhole, ShieldCheck } from 'lucide-react';
import { useEffect, useState, type FormEvent } from 'react';
import { Callout } from '../components/ui';
import { api } from '../lib/api';
import { useAuth } from '../lib/auth';

export function AuthScreen() {
  const { login, register, expired } = useAuth();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [registrationOpen, setRegistrationOpen] = useState(true);
  const [apiDown, setApiDown] = useState(false);

  useEffect(() => {
    api.get<{ registration_open: boolean }>('/api/auth/config')
      .then((c) => setRegistrationOpen(c.registration_open))
      .catch(() => setApiDown(true));
  }, []);
  useEffect(() => { document.title = `${mode === 'login' ? 'Sign in' : 'Create account'} · Finance Intelligence Studio`; }, [mode]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === 'login') await login(email, password);
      else await register(email, password, name);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-screen">
      <div className="app-bg" aria-hidden="true" />
      <div className="auth-wrap">
        <div className="auth-brand">
          <div className="brand-mark" style={{ width: 44, height: 44, borderRadius: 13 }}><Activity size={24} strokeWidth={2.5} /></div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 20 }}>Finance Intelligence Studio</div>
            <div className="muted">FP&amp;A, valuation and financial analysis</div>
          </div>
        </div>
        <form className="card auth-card" onSubmit={submit} noValidate>
          <h1 style={{ fontSize: 20 }}>{mode === 'login' ? 'Sign in' : 'Create your account'}</h1>
          <p className="muted" style={{ marginTop: 4 }}>{mode === 'login' ? 'Your projects, files and models are private to your account.' : 'Accounts keep each person\'s files and models separate.'}</p>
          {expired && mode === 'login' && <div className="mt"><Callout tone="info">Your session ended. Please sign in again.</Callout></div>}
          {apiDown && <div className="mt"><Callout tone="error" title="Cannot reach the server">Start the backend: <code>cd backend &amp;&amp; uv run uvicorn app.main:app --reload</code></Callout></div>}
          <div className="stack mt" style={{ gap: 12 }}>
            {mode === 'register' && (
              <div className="field"><label className="field-label" htmlFor="auth-name">Your name</label>
                <input id="auth-name" className="input" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} required maxLength={80} /></div>
            )}
            <div className="field"><label className="field-label" htmlFor="auth-email">Email</label>
              <input id="auth-email" className="input" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></div>
            <div className="field"><label className="field-label" htmlFor="auth-password">Password</label>
              <input id="auth-password" className="input" type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={password} onChange={(e) => setPassword(e.target.value)} required />
              {mode === 'register' && <div className="field-hint">At least 10 characters, not a common password, and not containing your email name.</div>}
            </div>
            {error && <Callout tone="error">{error}</Callout>}
            <button className="btn primary" type="submit" disabled={busy || !email || !password || (mode === 'register' && !name.trim())} style={{ height: 40 }}>
              <LockKeyhole size={16} />{busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}
            </button>
          </div>
          <div className="mt" style={{ textAlign: 'center', fontSize: 13 }}>
            {mode === 'login' ? (registrationOpen ? <>New here? <button type="button" className="link-btn" onClick={() => { setMode('register'); setError(null); }}>Create an account</button></> : <span className="faint">Registration is closed on this server.</span>)
              : <>Already have an account? <button type="button" className="link-btn" onClick={() => { setMode('login'); setError(null); }}>Sign in</button></>}
          </div>
        </form>
        <div className="auth-foot faint"><ShieldCheck size={14} /> Passwords are hashed with scrypt. Sessions use secure, HttpOnly cookies. Educational tool — not investment advice.</div>
      </div>
    </div>
  );
}
