import { Download, Plus, RotateCcw, Trash2 } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Bar, CartesianGrid, ComposedChart, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, Cell } from 'recharts';
import { C, ChartTooltip, Legend, axisProps, gridProps } from '../components/charts';
import { Badge, Callout, Card, ErrorBox, Formula, Kpi, LearnBox, NumberField, PageHeader } from '../components/ui';
import { api } from '../lib/api';
import { downloadFile, fmtCompact, fmtMoney, fmtNum, fmtPct, isNum, toCSV } from '../lib/format';
import { useSettings } from '../lib/settings';
import { useAsync, useDebounced } from '../lib/useApi';

interface Appraisal {
  convention: string; npv: number; decision: string;
  irr: { status: string; values: number[]; sign_changes: number; message: string };
  mirr: { value: number | null; finance_rate: number; reinvest_rate: number; error: string | null };
  payback: { period: number | null; message: string }; discounted_payback: { period: number | null; message: string };
  profitability_index: { value: number | null; error: string | null }; eaa: number;
  timeline: { t: number; cash_flow: number; discount_factor: number; present_value: number; cumulative: number; cumulative_discounted: number }[];
  npv_profile: { rate: number; npv: number }[];
}

const EXAMPLE = { initial: 100000, flows: [30000, 35000, 40000, 30000, 20000] as (number | null)[], rate: 0.1 };

