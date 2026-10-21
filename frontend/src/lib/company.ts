import { useEffect, useState } from 'react';
import { api } from './api';
import { loadRaw } from './storage';

/** Statement data as saved by the Financial Statements page. */
export interface StatementData {
  periods: string[]; lines: { label: string; statement: string; key: string | null; values: (number | null)[]; source?: string | null }[];
  company?: string; units?: string; market?: Record<string, (number | null)[]>;
}
export interface CompanyData { periods: string[]; items: Record<string, (number | null)[]> }
export interface CompanySource { id: string; name: string; isExample: boolean; load: () => Promise<StatementData> }

/** Lines mapped to a standard item become engine inputs; unmapped lines are ignored. */
export function toCompany(d: StatementData): CompanyData {
  const items: Record<string, (number | null)[]> = {};
  const clean = (vs: (number | null)[]) => vs.map((v) => (typeof v === 'number' && Number.isFinite(v) ? v : null));
  for (const l of d.lines) if (l.key) items[l.key] = clean(l.values);
  for (const [k, vs] of Object.entries(d.market ?? {})) if (vs.length === d.periods.length) items[k] = clean(vs);
  return { periods: d.periods, items };
}

/** The data currently open on the Financial Statements page, plus every saved statements model. */
export function useCompanySources() {
  const [sources, setSources] = useState<CompanySource[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const current = loadRaw<{ data: StatementData; isExample: boolean } | null>('fis.statements', null);
    const list: CompanySource[] = [];
    const addCurrent = () => {
      if (!current?.data?.periods?.length) return;
      const name = current.isExample ? 'Financial Statements page (example data)'
        : current.data.company ? `${current.data.company} (open on Financial Statements, unsaved)` : 'Financial Statements page (unsaved)';
      list.push({ id: 'current', name, isExample: !!current.isExample, load: async () => current.data });
    };
    api.get<{ items: { id: string; name: string }[] }>('/api/saved?kind=statements')
      .then((r) => {
        for (const it of r.items) list.push({ id: it.id, name: it.name, isExample: false,
          load: async () => (await api.get<{ data: StatementData }>(`/api/saved/${it.id}`)).data });
        addCurrent();
        setSources([...list]);
      })
      .catch((e) => { setError((e as Error).message); addCurrent(); setSources([...list]); });
  }, []);
  return { sources, error };
}
