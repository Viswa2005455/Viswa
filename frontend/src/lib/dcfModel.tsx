import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { loadRaw, save } from './storage';
import type { DCFModel } from './types';

/**
 * The "working model" shared by DCF, Scenario Planning and Sensitivity Analysis so that all three
 * analyse the same assumptions. The defaults are clearly labelled example inputs, not market data.
 */
export const EXAMPLE_MODEL: DCFModel = {
  base_revenue: 1000,
  revenue_growth: [0.12, 0.11, 0.10, 0.08, 0.06],
  ebit_margin: [0.18, 0.185, 0.19, 0.195, 0.2],
  tax_rate: 0.25,
  da_pct_revenue: 0.04,
  capex_pct_revenue: 0.055,
  nwc_pct_revenue: 0.12,
  wacc: 0.11,
  terminal_growth: 0.04,
  terminal_method: 'gordon',
  exit_multiple: 10,
  debt: 300,
  cash: 120,
  shares_outstanding: 50,
  mid_year: false,
};

interface Ctx { model: DCFModel; setModel: (m: DCFModel) => void; patch: (p: Partial<DCFModel>) => void; reset: () => void; isExample: boolean }
const DCFContext = createContext<Ctx | null>(null);

export function DCFModelProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<{ model: DCFModel; isExample: boolean }>(() =>
    loadRaw('fis.dcf', { model: EXAMPLE_MODEL, isExample: true }));
  const persist = useCallback((s: { model: DCFModel; isExample: boolean }) => { save('fis.dcf', s); return s; }, []);
  const setModel = useCallback((m: DCFModel) => setState(persist({ model: m, isExample: false })), [persist]);
  const patch = useCallback((p: Partial<DCFModel>) => setState((s) => persist({ model: { ...s.model, ...p }, isExample: false })), [persist]);
  const reset = useCallback(() => setState(persist({ model: EXAMPLE_MODEL, isExample: true })), [persist]);
  const value = useMemo(() => ({ ...state, setModel, patch, reset }), [state, setModel, patch, reset]);
  return <DCFContext.Provider value={value}>{children}</DCFContext.Provider>;
}

export function useDCFModel() {
  const c = useContext(DCFContext);
  if (!c) throw new Error('useDCFModel outside provider');
  return c;
}
