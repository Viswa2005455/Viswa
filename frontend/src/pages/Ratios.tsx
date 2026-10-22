import { Download, FileUp, RotateCcw } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Badge, Callout, Card, ErrorBox, Formula, LearnBox, NumberField, PageHeader, Tabs } from '../components/ui';
import { SaveLoad } from '../components/SaveLoad';
import { api } from '../lib/api';
import { downloadFile, fmtNum, fmtRatio, isNum, toCSV } from '../lib/format';
import { useSettings } from '../lib/settings';
import { useToast } from '../lib/toast';
import type { UploadSummary } from '../lib/types';
import { useAsync, useDebounced } from '../lib/useApi';

interface Ratio {
  key: string; name: string; category: string; formula: string; unit: string; value: number | null; status: 'ok' | 'missing' | 'undefined';
  inputs: Record<string, number>; steps: string; interpretation: string; notes: string[]; missing: string[];
}
interface Mapping { item: string; item_label: string; source_label: string; value: number; source: string; period: string; prior_value: number | null; prior_source: string | null; prior_period: string | null }

type Data = Record<string, number | null>;
const GROUPS: { title: string; items: [string, string][]; prior?: boolean }[] = [
  { title: 'Income statement', items: [['revenue', 'Revenue'], ['cogs', 'Cost of goods sold'], ['operating_income', 'Operating income (EBIT)'], ['depreciation_amortization', 'Depreciation & amortisation'], ['interest_expense', 'Interest expense'], ['net_income', 'Net income']] },
  { title: 'Balance sheet (closing)', prior: true, items: [['cash', 'Cash & equivalents'], ['marketable_securities', 'Marketable securities'], ['receivables', 'Accounts receivable'], ['inventory', 'Inventory'], ['current_assets', 'Current assets'], ['total_assets', 'Total assets'], ['current_liabilities', 'Current liabilities'], ['accounts_payable', 'Accounts payable'], ['total_debt', 'Total debt'], ['total_liabilities', 'Total liabilities'], ['total_equity', "Shareholders' equity"]] },
  { title: 'Cash flow, tax & market', items: [['operating_cash_flow', 'Operating cash flow'], ['debt_service', 'Debt service (interest + principal)'], ['tax_rate', 'Effective tax rate'], ['shares_outstanding', 'Shares outstanding'], ['share_price', 'Share price']] },
];
const AVERAGEABLE = new Set(['receivables', 'inventory', 'total_assets', 'accounts_payable', 'total_equity', 'total_debt']);

const EXAMPLE: Data = {
  revenue: 5000, cogs: 3100, operating_income: 620, depreciation_amortization: 180, interest_expense: 95, net_income: 390,
  cash: 260, marketable_securities: 40, receivables: 720, inventory: 610, current_assets: 1700, total_assets: 4200, current_liabilities: 980,
  accounts_payable: 430, total_debt: 1150, total_liabilities: 2300, total_equity: 1900, operating_cash_flow: 560, debt_service: 310, tax_rate: 0.25,
  shares_outstanding: 100, share_price: 58,
  receivables_prior: 660, inventory_prior: 560, total_assets_prior: 3900, accounts_payable_prior: 400, total_equity_prior: 1720, total_debt_prior: 1200,
};

