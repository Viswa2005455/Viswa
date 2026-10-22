import { Download, Plus, RotateCcw, Trash2 } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Bar, BarChart, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { C, ChartTooltip, Legend, axisProps, gridProps } from '../components/charts';
import { SaveLoad } from '../components/SaveLoad';
import { Badge, Callout, Card, ErrorBox, Formula, Kpi, LearnBox, NumberField, PageHeader, Tabs, Warnings } from '../components/ui';
import { api } from '../lib/api';
import { downloadFile, fmtCompact, fmtMoney, fmtNum, isNum, toCSV } from '../lib/format';
import { useSettings } from '../lib/settings';
import { loadRaw, save } from '../lib/storage';
import { useAsync, useDebounced } from '../lib/useApi';

interface CashLine { name: string; values: (number | null)[] }
interface CBState { periods: string[]; opening: number | null; minimum: number | null; receipts: CashLine[]; payments: CashLine[] }
interface CBRes {
  periods: { period: string; opening: number; receipts: number; payments: number; net_flow: number; financing: number; closing: number; closing_without_financing: number }[];
  total_receipts: number; total_payments: number; total_financing: number; lowest_closing_without_financing: number; lowest_period: string;
  first_negative_period: string | null; receipts_by_line: Record<string, number>; payments_by_line: Record<string, number>; warnings: string[];
  runway: { average_net_burn: number; months: number | null; message: string } | null;
}

const MONTHS = ['Apr-26', 'May-26', 'Jun-26', 'Jul-26', 'Aug-26', 'Sep-26', 'Oct-26', 'Nov-26', 'Dec-26', 'Jan-27', 'Feb-27', 'Mar-27'];
const EXAMPLE: CBState = {
  periods: MONTHS, opening: 250000, minimum: 100000,
  receipts: [
    { name: 'Cash sales', values: [120000, 110000, 95000, 90000, 100000, 130000, 160000, 170000, 150000, 115000, 120000, 140000] },
    { name: 'Collections from debtors', values: [180000, 175000, 160000, 150000, 150000, 175000, 210000, 240000, 230000, 200000, 185000, 195000] },
  ],
  payments: [
    { name: 'Suppliers', values: [160000, 170000, 175000, 180000, 185000, 175000, 160000, 150000, 140000, 150000, 155000, 160000] },
    { name: 'Salaries', values: [95000, 95000, 95000, 95000, 95000, 95000, 95000, 95000, 95000, 98000, 98000, 98000] },
    { name: 'Rent & utilities', values: [30000, 30000, 30000, 30000, 30000, 30000, 30000, 30000, 30000, 30000, 30000, 30000] },
    { name: 'Equipment purchase', values: [0, 0, 120000, 0, 0, 0, 0, 0, 0, 0, 0, 0] },
    { name: 'Tax instalments', values: [0, 0, 25000, 0, 0, 25000, 0, 0, 25000, 0, 0, 25000] },
  ],
};

export function CashFlow() {
  const [tab, setTab] = useState<'budget' | 'wc'>('budget');
  return (
    <div className="page">
      <PageHeader title="Cash Flow & Working Capital"
        subtitle="Plan cash month by month, see when financing is needed and how long cash lasts, and measure how much cash is tied up in working capital."
        actions={<Tabs label="View" value={tab} onChange={setTab} options={[{ value: 'budget', label: 'Cash budget & runway' }, { value: 'wc', label: 'Working capital' }]} />} />
      {tab === 'budget' ? <CashBudget /> : <WorkingCapital />}
      <div className="mt">
        <LearnBox title="Cash budgets, runway and the cash conversion cycle">
          <div className="stack" style={{ fontSize: 13 }}>
            <p>A <b>cash budget</b> tracks actual receipts and payments, not revenue and expenses. A profitable company can still run out of cash if customers pay slowly or large purchases fall in the same month.</p>
            <Formula>{`Closing cash = Opening cash + Receipts − Payments + Financing
Runway (months) = Cash / Average monthly net burn
CCC = DIO + DSO − DPO
Cash released = (Receivables now − target) + (Inventory now − target) + (Payables target − now)`}</Formula>
            <p><b>Common mistake:</b> including non-cash items such as depreciation in a cash budget, or recording sales when invoiced rather than when collected.</p>
          </div>
        </LearnBox>
      </div>
    </div>
  );
}

