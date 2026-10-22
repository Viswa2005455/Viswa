import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { C, ChartTooltip, Legend, axisProps, gridProps } from '../components/charts';
import { Badge, Callout, Card, ErrorBox, Field, LearnBox, NumberField, PageHeader, Skeleton, Tabs } from '../components/ui';
import { api } from '../lib/api';
import { useDCFModel } from '../lib/dcfModel';
import { fmtCompact, fmtMoney, fmtNum, fmtPct, isNum } from '../lib/format';
import { useSettings } from '../lib/settings';
import type { DCFModel } from '../lib/types';
import { useAsync, useDebounced } from '../lib/useApi';

type Var = 'wacc' | 'terminal_growth' | 'revenue_growth' | 'ebit_margin' | 'tax_rate' | 'capex_pct_revenue' | 'da_pct_revenue' | 'nwc_pct_revenue' | 'exit_multiple';
const VARS: { key: Var; label: string; step: number; pct: boolean }[] = [
  { key: 'wacc', label: 'WACC', step: 0.005, pct: true },
  { key: 'terminal_growth', label: 'Terminal growth', step: 0.005, pct: true },
  { key: 'revenue_growth', label: 'Revenue growth (all years)', step: 0.01, pct: true },
  { key: 'ebit_margin', label: 'EBIT margin (all years)', step: 0.01, pct: true },
  { key: 'tax_rate', label: 'Tax rate', step: 0.01, pct: true },
  { key: 'capex_pct_revenue', label: 'CapEx % revenue', step: 0.005, pct: true },
  { key: 'da_pct_revenue', label: 'D&A % revenue', step: 0.005, pct: true },
  { key: 'nwc_pct_revenue', label: 'NWC % revenue', step: 0.01, pct: true },
  { key: 'exit_multiple', label: 'Exit multiple', step: 1, pct: false },
];
const OUTPUTS = [
  { key: 'enterprise_value', label: 'Enterprise value', money: true },
  { key: 'equity_value', label: 'Equity value', money: true },
  { key: 'value_per_share', label: 'Value per share', money: true },
  { key: 'final_year_fcff', label: 'Final-year FCFF', money: true },
  { key: 'final_year_ebitda', label: 'Final-year EBITDA', money: true },
];

function baseOf(model: DCFModel, v: Var): number {
  const val = model[v] as number | number[] | null;
  if (Array.isArray(val)) return val.reduce((a, b) => a + b, 0) / val.length;
  return val ?? 0;
}
const round = (x: number) => Math.round(x * 1e10) / 1e10;
const range = (center: number, step: number, n: number) => Array.from({ length: n }, (_, i) => round(center + (i - (n - 1) / 2) * step));
const fmtVar = (v: Var, x: number) => (VARS.find((d) => d.key === v)!.pct ? fmtPct(x, 2) : `${fmtNum(x, 1)}×`);

interface Grid { x_values: number[]; y_values: number[]; base_output: number | null; base_x: number; base_y: number; grid: { value: number | null; error: string | null }[][] }