export function Ratios() {
  const { settings } = useSettings();
  const toast = useToast();
  const [params] = useSearchParams();
  const [data, setData] = useState<Data>(EXAMPLE);
  const [isExample, setIsExample] = useState(true);
  const [days, setDays] = useState<number | null>(365);
  const [cat, setCat] = useState('All');
  const [sources, setSources] = useState<Record<string, string>>({});
  const [pending, setPending] = useState<{ file: string; rows: (Mapping & { accept: boolean })[] } | null>(null);

  const uploads = useAsync((signal) => api.get<{ uploads: UploadSummary[] }>('/api/uploads', { signal }), []);
  const candidates = uploads.data?.uploads.filter((u) => u.recommendations.some((r) => r.module === 'Ratio Analysis')) ?? [];
  const loadMapping = async (id: string) => {
    try {
      const rec = await api.get<{ name: string; statement_mapping: Mapping[] }>(`/api/uploads/${id}`);
      if (!rec.statement_mapping.length) { toast('No recognisable statement lines found', 'error'); return; }
      setPending({ file: rec.name, rows: rec.statement_mapping.map((m) => ({ ...m, accept: true })) });
    } catch (e) { toast((e as Error).message, 'error'); }
  };
  const fileParam = params.get('file');
  useEffect(() => { if (fileParam) loadMapping(fileParam); }, [fileParam]); // eslint-disable-line react-hooks/exhaustive-deps

  const applyMapping = () => {
    if (!pending) return;
    const next: Data = {};
    const src: Record<string, string> = {};
    pending.rows.filter((r) => r.accept).forEach((r) => {
      next[r.item] = r.value; src[r.item] = `${r.source} (${r.period})`;
      if (AVERAGEABLE.has(r.item) && isNum(r.prior_value)) { next[`${r.item}_prior`] = r.prior_value; src[`${r.item}_prior`] = `${r.prior_source} (${r.prior_period})`; }
    });
    setData(next); setSources(src); setIsExample(false); setPending(null);
    toast(`Applied ${Object.keys(next).length} confirmed values`);
  };

  const body = useMemo(() => ({ data: Object.fromEntries(Object.entries(data).filter(([, v]) => isNum(v))), period_days: days ?? 365 }), [data, days]);
  const req = useDebounced(body, 150);
  const res = useAsync((signal) => api.post<{ ratios: Ratio[] }>('/api/finance/ratios', req, { signal }), [JSON.stringify(req)]);
  const ratios = res.data?.ratios ?? [];
  const cats = ['All', ...Array.from(new Set(ratios.map((r) => r.category)))];
  const shown = ratios.filter((r) => cat === 'All' || r.category === cat);
  const set = (k: string, v: number | null) => { setIsExample(false); setData((d) => ({ ...d, [k]: v })); setSources((s) => { const n = { ...s }; delete n[k]; return n; }); };

  const exportCsv = () => {
    const rows: unknown[][] = [['Ratio analysis', isExample ? 'EXAMPLE DATA' : 'User data'], ['Period days', days], [],
      ['Category', 'Ratio', 'Value', 'Unit', 'Status', 'Formula', 'Calculation', 'Interpretation', 'Notes'],
      ...ratios.map((r) => [r.category, r.name, r.value ?? '', r.unit, r.status, r.formula, r.steps, r.interpretation, [...r.notes, ...(r.missing.length ? [`Missing: ${r.missing.join(', ')}`] : [])].join(' ')]),
      [], ['Input', 'Value', 'Source'], ...Object.entries(body.data).map(([k, v]) => [k, v, sources[k] ?? (isExample ? 'example' : 'manual entry')]), ['Generated', new Date().toISOString()]];
    downloadFile('ratio-analysis.csv', toCSV(rows));
  };

  return (
    <div className="page">
      <PageHeader title="Ratio Analysis" badge={isExample ? <Badge tone="sample">Example data</Badge> : undefined}
        subtitle="Liquidity, profitability, efficiency, leverage and valuation ratios — each with its formula, inputs, calculation, interpretation and limitations."
        actions={<>
          <SaveLoad kind="ratios" label="ratio inputs" getData={() => ({ data, days, sources })}
            onLoad={(d: { data: Data; days: number | null; sources?: Record<string, string> }) => { setData(d.data); setDays(d.days); setSources(d.sources ?? {}); setIsExample(false); }} />
          <button className="btn" onClick={() => { setData(EXAMPLE); setIsExample(true); setSources({}); }}><RotateCcw size={15} />Example</button>
          <button className="btn" onClick={() => { setData({}); setIsExample(false); setSources({}); }}>Clear</button>
          <button className="btn" onClick={exportCsv} disabled={!ratios.length}><Download size={15} />Export CSV</button>
        </>} />

      {pending && (
        <Card title={`Confirm values from ${pending.file}`} subtitle="Matched by line-item name; the latest period is used, with the previous period as the opening balance. Untick anything that is wrong.">
          <div className="table-wrap" tabIndex={0}>
            <table className="data">
              <thead><tr><th>Use</th><th>Engine item</th><th>Label in file</th><th className="r">Value</th><th>Period</th><th className="r">Prior</th><th>Source</th></tr></thead>
              <tbody>{pending.rows.map((m, i) => (
                <tr key={m.item}>
                  <td><input type="checkbox" checked={m.accept} aria-label={`Use ${m.item_label}`} onChange={(e) => setPending({ ...pending, rows: pending.rows.map((r, j) => j === i ? { ...r, accept: e.target.checked } : r) })} /></td>
                  <td>{m.item_label}</td><td>{m.source_label}</td><td className="r">{fmtNum(m.value, 2)}</td><td>{m.period}</td>
                  <td className="r">{AVERAGEABLE.has(m.item) && isNum(m.prior_value) ? fmtNum(m.prior_value, 2) : ''}</td><td className="mono" style={{ fontSize: 11.5 }}>{m.source}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <div className="row mt"><button className="btn primary" onClick={applyMapping}>Apply confirmed values</button><button className="btn" onClick={() => setPending(null)}>Cancel</button></div>
          <div className="mt-sm"><Callout tone="warn">Check that every value uses the same currency, units and reporting period before applying.</Callout></div>
        </Card>
      )}

      <div className="grid cols-3 mt">
        <div className="stack">
          <Card title="Import from an upload">
            {candidates.length ? <div className="row">{candidates.map((u) => <button key={u.id} className="btn sm" onClick={() => loadMapping(u.id)}><FileUp size={14} />{u.name}</button>)}</div>
              : <p className="muted">Upload an income statement or balance sheet (Excel/CSV with line items in the first column). <Link to="/upload">Upload</Link></p>}
          </Card>
          {GROUPS.map((g) => (
            <Card key={g.title} title={g.title} subtitle={g.prior ? 'Opening (prior) balances enable average-balance ratios' : 'Same currency and units for all values'}>
              <div className="stack" style={{ gap: 8 }}>
                {g.items.map(([k, label]) => (
                  <div key={k} className={g.prior && AVERAGEABLE.has(k) ? 'grid cols-2' : ''} style={{ gap: 8 }}>
                    <NumberField label={label} percent={k === 'tax_rate'} value={data[k] ?? null} onChange={(v) => set(k, v)}
                      hint={sources[k] ? <span title={sources[k]}>From {sources[k].split(' › ').slice(-1)[0]}</span> : undefined} />
                    {g.prior && AVERAGEABLE.has(k) && <NumberField label="Opening" value={data[`${k}_prior`] ?? null} onChange={(v) => set(`${k}_prior`, v)} />}
                  </div>
                ))}
              </div>
            </Card>
          ))}
          <Card title="Period length">
            <NumberField label="Days in period" value={days} onChange={setDays} min={1} max={366} hint="365 for annual, 90/91 for a quarter — used for DSO, DIO, DPO" />
          </Card>
        </div>

        <div className="span-2 stack">
          <div className="row between">
            <Tabs label="Category" value={cat} onChange={setCat} options={cats.map((c) => ({ value: c, label: c }))} />
            <span className="faint" style={{ fontSize: 12.5 }}>{ratios.filter((r) => r.status === 'ok').length} of {ratios.length} calculable</span>
          </div>
          {res.error && <ErrorBox error={res.error} />}
          <div className="grid cols-2">
            {shown.map((r) => (
              <Card key={r.key} title={r.name} subtitle={r.category} actions={r.status === 'ok' ? <b className="num" style={{ fontSize: 18 }}>{fmtRatio(r.value, r.unit, settings.currency)}</b>
                : <Badge tone={r.status === 'missing' ? 'warn' : 'neg'}>{r.status === 'missing' ? 'Missing inputs' : 'Not meaningful'}</Badge>}>
                <Formula>{r.formula}</Formula>
                {r.steps && <div className="mono mt-sm" style={{ fontSize: 12, color: 'var(--text-muted)' }}>{r.steps}</div>}
                {r.interpretation && <p className="mt-sm" style={{ fontSize: 13 }}>{r.interpretation}</p>}
                {r.missing.length > 0 && <p className="mt-sm faint" style={{ fontSize: 12.5 }}>Needs: {r.missing.join(', ')}</p>}
                {r.notes.filter((n) => !n.startsWith('Cannot calculate')).map((n) => <p key={n} className="mt-sm faint" style={{ fontSize: 12 }}>{n}</p>)}
              </Card>
            ))}
          </div>
          <Callout tone="info" title="Limitations">
            Ratios are only comparable across companies with similar industries, accounting policies, capital structures and reporting periods.
            A single-period ratio says little on its own — compare trends over several periods and against peers.
          </Callout>
          <LearnBox title="Reading ratios">
            <div className="stack" style={{ fontSize: 13 }}>
              <p><b>Liquidity</b> ratios test whether short-term obligations can be met. <b>Profitability</b> ratios show how much of revenue or capital turns into profit. <b>Efficiency</b> ratios show how quickly assets turn over. <b>Leverage</b> ratios show reliance on debt and the ability to service it.</p>
              <p>Use <b>average balances</b> for ratios that mix a flow (revenue, COGS, net income) with a stock (assets, receivables), because the flow accrues over the whole period.</p>
              <p><b>Common mistakes:</b> computing ROE with negative equity, mixing quarterly income with annual days, and comparing a retailer's inventory turnover with a software company's.</p>
            </div>
          </LearnBox>
        </div>
      </div>
    </div>
  );
}