function LinesEditor({ title, lines, periods, onChange }: { title: string; lines: CashLine[]; periods: string[]; onChange: (l: CashLine[]) => void }) {
  return (
    <Card title={title} flush actions={<button className="btn sm" onClick={() => onChange([...lines, { name: 'New line', values: Array(periods.length).fill(0) }])}><Plus size={14} />Line</button>}>
      <div className="table-wrap" tabIndex={0} style={{ border: 0, borderRadius: 0 }}>
        <table className="data">
          <thead><tr><th>Line</th>{periods.map((p) => <th key={p} className="r">{p}</th>)}<th className="r">Total</th><th /></tr></thead>
          <tbody>
            {lines.map((l, i) => (
              <tr key={i}>
                <td style={{ minWidth: 170 }}><input className="input compact" aria-label="Line name" value={l.name} onChange={(e) => onChange(lines.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} /></td>
                {l.values.map((v, k) => (
                  <td key={k} style={{ minWidth: 118 }}>
                    <NumberField compact ariaLabel={`${l.name} ${periods[k]}`} value={v} min={0} required
                      onChange={(nv) => onChange(lines.map((x, j) => (j === i ? { ...x, values: x.values.map((y, m) => (m === k ? nv : y)) } : x)))} />
                  </td>
                ))}
                <td className="r">{fmtNum(l.values.reduce<number>((a, b) => a + (b ?? 0), 0), 0)}</td>
                <td><button className="btn icon sm ghost" aria-label={`Remove ${l.name}`} onClick={() => onChange(lines.filter((_, j) => j !== i))}><Trash2 size={14} /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function CashBudget() {
  const { settings } = useSettings();
  const cur = settings.currency;
  const [s, setS] = useState<{ data: CBState; isExample: boolean }>(() => loadRaw('fis.cashbudget', { data: EXAMPLE, isExample: true }));
  const set = (d: CBState, example = false) => { const n = { data: d, isExample: example }; setS(n); save('fis.cashbudget', n); };
  const d = s.data;
  const incomplete = d.opening === null || [...d.receipts, ...d.payments].some((l) => l.values.some((v) => v === null) || !l.name.trim());
  const body = useMemo(() => (incomplete ? null : { periods: d.periods, opening_cash: d.opening, minimum_cash: d.minimum ?? 0, receipts: d.receipts, payments: d.payments }), [d, incomplete]);
  const req = useDebounced(body, 150);
  const res = useAsync((signal) => api.post<CBRes>('/api/finance/cash-budget', req, { signal }), [JSON.stringify(req)], !!req);
  const r = res.data;

  const exportCsv = () => {
    if (!r) return;
    const rows: unknown[][] = [['Cash budget', s.isExample ? 'EXAMPLE DATA' : 'User data'], ['Minimum cash', d.minimum ?? 0], [],
      ['Line', ...d.periods, 'Total'], ...d.receipts.map((l) => [`Receipt: ${l.name}`, ...l.values, l.values.reduce<number>((a, b) => a + (b ?? 0), 0)]),
      ...d.payments.map((l) => [`Payment: ${l.name}`, ...l.values, l.values.reduce<number>((a, b) => a + (b ?? 0), 0)]), [],
      ['Opening', ...r.periods.map((p) => p.opening)], ['Net flow', ...r.periods.map((p) => p.net_flow)], ['Financing', ...r.periods.map((p) => p.financing)],
      ['Closing', ...r.periods.map((p) => p.closing)], ['Closing without financing', ...r.periods.map((p) => p.closing_without_financing)], ['Generated', new Date().toISOString()]];
    downloadFile('cash-budget.csv', toCSV(rows));
  };

  return (
    <div className="stack">
      <div className="row between">
        <div className="row">{s.isExample && <Badge tone="sample">Example data</Badge>}</div>
        <div className="row">
          <SaveLoad kind="cash_budget" label="cash budget" getData={() => d} onLoad={(x: CBState) => set(x)} />
          <button className="btn" onClick={() => set(EXAMPLE, true)}><RotateCcw size={15} />Example</button>
          <button className="btn" onClick={exportCsv} disabled={!r}><Download size={15} />Export CSV</button>
        </div>
      </div>
      <div className="grid cols-4">
        <Card><NumberField label="Opening cash" value={d.opening} onChange={(v) => set({ ...d, opening: v })} required /></Card>
        <Card><NumberField label="Minimum cash balance" value={d.minimum} onChange={(v) => set({ ...d, minimum: v })} min={0} hint="Shortfalls below this are financed" /></Card>
        <Kpi label="Peak financing needed" value={r ? fmtMoney(r.total_financing, cur) : '—'} deltaTone={r && r.total_financing > 0 ? 'neg' : 'pos'} delta={r ? (r.total_financing > 0 ? 'Arrange a facility in advance' : 'No financing needed') : undefined} />
        <Kpi label="Cash runway (without financing)"
          value={r ? (r.first_negative_period ? `Runs out ${r.first_negative_period}` : r.runway && isNum(r.runway.months) ? `${fmtNum(r.runway.months, 1)} months` : 'Not burning cash') : '—'}
          deltaTone={r?.first_negative_period ? 'neg' : 'muted'}
          delta={r ? `Lowest unfinanced cash ${fmtMoney(r.lowest_closing_without_financing, cur)} (${r.lowest_period})` : undefined} />
      </div>
      {res.error && <ErrorBox error={res.error} />}
      {incomplete && <Callout tone="warn">Fill in every cell (use 0 where there is no flow) and the opening cash. Blanks are not treated as zero.</Callout>}
      {r && <Warnings items={r.warnings} />}
      {r && (
        <div className="grid cols-2">
          <Card title="Cash balance" subtitle="Closing cash with and without financing, against the minimum balance">
            <div className="chart">
              <ResponsiveContainer>
                <ComposedChart data={r.periods} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid {...gridProps} />
                  <XAxis dataKey="period" {...axisProps} />
                  <YAxis {...axisProps} width={56} tickFormatter={(v) => fmtCompact(v, cur)} />
                  <Tooltip content={<ChartTooltip format={(v) => fmtMoney(v, cur)} />} />
                  <ReferenceLine y={0} stroke="var(--border-strong)" />
                  {isNum(d.minimum) && d.minimum > 0 && <ReferenceLine y={d.minimum} stroke={C.c4} strokeDasharray="5 4" />}
                  <Bar dataKey="financing" name="Financing drawn" fill={C.c3} radius={[4, 4, 0, 0]} maxBarSize={22} />
                  <Line dataKey="closing" name="Closing (with financing)" stroke={C.c1} strokeWidth={2.4} dot={{ r: 2.5 }} />
                  <Line dataKey="closing_without_financing" name="Closing (no financing)" stroke={C.neg} strokeWidth={1.8} strokeDasharray="5 4" dot={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <Legend items={[{ label: 'Closing with financing', color: 'var(--chart-1)' }, { label: 'Without financing', color: 'var(--negative)', dashed: true },
              { label: 'Minimum balance', color: 'var(--chart-4)', dashed: true }, { label: 'Financing drawn', color: 'var(--chart-3)' }]} />
          </Card>
          <Card title="Receipts vs payments" subtitle="Monthly inflows and outflows">
            <div className="chart">
              <ResponsiveContainer>
                <BarChart data={r.periods} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid {...gridProps} />
                  <XAxis dataKey="period" {...axisProps} />
                  <YAxis {...axisProps} width={56} tickFormatter={(v) => fmtCompact(v, cur)} />
                  <Tooltip cursor={{ fill: 'var(--bg-hover)' }} content={<ChartTooltip format={(v) => fmtMoney(v, cur)} />} />
                  <Bar dataKey="receipts" name="Receipts" fill={C.c1} radius={[4, 4, 0, 0]} maxBarSize={16} />
                  <Bar dataKey="payments" name="Payments" fill={C.neg} radius={[4, 4, 0, 0]} maxBarSize={16} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <Legend items={[{ label: 'Receipts', color: 'var(--chart-1)' }, { label: 'Payments', color: 'var(--negative)' }]} />
          </Card>
        </div>
      )}
      {r && (
        <Card title="Cash budget" flush>
          <div className="table-wrap" tabIndex={0} style={{ border: 0, borderRadius: 0 }}>
            <table className="data">
              <thead><tr><th />{r.periods.map((p) => <th key={p.period} className="r">{p.period}</th>)}</tr></thead>
              <tbody>
                {([['Opening cash', 'opening'], ['+ Receipts', 'receipts'], ['− Payments', 'payments'], ['= Net cash flow', 'net_flow'], ['+ Financing', 'financing'], ['Closing cash', 'closing']] as const).map(([label, k]) => (
                  <tr key={k} style={k === 'closing' || k === 'net_flow' ? { fontWeight: 650 } : undefined}>
                    <td>{label}</td>{r.periods.map((p) => <td key={p.period} className={`r ${k === 'net_flow' ? (p.net_flow >= 0 ? 'pos' : 'neg') : ''}`}>{fmtNum(p[k], 0)}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      <LinesEditor title="Receipts (cash in)" lines={d.receipts} periods={d.periods} onChange={(l) => set({ ...d, receipts: l })} />
      <LinesEditor title="Payments (cash out)" lines={d.payments} periods={d.periods} onChange={(l) => set({ ...d, payments: l })} />
      <Callout tone="info">Financing is drawn to restore the minimum balance in any month it is breached. Repayments and interest on that financing are not modelled in this version.</Callout>
    </div>
  );
}

interface WCRes {
  dso: number; dio: number; dpo: number; ccc: number; target_dso: number; target_dio: number; target_dpo: number; target_ccc: number;
  receivables: number; inventory: number; payables: number; target_receivables: number; target_inventory: number; target_payables: number;
  nwc: number; target_nwc: number; cash_released: number; breakdown: Record<string, number>;
}

function WorkingCapital() {
  const { settings } = useSettings();
  const cur = settings.currency;
  const [v, setV] = useState<Record<string, number | null>>({ revenue: 5000, cogs: 3100, receivables: 720, inventory: 610, payables: 430, target_dso: 45, target_dio: 60, target_dpo: 55, days: 365 });
  const ok = Object.values(v).every(isNum);
  const req = useDebounced(ok ? v : null, 150);
  const res = useAsync((signal) => api.post<WCRes>('/api/finance/working-capital', req, { signal }), [JSON.stringify(req)], !!req);
  const r = res.data;
  const f = (k: string, label: string, hint?: string) => <NumberField label={label} value={v[k]} onChange={(n) => setV({ ...v, [k]: n })} required min={0} hint={hint} />;
  const daysChart = r ? [
    { name: 'DSO', current: r.dso, target: r.target_dso }, { name: 'DIO', current: r.dio, target: r.target_dio },
    { name: 'DPO', current: r.dpo, target: r.target_dpo }, { name: 'CCC', current: r.ccc, target: r.target_ccc },
  ] : [];
  return (
    <div className="grid cols-3">
      <div className="stack">
        <Card title="Current position" subtitle="Example inputs — annual flows and closing balances">
          <div className="form-grid">{f('revenue', 'Revenue')}{f('cogs', 'COGS')}{f('receivables', 'Receivables')}{f('inventory', 'Inventory')}{f('payables', 'Payables')}{f('days', 'Days in period')}</div>
        </Card>
        <Card title="Targets">
          <div className="form-grid">{f('target_dso', 'Target DSO', 'days')}{f('target_dio', 'Target DIO', 'days')}{f('target_dpo', 'Target DPO', 'days')}</div>
        </Card>
      </div>
      <div className="span-2 stack">
        {res.error && <ErrorBox error={res.error} />}
        <div className="grid cols-4">
          <Kpi label="Cash conversion cycle" value={r ? `${fmtNum(r.ccc, 1)} days` : '—'} delta={r ? `Target ${fmtNum(r.target_ccc, 1)} days` : undefined} />
          <Kpi label="Net working capital" value={r ? fmtMoney(r.nwc, cur) : '—'} delta={r ? `Target ${fmtMoney(r.target_nwc, cur)}` : undefined} />
          <Kpi label="Cash released at target" value={r ? fmtMoney(r.cash_released, cur) : '—'} deltaTone={r && r.cash_released >= 0 ? 'pos' : 'neg'} delta={r ? (r.cash_released >= 0 ? 'One-off cash inflow' : 'Additional cash tied up') : undefined} />
          <Kpi label="Cash per day of CCC" value={r ? fmtMoney((v.revenue ?? 0) / (v.days || 365), cur) : '—'} delta="≈ revenue per day" />
        </div>
        {r && (
          <div className="grid cols-2">
            <Card title="Days: current vs target">
              <div className="chart">
                <ResponsiveContainer>
                  <BarChart data={daysChart} margin={{ top: 8, right: 8, left: -10, bottom: 0 }}>
                    <CartesianGrid {...gridProps} />
                    <XAxis dataKey="name" {...axisProps} />
                    <YAxis {...axisProps} width={44} />
                    <Tooltip cursor={{ fill: 'var(--bg-hover)' }} content={<ChartTooltip format={(x) => `${fmtNum(x, 1)} days`} />} />
                    <Bar dataKey="current" name="Current" fill={C.c2} radius={[4, 4, 0, 0]} maxBarSize={30} />
                    <Bar dataKey="target" name="Target" fill={C.c1} radius={[4, 4, 0, 0]} maxBarSize={30} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <Legend items={[{ label: 'Current', color: 'var(--chart-2)' }, { label: 'Target', color: 'var(--chart-1)' }]} />
            </Card>
            <Card title="Where the cash comes from">
              {Object.entries(r.breakdown).map(([k, x]) => (
                <div key={k} className="metric-row"><span style={{ textTransform: 'capitalize' }}>{k}</span><span className={`v ${x >= 0 ? 'pos' : 'neg'}`}>{x >= 0 ? '+' : ''}{fmtMoney(x, cur)}</span></div>
              ))}
              <div className="metric-row"><span><b>Total cash released</b></span><span className="v">{fmtMoney(r.cash_released, cur)}</span></div>
              <div className="mt"><Formula>{`Receivables: ${r.target_dso} × revenue / days = ${fmtNum(r.target_receivables, 1)}
Inventory:   ${r.target_dio} × COGS / days = ${fmtNum(r.target_inventory, 1)}
Payables:    ${r.target_dpo} × COGS / days = ${fmtNum(r.target_payables, 1)}`}</Formula></div>
              <p className="faint mt-sm" style={{ fontSize: 12.5 }}>Longer supplier terms release cash but may cost early-payment discounts or supplier goodwill.</p>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}
