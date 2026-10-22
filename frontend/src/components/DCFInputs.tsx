import { Minus, Plus } from 'lucide-react';
import { Field, NumberField, Tabs } from './ui';
import type { DCFModel } from '../lib/types';

/** Assumption editor for the shared DCF working model. Rates are shown in % and stored as decimals. */
export function DCFAssumptions({ model, patch }: { model: DCFModel; patch: (p: Partial<DCFModel>) => void }) {
  const n = model.revenue_growth.length;
  const margins = model.ebit_margin.length === n ? model.ebit_margin : Array.from({ length: n }, (_, i) => model.ebit_margin[Math.min(i, model.ebit_margin.length - 1)]);

  const setYears = (k: number) => {
    if (k < 1 || k > 15) return;
    const ext = <T,>(arr: T[]) => (k <= arr.length ? arr.slice(0, k) : [...arr, ...Array(k - arr.length).fill(arr[arr.length - 1])]);
    patch({ revenue_growth: ext(model.revenue_growth), ebit_margin: ext(margins) });
  };
  const setArr = (key: 'revenue_growth' | 'ebit_margin', i: number, v: number | null) => {
    if (v === null) return;
    const base = key === 'ebit_margin' ? margins : model.revenue_growth;
    patch({ [key]: base.map((x, j) => (j === i ? v : x)) } as Partial<DCFModel>);
  };

  return (
    <div className="stack">
      <div className="form-grid">
        <NumberField required label="Base-year revenue" value={model.base_revenue} onChange={(v) => v !== null && patch({ base_revenue: v })} min={0} hint="Last actual year" />
        <NumberField required label="Tax rate" percent value={model.tax_rate} onChange={(v) => v !== null && patch({ tax_rate: v })} min={0} max={99.9} />
        <NumberField required label="D&A % revenue" percent value={model.da_pct_revenue} onChange={(v) => v !== null && patch({ da_pct_revenue: v })} />
        <NumberField required label="CapEx % revenue" percent value={model.capex_pct_revenue} onChange={(v) => v !== null && patch({ capex_pct_revenue: v })} />
        <NumberField required label="NWC % revenue" percent value={model.nwc_pct_revenue} onChange={(v) => v !== null && patch({ nwc_pct_revenue: v })} hint="ΔNWC = % × Δrevenue" />
        <NumberField required label="WACC" percent value={model.wacc} onChange={(v) => v !== null && patch({ wacc: v })} />
      </div>

      <div>
        <div className="row between" style={{ marginBottom: 6 }}>
          <span className="field-label">Forecast years: {n}</span>
          <div className="row">
            <button className="btn icon sm" aria-label="Remove a forecast year" onClick={() => setYears(n - 1)} disabled={n <= 1}><Minus size={14} /></button>
            <button className="btn icon sm" aria-label="Add a forecast year" onClick={() => setYears(n + 1)} disabled={n >= 15}><Plus size={14} /></button>
          </div>
        </div>
        <div className="table-wrap" tabIndex={0}>
          <table className="data">
            <thead><tr><th>Year</th><th>Revenue growth %</th><th>EBIT margin %</th></tr></thead>
            <tbody>
              {model.revenue_growth.map((g, i) => (
                <tr key={i}>
                  <td>Y{i + 1}</td>
                  <td style={{ minWidth: 110 }}><NumberField compact percent ariaLabel={`Revenue growth year ${i + 1}`} value={g} onChange={(v) => setArr('revenue_growth', i, v)} /></td>
                  <td style={{ minWidth: 110 }}><NumberField compact percent ariaLabel={`EBIT margin year ${i + 1}`} value={margins[i]} onChange={(v) => setArr('ebit_margin', i, v)} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <Field label="Terminal value method">
        <Tabs label="Terminal value method" value={model.terminal_method} onChange={(v) => patch({ terminal_method: v })}
          options={[{ value: 'gordon', label: 'Gordon growth' }, { value: 'exit_multiple', label: 'Exit multiple' }]} />
      </Field>
      <div className="form-grid">
        {model.terminal_method === 'gordon'
          ? <NumberField required label="Terminal growth (g)" percent value={model.terminal_growth} onChange={(v) => v !== null && patch({ terminal_growth: v })} hint="Must be below WACC" />
          : <NumberField required label="Exit EV/EBITDA multiple" suffix="×" value={model.exit_multiple} onChange={(v) => patch({ exit_multiple: v })} min={0} />}
        <NumberField required label="Debt" value={model.debt} onChange={(v) => v !== null && patch({ debt: v })} min={0} />
        <NumberField required label="Cash" value={model.cash} onChange={(v) => v !== null && patch({ cash: v })} min={0} />
        <NumberField label="Shares outstanding" value={model.shares_outstanding} onChange={(v) => patch({ shares_outstanding: v && v > 0 ? v : null })} hint="Optional" />
      </div>
      <label className="row" style={{ fontSize: 13 }}>
        <input type="checkbox" checked={model.mid_year} onChange={(e) => patch({ mid_year: e.target.checked })} />
        Mid-year discounting convention
      </label>
    </div>
  );
}