export function Sensitivity() {
  const { model, isExample } = useDCFModel();
  const [mode, setMode] = useState<'two' | 'one' | 'tornado' | 'breakeven'>('two');
  const [output, setOutput] = useState('enterprise_value');
  return (
    <div className="page">
      <PageHeader title="Sensitivity Analysis" badge={isExample ? <Badge tone="sample">Example DCF assumptions</Badge> : undefined}
        subtitle={<>Every cell and bar re-runs the full <Link to="/dcf">DCF model</Link> with changed inputs — nothing is interpolated.</>}
        actions={<Tabs label="Analysis type" value={mode} onChange={setMode} options={[
          { value: 'two', label: 'Two-variable' }, { value: 'one', label: 'One-variable' }, { value: 'tornado', label: 'Tornado' }, { value: 'breakeven', label: 'Break-even' }]} />} />
      <div className="row" style={{ marginBottom: 16 }}>
        <Field label="Output">
          <select className="input" style={{ width: 220 }} value={output} onChange={(e) => setOutput(e.target.value)}>
            {OUTPUTS.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
          </select>
        </Field>
        {output === 'value_per_share' && !model.shares_outstanding && <Callout tone="warn">Enter shares outstanding in the DCF model to compute value per share.</Callout>}
      </div>
      {mode === 'two' && <TwoWay model={model} output={output} />}
      {mode === 'one' && <OneWay model={model} output={output} />}
      {mode === 'tornado' && <Tornado model={model} output={output} />}
      {mode === 'breakeven' && <BreakEven model={model} output={output} />}
      <div className="mt">
        <LearnBox title="Sensitivity analysis">
          <div style={{ fontSize: 13 }} className="stack">
            <p>Sensitivity analysis changes one or two inputs while holding everything else constant, to show which assumptions matter most.</p>
            <p>A <b>tornado chart</b> ranks inputs by the swing in output between their low and high values; the widest bars deserve the most research. A <b>break-even</b> value is the input level at which the output reaches a target (e.g. the WACC at which EV equals today's market price).</p>
            <p><b>Limitation:</b> inputs are often correlated in reality (higher growth may need more CapEx), which one-at-a-time analysis ignores — use Scenario Planning for coherent combinations.</p>
          </div>
        </LearnBox>
      </div>
    </div>
  );
}

function VarSelect({ label, value, onChange, exclude }: { label: string; value: Var; onChange: (v: Var) => void; exclude?: Var }) {
  return (
    <Field label={label}>
      <select className="input" value={value} onChange={(e) => onChange(e.target.value as Var)}>
        {VARS.filter((v) => v.key !== exclude).map((v) => <option key={v.key} value={v.key}>{v.label}</option>)}
      </select>
    </Field>
  );
}

function TwoWay({ model, output }: { model: DCFModel; output: string }) {
  const { settings } = useSettings();
  const [xVar, setXVar] = useState<Var>('wacc');
  const [yVar, setYVar] = useState<Var>('terminal_growth');
  const [xStep, setXStep] = useState<number | null>(0.005);
  const [yStep, setYStep] = useState<number | null>(0.005);
  const [size, setSize] = useState(5);
  const xd = VARS.find((v) => v.key === xVar)!;
  const yd = VARS.find((v) => v.key === yVar)!;

  const body = useMemo(() => (isNum(xStep) && isNum(yStep) && xStep > 0 && yStep > 0 ? {
    model, x_variable: xVar, y_variable: yVar, output,
    x_values: range(baseOf(model, xVar), xStep, size), y_values: range(baseOf(model, yVar), yStep, size),
  } : null), [model, xVar, yVar, output, xStep, yStep, size]);
  const req = useDebounced(body, 250);
  const res = useAsync(() => api.post<Grid>('/api/finance/dcf/sensitivity', req), [JSON.stringify(req)], !!req);
  const g = res.data;

  const vals = g?.grid.flat().map((c) => c.value).filter(isNum) ?? [];
  const maxDev = g && isNum(g.base_output) ? Math.max(1e-9, ...vals.map((v) => Math.abs(v - g.base_output!))) : 1;
  const cellBg = (v: number | null) => {
    if (!g || !isNum(v) || !isNum(g.base_output)) return undefined;
    const d = (v - g.base_output) / maxDev;
    const a = Math.min(0.55, Math.abs(d) * 0.55);
    return d >= 0 ? `color-mix(in srgb, var(--chart-1) ${a * 100}%, transparent)` : `color-mix(in srgb, var(--negative) ${a * 100}%, transparent)`;
  };
  const near = (a: number, b: number) => Math.abs(a - b) < 1e-9;

  return (
    <div className="grid cols-3">
      <Card title="Grid setup">
        <div className="stack">
          <VarSelect label="Columns (x)" value={xVar} onChange={setXVar} exclude={yVar} />
          <NumberField label={`Column step`} percent={xd.pct} suffix={xd.pct ? undefined : '×'} value={xStep} onChange={setXStep} min={0} required />
          <VarSelect label="Rows (y)" value={yVar} onChange={setYVar} exclude={xVar} />
          <NumberField label="Row step" percent={yd.pct} suffix={yd.pct ? undefined : '×'} value={yStep} onChange={setYStep} min={0} required />
          <Field label="Grid size">
            <Tabs label="Grid size" value={String(size)} onChange={(v) => setSize(Number(v))} options={[{ value: '5', label: '5 × 5' }, { value: '7', label: '7 × 7' }, { value: '9', label: '9 × 9' }]} />
          </Field>
          {model.terminal_method === 'exit_multiple' && (xVar === 'terminal_growth' || yVar === 'terminal_growth') && (
            <Callout tone="warn">The model uses the exit-multiple method, so terminal growth has no effect.</Callout>
          )}
          {model.terminal_method === 'gordon' && (xVar === 'exit_multiple' || yVar === 'exit_multiple') && (
            <Callout tone="warn">The model uses Gordon growth, so the exit multiple has no effect.</Callout>
          )}
        </div>
      </Card>
      <Card className="span-2" title={`${OUTPUTS.find((o) => o.key === output)?.label}: ${yd.label} × ${xd.label}`}
        subtitle="Outlined cell = base case. Green above base, orange below. 'n/a' = invalid combination (hover for the reason).">
        {res.error && <ErrorBox error={res.error} />}
        {!g && res.loading && <Skeleton h={240} />}
        {g && (
          <div className="table-wrap" tabIndex={0}>
            <table className="data heat">
              <thead>
                <tr><th className="axis">{yd.label} ↓ / {xd.label} →</th>{g.x_values.map((x) => <th key={x} className="r" style={near(x, g.base_x) ? { color: 'var(--text)' } : undefined}>{fmtVar(xVar, x)}</th>)}</tr>
              </thead>
              <tbody>
                {g.grid.map((row, i) => (
                  <tr key={i}>
                    <th className="axis" style={near(g.y_values[i], g.base_y) ? { color: 'var(--text)' } : undefined}>{fmtVar(yVar, g.y_values[i])}</th>
                    {row.map((c, j) => (
                      <td key={j} className={`cell ${near(g.x_values[j], g.base_x) && near(g.y_values[i], g.base_y) ? 'base' : ''}`}
                        style={{ background: cellBg(c.value) }} title={c.error ?? undefined}>
                        {isNum(c.value) ? fmtMoney(c.value, settings.currency, output === 'value_per_share' ? 2 : 0) : <span className="faint">n/a</span>}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

function OneWay({ model, output }: { model: DCFModel; output: string }) {
  const { settings } = useSettings();
  const [v, setV] = useState<Var>('wacc');
  const [step, setStep] = useState<number | null>(0.005);
  const d = VARS.find((x) => x.key === v)!;
  const other: Var = v === 'tax_rate' ? 'wacc' : 'tax_rate';
  const body = useMemo(() => (isNum(step) && step > 0 ? {
    model, x_variable: v, x_values: range(baseOf(model, v), step, 11), y_variable: other, y_values: [baseOf(model, other)], output,
  } : null), [model, v, step, output, other]);
  const req = useDebounced(body, 250);
  const res = useAsync(() => api.post<Grid>('/api/finance/dcf/sensitivity', req), [JSON.stringify(req)], !!req);
  const data = res.data?.x_values.map((x, i) => ({ x, value: res.data!.grid[0][i].value })) ?? [];
  return (
    <div className="grid cols-3">
      <Card title="Variable">
        <div className="stack">
          <VarSelect label="Input" value={v} onChange={setV} />
          <NumberField label="Step" percent={d.pct} suffix={d.pct ? undefined : '×'} value={step} onChange={setStep} min={0} required />
          <p className="faint" style={{ fontSize: 12.5 }}>11 points centred on the base value ({fmtVar(v, baseOf(model, v))}).</p>
        </div>
      </Card>
      <Card className="span-2" title={`${OUTPUTS.find((o) => o.key === output)?.label} vs ${d.label}`}>
        {res.error && <ErrorBox error={res.error} />}
        <div className="chart tall">
          <ResponsiveContainer>
            <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="x" type="number" domain={['dataMin', 'dataMax']} {...axisProps} tickFormatter={(x) => fmtVar(v, x)} />
              <YAxis {...axisProps} width={60} tickFormatter={(y) => fmtCompact(y, settings.currency)} />
              <Tooltip content={<ChartTooltip labelFormat={(l) => `${d.label}: ${fmtVar(v, Number(l))}`} format={(y) => fmtMoney(y, settings.currency)} />} />
              <ReferenceLine x={baseOf(model, v)} stroke={C.c3} strokeDasharray="4 4" />
              <Line dataKey="value" name="Output" stroke={C.c1} strokeWidth={2.4} dot={{ r: 3 }} connectNulls={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <Legend items={[{ label: 'Output', color: 'var(--chart-1)' }, { label: 'Base case', color: 'var(--chart-3)', dashed: true }]} />
        {data.some((p) => p.value === null) && <Callout tone="warn">Some points are invalid (for example WACC ≤ terminal growth) and are left blank.</Callout>}
      </Card>
    </div>
  );
}

interface TornadoRes { base_output: number; bars: { variable: Var; base_input: number; low_input: number; high_input: number; low_output: number | null; high_output: number | null; swing: number; error: string | null }[] }

function Tornado({ model, output }: { model: DCFModel; output: string }) {
  const { settings } = useSettings();
  const [shock, setShock] = useState<number | null>(0.1);
  const active = VARS.filter((v) => (model.terminal_method === 'gordon' ? v.key !== 'exit_multiple' : v.key !== 'terminal_growth'));
  const body = useMemo(() => {
    if (!isNum(shock) || shock <= 0) return null;
    const ranges: Record<string, [number, number]> = {};
    active.forEach((v) => { const b = baseOf(model, v.key); const d = Math.abs(b) * shock || v.step; ranges[v.key] = [round(b - d), round(b + d)]; });
    return { model, ranges, output };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [model, shock, output]);
  const req = useDebounced(body, 250);
  const res = useAsync(() => api.post<TornadoRes>('/api/finance/dcf/tornado', req), [JSON.stringify(req)], !!req);
  const t = res.data;
  const data = t?.bars.map((b) => ({
    name: VARS.find((v) => v.key === b.variable)!.label,
    low: isNum(b.low_output) ? b.low_output - t.base_output : null,
    high: isNum(b.high_output) ? b.high_output - t.base_output : null,
    b,
  })) ?? [];
  return (
    <div className="grid cols-3">
      <Card title="Shock size">
        <NumberField label="Change each input by ± (relative)" percent value={shock} onChange={setShock} min={0} hint="10% of WACC 11% = 9.9% to 12.1%" required />
        {t && <div className="mt"><div className="metric-row"><span>Base output</span><span className="v">{fmtMoney(t.base_output, settings.currency)}</span></div></div>}
      </Card>
      <Card className="span-2" title="Tornado: change in output vs base" subtitle="Sorted by total swing">
        {res.error && <ErrorBox error={res.error} />}
        <div className="chart tall">
          <ResponsiveContainer>
            <BarChart data={data} layout="vertical" stackOffset="sign" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
              <CartesianGrid {...gridProps} horizontal={false} vertical />
              <XAxis type="number" {...axisProps} tickFormatter={(v) => fmtCompact(v, settings.currency)} />
              <YAxis type="category" dataKey="name" {...axisProps} width={150} />
              <Tooltip cursor={{ fill: 'var(--bg-hover)' }} content={<ChartTooltip format={(v) => `${v >= 0 ? '+' : ''}${fmtMoney(v, settings.currency)}`} />} />
              <ReferenceLine x={0} stroke="var(--border-strong)" />
              <Bar dataKey="low" name="Input low" stackId="s" fill={C.c4} radius={3} maxBarSize={22} />
              <Bar dataKey="high" name="Input high" stackId="s" fill={C.c2} radius={3} maxBarSize={22} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <Legend items={[{ label: 'Input at low value', color: 'var(--chart-4)' }, { label: 'Input at high value', color: 'var(--chart-2)' }]} />
        {t && (
          <div className="table-wrap mt" tabIndex={0}>
            <table className="data">
              <thead><tr><th>Input</th><th className="r">Low</th><th className="r">Base</th><th className="r">High</th><th className="r">Output at low</th><th className="r">Output at high</th><th className="r">Swing</th></tr></thead>
              <tbody>{t.bars.map((b) => (
                <tr key={b.variable} title={b.error ?? undefined}>
                  <td>{VARS.find((v) => v.key === b.variable)!.label}</td>
                  <td className="r">{fmtVar(b.variable, b.low_input)}</td><td className="r">{fmtVar(b.variable, b.base_input)}</td><td className="r">{fmtVar(b.variable, b.high_input)}</td>
                  <td className="r">{isNum(b.low_output) ? fmtMoney(b.low_output, settings.currency) : 'n/a'}</td>
                  <td className="r">{isNum(b.high_output) ? fmtMoney(b.high_output, settings.currency) : 'n/a'}</td>
                  <td className="r">{fmtMoney(b.swing, settings.currency)}</td>
                </tr>))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

function BreakEven({ model, output }: { model: DCFModel; output: string }) {
  const { settings } = useSettings();
  const [v, setV] = useState<Var>('wacc');
  const [target, setTarget] = useState<number | null>(null);
  const [lo, setLo] = useState<number | null>(round(model.terminal_growth + 0.005));
  const [hi, setHi] = useState<number | null>(0.4);
  const d = VARS.find((x) => x.key === v)!;
  const body = isNum(target) && isNum(lo) && isNum(hi) && lo < hi ? { model, variable: v, output, target, low: lo, high: hi } : null;
  const req = useDebounced(body, 300);
  const res = useAsync(() => api.post<{ value: number | null; base_value: number; message: string | null }>('/api/finance/dcf/break-even', req), [JSON.stringify(req)], !!req);
  return (
    <div className="grid cols-3">
      <Card title="Find the break-even input">
        <div className="stack">
          <VarSelect label="Input to solve for" value={v} onChange={(nv) => { setV(nv); const dd = VARS.find((x) => x.key === nv)!; setLo(nv === 'wacc' ? round(model.terminal_growth + 0.005) : dd.pct ? -0.2 : 1); setHi(dd.pct ? 0.4 : 40); }} />
          <NumberField label={`Target ${OUTPUTS.find((o) => o.key === output)?.label.toLowerCase()}`} value={target} onChange={setTarget} required />
          <div className="grid cols-2" style={{ gap: 10 }}>
            <NumberField label="Search from" percent={d.pct} value={lo} onChange={setLo} required />
            <NumberField label="Search to" percent={d.pct} value={hi} onChange={setHi} required />
          </div>
        </div>
      </Card>
      <Card className="span-2" title="Result">
        {!body && <p className="muted">Enter a target value and a valid search range.</p>}
        {res.error && <ErrorBox error={res.error} />}
        {body && res.data && (isNum(res.data.value) ? (
          <Callout tone="success" title={`${d.label} = ${fmtVar(v, res.data.value)}`}>
            At this value the {OUTPUTS.find((o) => o.key === output)?.label.toLowerCase()} equals {fmtMoney(target, settings.currency)} (base case input: {fmtVar(v, res.data.base_value)}).
            Solved by bisection on the full DCF model.
          </Callout>
        ) : <Callout tone="warn">{res.data.message}</Callout>)}
      </Card>
    </div>
  );
}
