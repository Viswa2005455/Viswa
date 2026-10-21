import { Copy, Download, Plus, RotateCcw, Trash2 } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { C, ChartTooltip, Legend, axisProps, gridProps } from '../components/charts';
import { SaveLoad } from '../components/SaveLoad';
import type { DCFModel } from '../lib/types';
import { Badge, Callout, Card, ErrorBox, LearnBox, NumberField, PageHeader } from '../components/ui';
import { api } from '../lib/api';
import { useDCFModel } from '../lib/dcfModel';
import { downloadFile, fmtCompact, fmtMoney, fmtNum, fmtPct, isNum, toCSV } from '../lib/format';
import { useSettings } from '../lib/settings';
import { loadRaw, save } from '../lib/storage';
import { useAsync, useDebounced } from '../lib/useApi';

type OverrideKey = 'wacc' | 'terminal_growth' | 'tax_rate' | 'capex_pct_revenue' | 'nwc_pct_revenue' | 'da_pct_revenue';
interface Scenario { id: string; name: string; revenue_growth_shift: number; ebit_margin_shift: number; overrides: Partial<Record<OverrideKey, number>> }
interface ScenarioRes {
  name: string; error: string | null; enterprise_value: number; equity_value: number; value_per_share: number | null;
  final_revenue: number; final_ebitda: number; final_ebit: number; final_nopat: number; final_fcff: number; cumulative_fcff: number;
  terminal_share: number; years: { year: number; revenue: number; fcff: number }[]; warnings: string[];
}

const OVERRIDES: { key: OverrideKey; label: string }[] = [
  { key: 'wacc', label: 'WACC' }, { key: 'terminal_growth', label: 'Terminal growth' }, { key: 'tax_rate', label: 'Tax rate' },
  { key: 'capex_pct_revenue', label: 'CapEx % revenue' }, { key: 'nwc_pct_revenue', label: 'NWC % revenue' }, { key: 'da_pct_revenue', label: 'D&A % revenue' },
];

const DEFAULTS: Scenario[] = [
  { id: 'base', name: 'Base case', revenue_growth_shift: 0, ebit_margin_shift: 0, overrides: {} },
  { id: 'opt', name: 'Optimistic', revenue_growth_shift: 0.02, ebit_margin_shift: 0.015, overrides: { wacc: 0.105 } },
  { id: 'pes', name: 'Pessimistic', revenue_growth_shift: -0.03, ebit_margin_shift: -0.02, overrides: { wacc: 0.12, capex_pct_revenue: 0.065 } },
];
const COLORS = [C.c1, C.c2, C.c4, C.c3, C.c5];
const uid = () => Math.random().toString(36).slice(2, 9);

/** Each changed assumption applied alone to the base case (one-at-a-time attribution). */
function attributionRuns(s: Scenario): Scenario[] {
  const runs: Scenario[] = [];
  if (s.revenue_growth_shift) runs.push({ id: `${s.id}|growth`, name: `${s.id}|Revenue growth shift`, revenue_growth_shift: s.revenue_growth_shift, ebit_margin_shift: 0, overrides: {} });
  if (s.ebit_margin_shift) runs.push({ id: `${s.id}|margin`, name: `${s.id}|EBIT margin shift`, revenue_growth_shift: 0, ebit_margin_shift: s.ebit_margin_shift, overrides: {} });
  for (const o of OVERRIDES) {
    const v = s.overrides[o.key];
    if (isNum(v)) runs.push({ id: `${s.id}|${o.key}`, name: `${s.id}|${o.label}`, revenue_growth_shift: 0, ebit_margin_shift: 0, overrides: { [o.key]: v } });
  }
  return runs;
}