export function Investment() {
  const { settings } = useSettings();
  const cur = settings.currency;
  const [initial, setInitial] = useState<number | null>(EXAMPLE.initial);
  const [flows, setFlows] = useState<(number | null)[]>(EXAMPLE.flows);
  const [rate, setRate] = useState<number | null>(EXAMPLE.rate);
  const [finRate, setFinRate] = useState<number | null>(null);
  const [reRate, setReRate] = useState<number | null>(null);
  const [isExample, setIsExample] = useState(true);

  const missing = initial === null || rate === null || flows.some((f) => f === null);
  const body = useMemo(() => missing ? null : {
    cash_flows: [-(initial as number), ...(flows as number[])], discount_rate: rate, finance_rate: finRate, reinvest_rate: reRate,
  }, [initial, flows, rate, finRate, reRate, missing]);
  const req = useDebounced(body, 250);
  const res = useAsync(() => api.post<Appraisal>('/api/finance/appraisal', req), [JSON.stringify(req)], !!req);
  const r = res.data;

  const edit = <T,>(setter: (v: T) => void) => (v: T) => { setIsExample(false); setter(v); };
  const irrText = r ? r.irr.status === 'unique' ? fmtPct(r.irr.values[0]) : r.irr.status === 'multiple' ? 'Multiple' : 'None' : '—';

  const exportCsv = () => {
    if (!r || !req) return;
    const rows: unknown[][] = [['Investment appraisal', isExample ? 'EXAMPLE INPUTS' : 'User inputs'], ['Discount rate', req.discount_rate],
      ['Convention', r.convention], [], ['t', 'Cash flow', 'Discount factor', 'Present value', 'Cumulative', 'Cumulative discounted'],
      ...r.timeline.map((t) => [t.t, t.cash_flow, t.discount_factor, t.present_value, t.cumulative, t.cumulative_discounted]), [],
      ['NPV', r.npv], ['IRR', r.irr.status === 'unique' ? r.irr.values[0] : r.irr.message], ['MIRR', r.mirr.value ?? r.mirr.error],
      ['Payback (periods)', r.payback.period ?? 'Not recovered'], ['Discounted payback', r.discounted_payback.period ?? 'Not recovered'],
      ['Profitability index', r.profitability_index.value ?? r.profitability_index.error], ['EAA', r.eaa], ['Generated', new Date().toISOString()]];
    downloadFile('investment-appraisal.csv', toCSV(rows));
  };

  return (
    <div className="page">
      <PageHeader title="Investment Appraisal" badge={isExample ? <Badge tone="sample">Example inputs</Badge> : undefined}
        subtitle="NPV, IRR, MIRR, payback, discounted payback, profitability index and equivalent annual annuity, recalculated as you type."
        actions={<>
          <button className="btn" onClick={() => { setInitial(EXAMPLE.initial); setFlows(EXAMPLE.flows); setRate(EXAMPLE.rate); setFinRate(null); setReRate(null); setIsExample(true); }}><RotateCcw size={15} />Example</button>
          <button className="btn" onClick={exportCsv} disabled={!r}><Download size={15} />Export CSV</button>
        </>} />

      <div className="grid cols-3">
        <Card title="Inputs" subtitle="Periods are years unless your rate is per month. Rates in %.">
          <div className="stack">
            <NumberField label="Initial investment (t = 0)" hint="Enter as a positive amount; it is treated as an outflow." value={initial} onChange={edit(setInitial)} min={0} required />
            <NumberField label="Discount rate (per period)" percent value={rate} onChange={edit(setRate)} required min={-99} />
            <div className="grid cols-2" style={{ gap: 10 }}>
              <NumberField label="MIRR finance rate" percent value={finRate} onChange={edit(setFinRate)} hint="Blank = discount rate" />
              <NumberField label="MIRR reinvestment rate" percent value={reRate} onChange={edit(setReRate)} hint="Blank = discount rate" />
            </div>
            <div>
              <div className="field-label" style={{ marginBottom: 6 }}>Cash flows (t = 1 … n)</div>
              <div className="stack" style={{ gap: 6 }}>
                {flows.map((f, i) => (
                  <div key={i} className="row" style={{ flexWrap: 'nowrap' }}>
                    <span className="faint num" style={{ width: 34, fontSize: 12 }}>t={i + 1}</span>
                    <div style={{ flex: 1 }}>
                      <NumberField ariaLabel={`Cash flow year ${i + 1}`} compact value={f} required onChange={edit((v: number | null) => setFlows((fl) => fl.map((x, j) => (j === i ? v : x))))} />
                    </div>
                    <button className="btn icon sm ghost" aria-label={`Remove year ${i + 1}`} disabled={flows.length <= 1}
                      onClick={() => { setIsExample(false); setFlows((fl) => fl.filter((_, j) => j !== i)); }}><Trash2 size={14} /></button>
                  </div>
                ))}
              </div>
              <button className="btn sm mt-sm" disabled={flows.length >= 100} onClick={() => { setIsExample(false); setFlows((fl) => [...fl, null]); }}><Plus size={14} />Add period</button>
            </div>
            {missing && <Callout tone="warn">Fill in every cash flow and the discount rate. Blank values are not assumed to be zero.</Callout>}
          </div>
        </Card>

        <div className="span-2 stack">
          {res.error && <ErrorBox error={res.error} />}
          <div className="grid cols-4">
            <Kpi label="Net present value" value={r ? fmtMoney(r.npv, cur) : '—'} deltaTone={r && r.npv >= 0 ? 'pos' : 'neg'}
              delta={r ? (r.npv > 0 ? 'Accept' : r.npv < 0 ? 'Reject' : 'Indifferent') : undefined} />
            <Kpi label="IRR" value={irrText} delta={r && r.irr.status !== 'unique' ? r.irr.status === 'multiple' ? `${r.irr.values.map((v) => fmtPct(v, 1)).join(', ')}` : 'No valid IRR' : r && isNum(rate) ? (r.irr.values[0] > rate ? 'Above discount rate' : 'Below discount rate') : undefined}
              deltaTone={r && r.irr.status === 'unique' && isNum(rate) ? (r.irr.values[0] > rate ? 'pos' : 'neg') : 'muted'} />
            <Kpi label="MIRR" value={r?.mirr.value !== null && r ? fmtPct(r.mirr.value) : '—'} delta={r?.mirr.error ?? undefined} />
            <Kpi label="Profitability index" value={r && isNum(r.profitability_index.value) ? fmtNum(r.profitability_index.value, 3) : '—'} />
            <Kpi label="Payback" value={r ? (isNum(r.payback.period) ? `${fmtNum(r.payback.period, 2)} yrs` : 'Not recovered') : '—'} />
            <Kpi label="Discounted payback" value={r ? (isNum(r.discounted_payback.period) ? `${fmtNum(r.discounted_payback.period, 2)} yrs` : 'Not recovered') : '—'} />
            <Kpi label="Equivalent annual annuity" value={r ? fmtMoney(r.eaa, cur) : '—'} />
            <Kpi label="Sign changes" value={r ? String(r.irr.sign_changes) : '—'} delta={r ? (r.irr.sign_changes === 1 ? 'Conventional' : 'Unconventional') : undefined} />
          </div>

          {r && (
            <>
              <Callout tone={r.npv >= 0 ? 'success' : 'warn'} title={r.decision}>
                {r.irr.message} {r.payback.message !== 'Assumes cash flows arrive evenly within each period.' ? r.payback.message : ''}
              </Callout>
              <div className="grid cols-2">
                <Card title="Cash flow timeline" subtitle="Bars: cash flow · Line: cumulative discounted cash flow">
                  <div className="chart">
                    <ResponsiveContainer>
                      <ComposedChart data={r.timeline} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                        <CartesianGrid {...gridProps} />
                        <XAxis dataKey="t" {...axisProps} tickFormatter={(t) => `t${t}`} />
                        <YAxis {...axisProps} width={56} tickFormatter={(v) => fmtCompact(v, cur)} />
                        <Tooltip cursor={{ fill: 'var(--bg-hover)' }} content={<ChartTooltip labelFormat={(l) => `Period ${l}`} format={(v) => fmtMoney(v, cur)} />} />
                        <ReferenceLine y={0} stroke="var(--border-strong)" />
                        <Bar dataKey="cash_flow" name="Cash flow" radius={[4, 4, 0, 0]} maxBarSize={36}>
                          {r.timeline.map((t) => <Cell key={t.t} fill={t.cash_flow >= 0 ? C.c1 : C.neg} />)}
                        </Bar>
                        <Line dataKey="cumulative_discounted" name="Cumulative discounted" stroke={C.c2} strokeWidth={2.2} dot={{ r: 3 }} />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                </Card>
                <Card title="NPV profile" subtitle="NPV at different discount rates; it crosses zero at the IRR">
                  <div className="chart">
                    <ResponsiveContainer>
                      <LineChart data={r.npv_profile} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                        <CartesianGrid {...gridProps} />
                        <XAxis dataKey="rate" type="number" domain={['dataMin', 'dataMax']} {...axisProps} tickFormatter={(v) => fmtPct(v, 0)} />
                        <YAxis {...axisProps} width={56} tickFormatter={(v) => fmtCompact(v, cur)} />
                        <Tooltip content={<ChartTooltip labelFormat={(l) => `Rate ${fmtPct(Number(l), 1)}`} format={(v) => fmtMoney(v, cur)} />} />
                        <ReferenceLine y={0} stroke="var(--border-strong)" />
                        {isNum(rate) && <ReferenceLine x={rate} stroke={C.c3} strokeDasharray="4 4" label={{ value: 'Your rate', fill: 'var(--text-muted)', fontSize: 11, position: 'insideTopRight' }} />}
                        {r.irr.values.map((v) => <ReferenceLine key={v} x={v} stroke={C.c4} strokeDasharray="2 3" />)}
                        <Line dataKey="npv" name="NPV" stroke={C.c1} strokeWidth={2.2} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                  <Legend items={[{ label: 'NPV', color: 'var(--chart-1)' }, { label: 'Your discount rate', color: 'var(--chart-3)', dashed: true }, { label: 'IRR', color: 'var(--chart-4)', dashed: true }]} />
                </Card>
              </div>

              <Card title="Step-by-step calculation" flush>
                <div style={{ padding: '0 18px 14px' }}><Formula>{`NPV = Σ CFₜ / (1 + r)ᵗ,  t = 0 … ${r.timeline.length - 1},  r = ${fmtPct(rate, 2)}\n${r.convention}`}</Formula></div>
                <div className="table-wrap" tabIndex={0} style={{ border: 0, borderTop: '1px solid var(--border)', borderRadius: 0 }}>
                  <table className="data">
                    <thead><tr><th>t</th><th className="r">Cash flow</th><th className="r">Discount factor 1/(1+r)ᵗ</th><th className="r">Present value</th><th className="r">Cumulative</th><th className="r">Cumulative discounted</th></tr></thead>
                    <tbody>
                      {r.timeline.map((t) => (
                        <tr key={t.t}><td>{t.t}</td><td className="r">{fmtMoney(t.cash_flow, cur)}</td><td className="r">{fmtNum(t.discount_factor, 6)}</td>
                          <td className="r">{fmtMoney(t.present_value, cur, 2)}</td><td className="r">{fmtMoney(t.cumulative, cur)}</td><td className="r">{fmtMoney(t.cumulative_discounted, cur, 2)}</td></tr>
                      ))}
                    </tbody>
                    <tfoot><tr><td>NPV</td><td /><td /><td className="r">{fmtMoney(r.npv, cur, 2)}</td><td /><td /></tr></tfoot>
                  </table>
                </div>
              </Card>
            </>
          )}

          <LearnBox title="NPV, IRR and MIRR">
            <div className="stack" style={{ fontSize: 13 }}>
              <p><b>NPV</b> discounts each cash flow back to today and adds them. Positive NPV means the project earns more than the discount rate (the required return).</p>
              <p><b>IRR</b> is the rate at which NPV = 0. Accept if IRR exceeds the cost of capital — but only for conventional cash flows (one sign change). With several sign changes there may be several IRRs or none; use NPV.</p>
              <p><b>MIRR</b> assumes positive flows are reinvested at a realistic reinvestment rate and outflows are financed at the finance rate, giving a single, comparable rate.</p>
              <p><b>Payback</b> ignores the time value of money and cash flows after the payback point; discounted payback fixes the first issue only.</p>
              <p><b>Common mistake:</b> Excel's <code>NPV()</code> discounts its first value. Use <code>=CF0 + NPV(r, CF1:CFn)</code>.</p>
            </div>
          </LearnBox>
        </div>
      </div>
    </div>
  );
}
