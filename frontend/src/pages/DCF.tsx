import { ArrowRight, RotateCcw } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, Cell, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { DCFAssumptions } from '../components/DCFInputs';
import { SaveLoad } from '../components/SaveLoad';
import { MonteCarlo, ReverseDCF, useMarketPrice } from '../components/ValuationRange';
import { C, ChartTooltip, Legend, axisProps, gridProps } from '../components/charts';
import { Badge, Callout, Card, ErrorBox, Formula, Kpi, LearnBox, NumberField, PageHeader, Warnings } from '../components/ui';
import { api } from '../lib/api';
import { useDCFModel } from '../lib/dcfModel';
import { fmtCompact, fmtMoney, fmtNum, fmtPct, isNum } from '../lib/format';
import { useSettings } from '../lib/settings';
import type { DCFResult } from '../lib/types';
import { useAsync, useDebounced } from '../lib/useApi';

export function DCF() {
  const { model, patch, reset, isExample, setModel } = useDCFModel();
  const { settings } = useSettings();
  const cur = settings.currency;
  const [marketPrice, setMarketPrice] = useMarketPrice();
  const req = useDebounced(model, 250);
  const res = useAsync(() => api.post<DCFResult>('/api/finance/dcf', req), [JSON.stringify(req)]);
  const r = res.data;
  const stale = res.error ? null : r;

  const rows: [string, (y: DCFResult['years'][number]) => string][] = [
    ['Revenue', (y) => fmtNum(y.revenue, 1)],
    ['Growth', (y) => fmtPct(y.revenue_growth, 1)],
    ['EBIT', (y) => fmtNum(y.ebit, 1)],
    ['EBIT margin', (y) => fmtPct(y.ebit_margin, 1)],
    ['− Taxes on EBIT', (y) => fmtNum(-y.taxes, 1)],
    ['= NOPAT', (y) => fmtNum(y.nopat, 1)],
    ['+ D&A', (y) => fmtNum(y.da, 1)],
    ['− CapEx', (y) => fmtNum(-y.capex, 1)],
    ['− Δ NWC', (y) => fmtNum(-y.delta_nwc, 1)],
    ['= FCFF', (y) => fmtNum(y.fcff, 1)],
    ['Discount period', (y) => fmtNum(y.discount_period, 1)],
    ['Discount factor', (y) => fmtNum(y.discount_factor, 4)],
    ['PV of FCFF', (y) => fmtNum(y.pv_fcff, 1)],
  ];

  const bridge = stale ? [
    { name: 'PV of FCFF', value: stale.sum_pv_fcff },
    { name: 'PV of terminal value', value: stale.pv_terminal_value },
    { name: 'Enterprise value', value: stale.enterprise_value, total: true },
    { name: 'Less net debt', value: -stale.net_debt },
    { name: 'Equity value', value: stale.equity_value, total: true },
  ] : [];

  return (
    <div className="page">
      <PageHeader title="DCF Valuation" badge={isExample ? <Badge tone="sample">Example assumptions</Badge> : <Badge tone="accent">Your assumptions</Badge>}
        subtitle="Unlevered free cash flow (FCFF) model. These assumptions are shared with Scenario Planning and Sensitivity Analysis."
        actions={<>
          <SaveLoad kind="dcf" label="DCF model" getData={() => model} onLoad={(m) => setModel(m)} />
          <button className="btn" onClick={reset}><RotateCcw size={15} />Reset to example</button>
          <Link className="btn" to="/sensitivity">Sensitivity <ArrowRight size={15} /></Link>
        </>} />
      {isExample && <div style={{ marginBottom: 16 }}><Callout tone="warn">The default inputs are illustrative examples, not verified market data. Replace them with your own assumptions and sources.</Callout></div>}

      <div className="grid cols-3">
        <div className="stack">
          <Card title="Assumptions" subtitle="All currency inputs in the same currency and units">
            <DCFAssumptions model={model} patch={patch} />
          </Card>
          <WaccBuilder onUse={(w) => patch({ wacc: w })} />
        </div>

        <div className="span-2 stack">
          {res.error && <ErrorBox error={res.error} />}
          <div className="grid cols-4">
            <Kpi label="Enterprise value" value={stale ? fmtMoney(stale.enterprise_value, cur) : '—'} />
            <Kpi label="Equity value" value={stale ? fmtMoney(stale.equity_value, cur) : '—'} deltaTone="muted" delta={stale ? `Net debt ${fmtMoney(stale.net_debt, cur)}` : undefined} />
            <Kpi label="Value per share" value={stale && isNum(stale.value_per_share) ? fmtMoney(stale.value_per_share, cur, 2) : '—'} delta={!model.shares_outstanding ? 'Enter shares outstanding' : undefined} />
            <Kpi label="Terminal value share of EV" value={stale ? fmtPct(stale.terminal_value_share_of_ev, 1) : '—'}
              delta={stale ? (model.terminal_method === 'gordon' ? `Implied exit ${isNum(stale.implied_exit_multiple) ? fmtNum(stale.implied_exit_multiple, 1) + '×' : 'n/a'}` : `Implied g ${fmtPct(stale.implied_terminal_growth, 2)}`) : undefined} />
          </div>
          {stale && <Warnings items={stale.warnings} />}

          {stale && (
            <div className="grid cols-2">
              <Card title="Free cash flow to the firm" subtitle="FCFF and its present value by year">
                <div className="chart">
                  <ResponsiveContainer>
                    <ComposedChart data={stale.years} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid {...gridProps} />
                      <XAxis dataKey="year" {...axisProps} tickFormatter={(y) => `Y${y}`} />
                      <YAxis {...axisProps} width={52} tickFormatter={(v) => fmtCompact(v, cur)} />
                      <Tooltip cursor={{ fill: 'var(--bg-hover)' }} content={<ChartTooltip labelFormat={(l) => `Year ${l}`} format={(v) => fmtMoney(v, cur, 1)} />} />
                      <Bar dataKey="fcff" name="FCFF" fill={C.c1} radius={[4, 4, 0, 0]} maxBarSize={34} />
                      <Line dataKey="pv_fcff" name="PV of FCFF" stroke={C.c2} strokeWidth={2.2} dot={{ r: 3 }} />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
                <Legend items={[{ label: 'FCFF', color: 'var(--chart-1)' }, { label: 'Present value', color: 'var(--chart-2)' }]} />
              </Card>
              <Card title="Valuation bridge" subtitle="From discounted cash flows to equity value">
                <div className="chart">
                  <ResponsiveContainer>
                    <BarChart data={bridge} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
                      <CartesianGrid {...gridProps} horizontal={false} vertical />
                      <XAxis type="number" {...axisProps} tickFormatter={(v) => fmtCompact(v, cur)} />
                      <YAxis type="category" dataKey="name" {...axisProps} width={130} />
                      <Tooltip cursor={{ fill: 'var(--bg-hover)' }} content={<ChartTooltip format={(v) => fmtMoney(v, cur, 1)} />} />
                      <Bar dataKey="value" name="Value" radius={4} maxBarSize={26}>
                        {bridge.map((b) => <Cell key={b.name} fill={b.total ? C.c3 : b.value < 0 ? C.neg : C.c1} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Card>
            </div>
          )}

          {stale && (
            <Card title="Projection" subtitle={`Discounting at WACC ${fmtPct(model.wacc, 2)}, ${model.mid_year ? 'mid-year' : 'end-of-year'} convention`} flush>
              <div className="table-wrap" style={{ border: 0, borderTop: '1px solid var(--border)', borderRadius: 0 }}>
                <table className="data">
                  <thead><tr><th>Line item</th>{stale.years.map((y) => <th key={y.year} className="r">Year {y.year}</th>)}</tr></thead>
                  <tbody>
                    {rows.map(([label, f]) => (
                      <tr key={label} style={label.startsWith('=') ? { fontWeight: 650 } : undefined}>
                        <td>{label}</td>{stale.years.map((y) => <td key={y.year} className="r">{f(y)}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="grid cols-2" style={{ padding: 18 }}>
                <div>
                  <div className="metric-row"><span>Sum of PV of FCFF</span><span className="v">{fmtMoney(stale.sum_pv_fcff, cur, 1)}</span></div>
                  <div className="metric-row"><span>Terminal value (Year {stale.years.length})</span><span className="v">{fmtMoney(stale.terminal_value, cur, 1)}</span></div>
                  <div className="metric-row"><span>PV of terminal value</span><span className="v">{fmtMoney(stale.pv_terminal_value, cur, 1)}</span></div>
                  <div className="metric-row"><span>Enterprise value</span><span className="v">{fmtMoney(stale.enterprise_value, cur, 1)}</span></div>
                  <div className="metric-row"><span>− Debt + Cash</span><span className="v">{fmtMoney(-stale.net_debt, cur, 1)}</span></div>
                  <div className="metric-row"><span><b>Equity value</b></span><span className="v">{fmtMoney(stale.equity_value, cur, 1)}</span></div>
                </div>
                <Formula>{`FCFF = EBIT × (1 − T) + D&A − CapEx − ΔNWC
${model.terminal_method === 'gordon'
  ? `TV = FCFFₙ × (1 + g) / (WACC − g)\n   = ${fmtNum(stale.years[stale.years.length - 1].fcff, 2)} × (1 + ${fmtPct(model.terminal_growth, 2)}) / (${fmtPct(model.wacc, 2)} − ${fmtPct(model.terminal_growth, 2)})`
  : `TV = EBITDAₙ × multiple = ${fmtNum(stale.years[stale.years.length - 1].ebitda, 2)} × ${model.exit_multiple}`}
   = ${fmtNum(stale.terminal_value, 2)}
PV(TV) = TV / (1 + WACC)^${stale.years.length}
EV = Σ PV(FCFF) + PV(TV)
Equity = EV − Debt + Cash`}</Formula>
              </div>
            </Card>
          )}

          {stale && <ReverseDCF model={model} price={marketPrice} setPrice={setMarketPrice} />}
          {stale && <MonteCarlo model={model} price={marketPrice} />}

          <LearnBox title="Discounted cash flow valuation">
            <div className="stack" style={{ fontSize: 13 }}>
              <p>A DCF values a business as the present value of the cash it will generate for all capital providers (FCFF), discounted at the blended required return (WACC).</p>
              <p><b>Consistency:</b> FCFF (unlevered) pairs with WACC; free cash flow to equity pairs with the cost of equity. Nominal cash flows need a nominal discount rate.</p>
              <p><b>Terminal value</b> often exceeds 60–80% of EV. Keep g at or below long-run nominal GDP growth, and always check that WACC &gt; g.</p>
              <p><b>Reverse DCF</b> turns the question around: instead of "what is it worth?", it asks "what growth does today's price assume?" — then you judge whether that is realistic.</p>
              <p><b>Monte Carlo</b> runs the model thousands of times with assumptions drawn from ranges you choose. The P10–P90 band is a more honest answer than a single number.</p>
              <p><b>Common mistakes:</b> mixing currencies or units, double-counting cash, using book instead of market values in WACC weights, and forgetting the change in working capital.</p>
            </div>
          </LearnBox>
        </div>
      </div>
    </div>
  );
}

interface WACCRes { wacc: number; weight_equity: number; weight_debt: number; after_tax_cost_of_debt: number }

function WaccBuilder({ onUse }: { onUse: (w: number) => void }) {
  const [rf, setRf] = useState<number | null>(0.07);
  const [beta, setBeta] = useState<number | null>(1.1);
  const [rm, setRm] = useState<number | null>(0.13);
  const [e, setE] = useState<number | null>(2000);
  const [d, setD] = useState<number | null>(500);
  const [rd, setRd] = useState<number | null>(0.09);
  const [t, setT] = useState<number | null>(0.25);
  const ok = [rf, beta, rm, e, d, rd, t].every(isNum);
  const re = ok ? (rf as number) + (beta as number) * ((rm as number) - (rf as number)) : null;
  const req = useDebounced(ok ? { equity_value: e, debt_value: d, cost_of_equity: re, pre_tax_cost_of_debt: rd, tax_rate: t } : null, 250);
  const w = useAsync(() => api.post<WACCRes>('/api/finance/wacc', req), [JSON.stringify(req)], !!req);

  return (
    <Card title="WACC builder (CAPM)" subtitle="Example inputs — replace with sourced market data">
      <div className="form-grid">
        <NumberField label="Risk-free rate" percent value={rf} onChange={setRf} />
        <NumberField label="Beta" value={beta} onChange={setBeta} />
        <NumberField label="Expected market return" percent value={rm} onChange={setRm} />
        <NumberField label="Equity (market value)" value={e} onChange={setE} min={0} />
        <NumberField label="Debt (market value)" value={d} onChange={setD} min={0} />
        <NumberField label="Pre-tax cost of debt" percent value={rd} onChange={setRd} />
        <NumberField label="Tax rate" percent value={t} onChange={setT} />
      </div>
      {w.error && <div className="mt-sm"><ErrorBox error={w.error} /></div>}
      {w.data && isNum(re) && (
        <div className="mt">
          <Formula>{`Re = Rf + β(Rm − Rf) = ${fmtPct(rf, 2)} + ${beta} × ${fmtPct((rm as number) - (rf as number), 2)} = ${fmtPct(re, 2)}
WACC = E/V·Re + D/V·Rd(1 − T)
     = ${fmtPct(w.data.weight_equity, 1)} × ${fmtPct(re, 2)} + ${fmtPct(w.data.weight_debt, 1)} × ${fmtPct(w.data.after_tax_cost_of_debt, 2)}
     = ${fmtPct(w.data.wacc, 2)}`}</Formula>
          <button className="btn primary sm mt-sm" onClick={() => onUse(w.data!.wacc)}>Use {fmtPct(w.data.wacc, 2)} in the model</button>
        </div>
      )}
    </Card>
  );
}