export function Scenarios() {
  const { model, isExample, setModel } = useDCFModel();
  const { settings } = useSettings();
  const cur = settings.currency;
  const [scenarios, setScenariosState] = useState<Scenario[]>(() => loadRaw('fis.scenarios', DEFAULTS));
  const setScenarios = (s: Scenario[]) => { setScenariosState(s); save('fis.scenarios', s); };
  const update = (id: string, p: Partial<Scenario>) => setScenarios(scenarios.map((s) => (s.id === id ? { ...s, ...p } : s)));

  const payload = useMemo(() => {
    const extra = scenarios.slice(1).flatMap(attributionRuns);
    return { model, scenarios: [...scenarios, ...extra].map(({ name, id, ...rest }) => ({ ...rest, name: id.includes('|') ? name : id })) };
  }, [model, scenarios]);
  const req = useDebounced(payload, 300);
  const res = useAsync(() => api.post<{ scenarios: ScenarioRes[] }>('/api/finance/dcf/scenarios', req), [JSON.stringify(req)]);

  const byId = new Map<string, ScenarioRes>();
  res.data?.scenarios.forEach((r) => byId.set(r.name, r));
  const base = byId.get(scenarios[0]?.id);

  const metrics: [string, (r: ScenarioRes) => number | null, 'money' | 'money2' | 'num' | 'pct'][] = [
    ['Enterprise value', (r) => r.enterprise_value, 'money'],
    ['Equity value', (r) => r.equity_value, 'money'],
    ['Value per share', (r) => r.value_per_share, 'money2'],
    [`Revenue (Y${model.revenue_growth.length})`, (r) => r.final_revenue, 'num'],
    ['EBITDA (final year)', (r) => r.final_ebitda, 'num'],
    ['EBIT (final year)', (r) => r.final_ebit, 'num'],
    ['NOPAT (final year)', (r) => r.final_nopat, 'num'],
    ['FCFF (final year)', (r) => r.final_fcff, 'num'],
    ['Cumulative FCFF', (r) => r.cumulative_fcff, 'num'],
    ['Terminal value % of EV', (r) => r.terminal_share, 'pct'],
  ];
  const show = (v: number | null, kind: string) =>
    kind === 'money' ? fmtMoney(v, cur) : kind === 'money2' ? fmtMoney(v, cur, 2) : kind === 'pct' ? fmtPct(v, 1) : fmtNum(v, 1);

  const evChart = scenarios.map((s) => ({ name: s.name, ev: byId.get(s.id)?.enterprise_value ?? null, equity: byId.get(s.id)?.equity_value ?? null }));
  const revChart = model.revenue_growth.map((_, i) => {
    const row: Record<string, number | string> = { year: `Y${i + 1}` };
    scenarios.forEach((s) => { const r = byId.get(s.id); if (r && !r.error) row[s.id] = r.years[i]?.revenue; });
    return row;
  });

  const exportCsv = () => {
    const rows: unknown[][] = [['Scenario comparison', isExample ? 'EXAMPLE DCF ASSUMPTIONS' : 'User DCF assumptions'], [],
      ['Assumption', ...scenarios.map((s) => s.name)],
      ['Revenue growth shift (pp)', ...scenarios.map((s) => s.revenue_growth_shift * 100)],
      ['EBIT margin shift (pp)', ...scenarios.map((s) => s.ebit_margin_shift * 100)],
      ...OVERRIDES.map((o) => [o.label, ...scenarios.map((s) => s.overrides[o.key] ?? 'base')]), [],
      ['Output', ...scenarios.map((s) => s.name)],
      ...metrics.map(([label, get]) => [label, ...scenarios.map((s) => {
        const r = byId.get(s.id);
        if (!r || r.error) return r?.error ?? '';
        return get(r);
      })]), ['Generated', new Date().toISOString()]];
    downloadFile('scenario-comparison.csv', toCSV(rows));
  };

  return (
    <div className="page">
      <PageHeader title="Scenario Planning" badge={isExample ? <Badge tone="sample">Example DCF assumptions</Badge> : undefined}
        subtitle={<>Each scenario changes assumptions of the shared <Link to="/dcf">DCF model</Link> and is fully recalculated. Shifts are in percentage points; overrides replace the base value.</>}
        actions={<>
          <button className="btn" onClick={() => setScenarios([...scenarios, { id: uid(), name: `Custom ${scenarios.length}`, revenue_growth_shift: 0, ebit_margin_shift: 0, overrides: {} }])} disabled={scenarios.length >= 5}><Plus size={15} />Add scenario</button>
          <SaveLoad kind="scenarios" label="scenario set" getData={() => ({ scenarios, model })}
            onLoad={(d: { scenarios: Scenario[]; model?: DCFModel }) => { setScenarios(d.scenarios); if (d.model) setModel(d.model); }} />
          <button className="btn" onClick={() => setScenarios(DEFAULTS)}><RotateCcw size={15} />Defaults</button>
          <button className="btn" onClick={exportCsv} disabled={!res.data}><Download size={15} />Export CSV</button>
        </>} />
      {res.error && <ErrorBox error={res.error} />}

      <Card title="Assumptions by scenario" subtitle="Highlighted values differ from the base case. Blank override = use the DCF model's value." flush>
        <div className="table-wrap" style={{ border: 0, borderRadius: 0 }}>
          <table className="data">
            <thead>
              <tr><th>Assumption</th>{scenarios.map((s, i) => (
                <th key={s.id} style={{ minWidth: 170 }}>
                  <div className="row" style={{ flexWrap: 'nowrap', gap: 4 }}>
                    <i style={{ width: 8, height: 8, borderRadius: 3, background: COLORS[i % COLORS.length], flex: 'none' }} />
                    <input className="input compact" aria-label="Scenario name" value={s.name} maxLength={60} onChange={(e) => update(s.id, { name: e.target.value })} />
                    <button className="btn icon sm ghost" aria-label={`Duplicate ${s.name}`} disabled={scenarios.length >= 5}
                      onClick={() => setScenarios([...scenarios, { ...s, id: uid(), name: `${s.name} (copy)`, overrides: { ...s.overrides } }])}><Copy size={13} /></button>
                    {i > 0 && <button className="btn icon sm ghost" aria-label={`Delete ${s.name}`} onClick={() => setScenarios(scenarios.filter((x) => x.id !== s.id))}><Trash2 size={13} /></button>}
                  </div>
                </th>
              ))}</tr>
            </thead>
            <tbody>
              <ShiftRow label="Revenue growth shift (pp)" field="revenue_growth_shift" scenarios={scenarios} update={update} />
              <ShiftRow label="EBIT margin shift (pp)" field="ebit_margin_shift" scenarios={scenarios} update={update} />
              {OVERRIDES.map((o) => (
                <tr key={o.key}>
                  <td>{o.label} <span className="faint">(base {fmtPct(model[o.key], 1)})</span></td>
                  {scenarios.map((s) => {
                    const v = s.overrides[o.key];
                    const diff = isNum(v) && Math.abs(v - model[o.key]) > 1e-12;
                    return (
                      <td key={s.id} style={diff ? { background: 'var(--accent-soft)' } : undefined}>
                        <NumberField compact percent ariaLabel={`${o.label} for ${s.name}`} value={v ?? null}
                          onChange={(nv) => { const ov = { ...s.overrides }; if (nv === null) delete ov[o.key]; else ov[o.key] = nv; update(s.id, { overrides: ov }); }} />
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid cols-2 mt">
        <Card title="Outputs" flush>
          <div className="table-wrap" style={{ border: 0, borderRadius: 0 }}>
            <table className="data">
              <thead><tr><th>Metric</th>{scenarios.map((s) => <th key={s.id} className="r">{s.name}</th>)}</tr></thead>
              <tbody>
                {metrics.map(([label, get, kind]) => (
                  <tr key={label}><td>{label}</td>{scenarios.map((s) => {
                    const r = byId.get(s.id);
                    return <td key={s.id} className="r">{!r ? '…' : r.error ? <span className="neg" title={r.error}>Invalid</span> : show(get(r), kind)}</td>;
                  })}</tr>
                ))}
              </tbody>
            </table>
          </div>
          {scenarios.map((s) => byId.get(s.id)?.error && <div key={s.id} style={{ padding: '10px 18px' }}><Callout tone="error" title={s.name}>{byId.get(s.id)!.error}</Callout></div>)}
        </Card>

        <Card title="Enterprise and equity value by scenario">
          <div className="chart">
            <ResponsiveContainer>
              <BarChart data={evChart} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="name" {...axisProps} />
                <YAxis {...axisProps} width={56} tickFormatter={(v) => fmtCompact(v, cur)} />
                <Tooltip cursor={{ fill: 'var(--bg-hover)' }} content={<ChartTooltip format={(v) => fmtMoney(v, cur)} />} />
                <Bar dataKey="ev" name="Enterprise value" fill={C.c1} radius={[4, 4, 0, 0]} maxBarSize={40} />
                <Bar dataKey="equity" name="Equity value" fill={C.c2} radius={[4, 4, 0, 0]} maxBarSize={40} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <Legend items={[{ label: 'Enterprise value', color: 'var(--chart-1)' }, { label: 'Equity value', color: 'var(--chart-2)' }]} />
        </Card>

        <Card title="Revenue path">
          <div className="chart">
            <ResponsiveContainer>
              <LineChart data={revChart} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="year" {...axisProps} />
                <YAxis {...axisProps} width={56} tickFormatter={(v) => fmtCompact(v, cur)} />
                <Tooltip content={<ChartTooltip format={(v) => fmtNum(v, 1)} />} />
                {scenarios.map((s, i) => <Line key={s.id} dataKey={s.id} name={s.name} stroke={COLORS[i % COLORS.length]} strokeWidth={2.2} dot={false} />)}
              </LineChart>
            </ResponsiveContainer>
          </div>
          <Legend items={scenarios.map((s, i) => ({ label: s.name, color: COLORS[i % COLORS.length] }))} />
        </Card>

        <Card title="Largest drivers vs base case" subtitle="Each changed assumption applied on its own to the base case">
          {base && !base.error ? scenarios.slice(1).map((s) => {
            const r = byId.get(s.id);
            const parts = attributionRuns(s).map((a) => ({ label: a.name.split('|')[1], delta: (byId.get(a.name)?.enterprise_value ?? NaN) - base.enterprise_value }))
              .filter((p) => isNum(p.delta)).sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
            const total = r && !r.error ? r.enterprise_value - base.enterprise_value : null;
            const interaction = isNum(total) ? total - parts.reduce((acc, p) => acc + p.delta, 0) : null;
            return (
              <div key={s.id} style={{ marginBottom: 14 }}>
                <div className="row between"><b>{s.name}</b><span className={`num ${isNum(total) && total >= 0 ? 'pos' : 'neg'}`}>{isNum(total) ? `${total >= 0 ? '+' : ''}${fmtMoney(total, cur)}` : 'invalid'}</span></div>
                {parts.length === 0 ? <div className="faint" style={{ fontSize: 12.5 }}>No assumptions differ from the base case.</div> : parts.map((p) => (
                  <div key={p.label} className="metric-row"><span className="muted">{p.label}</span><span className={`v ${p.delta >= 0 ? 'pos' : 'neg'}`}>{p.delta >= 0 ? '+' : ''}{fmtMoney(p.delta, cur)}</span></div>
                ))}
                {isNum(interaction) && Math.abs(interaction) > 0.5 && <div className="metric-row"><span className="faint">Interaction effect (combined changes)</span><span className="v faint">{fmtMoney(interaction, cur)}</span></div>}
              </div>
            );
          }) : <span className="faint">Base case not available.</span>}
        </Card>
      </div>

      <div className="mt">
        <Callout tone="info" title="Scope of this version">
          Scenarios drive the DCF model's growth, margin, WACC, terminal growth, tax, CapEx, D&A and working-capital assumptions. Volume × price,
          salary, inflation and interest-rate drivers need the operating model planned for the Budgeting module.
        </Callout>
      </div>
      <div className="mt">
        <LearnBox title="Scenario analysis">
          <p style={{ fontSize: 13 }}>Scenario analysis changes several assumptions <i>together</i> to describe a coherent future (for example a recession: lower growth, lower margins, higher cost of capital). It differs from sensitivity analysis, which changes one or two variables at a time. Scenarios are not forecasts; they bound a range of plausible outcomes.</p>
        </LearnBox>
      </div>
    </div>
  );
}

function ShiftRow({ label, field, scenarios, update }: { label: string; field: 'revenue_growth_shift' | 'ebit_margin_shift'; scenarios: Scenario[]; update: (id: string, p: Partial<Scenario>) => void }) {
  return (
    <tr>
      <td>{label}</td>
      {scenarios.map((s) => (
        <td key={s.id} style={s[field] ? { background: 'var(--accent-soft)' } : undefined}>
          <NumberField compact percent ariaLabel={`${label} for ${s.name}`} value={s[field]} onChange={(v) => update(s.id, { [field]: v ?? 0 })} />
        </td>
      ))}
    </tr>
  );
}
