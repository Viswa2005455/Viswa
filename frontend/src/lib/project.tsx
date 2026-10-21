import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api } from './api';
import { useAuth } from './auth';
import { loadRaw, save } from './storage';

export interface Project {
  id: string; name: string; description: string; currency: string; units: string; archived: boolean;
  created_at: string; updated_at: string; uploads: number; saved_items: number;
}
interface Ctx {
  projects: Project[];
  active: Project | null;
  activeId: string | null;
  setActive: (id: string | null) => void;
  reload: () => Promise<void>;
}
const ProjectContext = createContext<Ctx | null>(null);

/** The active project scopes uploads and saved models. It is remembered per user in this browser. */
export function ProjectProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const key = user ? `fis.activeProject.${user.id}` : '';
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!user) return;
    try {
      const r = await api.get<{ projects: Project[] }>('/api/projects');
      setProjects(r.projects);
      setActiveId((cur) => (cur && r.projects.some((p) => p.id === cur) ? cur : null));
    } catch { /* handled by auth */ }
  }, [user]);

  useEffect(() => {
    if (!user) { setProjects([]); setActiveId(null); return; }
    setActiveId(loadRaw<string | null>(key, null));
    reload();
  }, [user, key, reload]);

  const setActive = useCallback((id: string | null) => { setActiveId(id); if (key) save(key, id); }, [key]);
  const active = projects.find((p) => p.id === activeId) ?? null;
  const value = useMemo(() => ({ projects, active, activeId: active?.id ?? null, setActive, reload }), [projects, active, setActive, reload]);
  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

export function useProjects() {
  const c = useContext(ProjectContext);
  if (!c) throw new Error('useProjects outside provider');
  return c;
}
