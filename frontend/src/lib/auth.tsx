import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api, UNAUTHORIZED_EVENT } from './api';

/** Working drafts kept in this browser. They are cleared on sign-out and when a different
 *  user signs in, so people sharing a computer never see each other's unsaved models. */
const DRAFT_KEYS = ['fis.dcf', 'fis.scenarios', 'fis.budgets', 'fis.statements', 'fis.cashbudget', 'fis.variance.import'];
function clearDrafts() {
  try { DRAFT_KEYS.forEach((k) => localStorage.removeItem(k)); } catch { /* storage unavailable */ }
}
function rememberUser(id: string) {
  try {
    if (localStorage.getItem('fis.lastUser') !== id) { clearDrafts(); localStorage.setItem('fis.lastUser', id); }
  } catch { /* storage unavailable */ }
}

export interface User { id: string; email: string; display_name: string; created_at: string; retention_days: number; session_days: number }
interface Ctx {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, display_name: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  expired: boolean;
}
const AuthContext = createContext<Ctx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [expired, setExpired] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const u = await api.get<User>('/api/auth/me');
      rememberUser(u.id);
      setUser(u);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    const on = () => setUser((u) => { if (u) setExpired(true); return null; });
    window.addEventListener(UNAUTHORIZED_EVENT, on);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, on);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const u = await api.post<User>('/api/auth/login', { email, password });
    rememberUser(u.id);
    setUser(u);
    setExpired(false);
  }, []);
  const register = useCallback(async (email: string, password: string, display_name: string) => {
    const u = await api.post<User>('/api/auth/register', { email, password, display_name });
    rememberUser(u.id);
    setUser(u);
    setExpired(false);
  }, []);
  const logout = useCallback(async () => {
    try { await api.post('/api/auth/logout', {}); } catch { /* already signed out */ }
    clearDrafts();
    setUser(null);
  }, []);

  const value = useMemo(() => ({ user, loading, login, register, logout, refresh, expired }), [user, loading, login, register, logout, refresh, expired]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const c = useContext(AuthContext);
  if (!c) throw new Error('useAuth outside provider');
  return c;
}
