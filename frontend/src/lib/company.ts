import { useEffect, useState } from 'react';
import { api } from './api';
import { loadRaw } from './storage';

/** Statement data as saved by the Financial Statements page. */
export interface StatementData { periods: string[]; lines: { label: string; statement: string; key: string | null; values: (number | null)[] }[] }
export interface CompanyData { periods: string[]; items: Record<string, (number | null)[]> }
export interface CompanySource { id: string; name: string; isExample: boolean; load: () => Promise<StatementData> }

/** Lines mapped to a standard item become engine inputs; unmapped lines are ignored. */
export function toCompany(d: StatementData): CompanyData {
  const items: Record<string, (number | null)[]> = {};
  for (const l of d.lines) if (l.key) items[l.key] = l.values.map((v) => (typeof v === 'number' && Number.isFinite(v) ? v : null));
  return { periods: d.periods, items };
}

/** The data currently open on the Financial Statements page, plus every saved statements model. */
export function useCompanySources() {
  const [sources, setSources] = useState<CompanySource[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const current = loadRaw<{ data: StatementData; isExample: boolean } | null>('fis.statements', null);
    const list: CompanySource[] = [];
    if (current?.data?.periods?.length) {
      list.push({ id: 'current', name: current.isExample ? 'Financial Statements page (example data)' : 'Financial Statements page (current)',
        isExample: !!current.isExample, load: async () => current.data });
    }
    api.get<{ items: { id: string; name: string }[] }>('/api/saved?kind=statements')
      .then((r) => {
        for (const it of r.items) list.push({ id: it.id, name: it.name, isExample: false,
          load: async () => (await api.get<{ data: StatementData }>(`/api/saved/${it.id}`)).data });
        setSources([...list]);
      })
      .catch((e) => { setError((e as Error).message); setSources([...list]); });
  }, []);
  return { sources, error };
}
