import { Download } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { C, ChartTooltip, Legend, axisProps, gridProps } from '../components/charts';
import { Badge, Callout, Card, ErrorBox, Field, Kpi, LearnBox, NumberField, PageHeader, Tabs, Warnings } from '../components/ui';
import { api } from '../lib/api';
import { downloadFile, fmtCompact, fmtNum, fmtPct, fmtPctPoints, isNum, parseInputNumber, toCSV } from '../lib/format';
import type { Series } from '../lib/types';
import { useAsync, useDebounced } from '../lib/useApi';

type Method = 'linear' | 'moving_average' | 'ses' | 'cagr';
interface FcRes {
  method: Method; history: number[]; forecast: number[]; lower: (number | null)[]; upper: (number | null)[]; fitted: (number | null)[];
  params: Record<string, number>; backtest: { holdout: number; mae: number | null; rmse: number | null; mape: number | null }; confidence: number; notes: string[];
}

const EXAMPLE = '182, 191.5, 176.2, 188.9, 205.3, 199.8, 214.6, 221, 218.4, 230.7, 238.1, 245.9';
const METHODS: { value: Method; label: string }[] = [
  { value: 'linear', label: 'Linear trend' }, { value: 'ses', label: 'Exponential smoothing' },
  { value: 'moving_average', label: 'Moving average' }, { value: 'cagr', label: 'Constant growth (CAGR)' },
];

export function Forecasting() {
  const [params] = useSearchParams();
  const fileParam = params.get('file');
  const [source, setSource] = useState<'manual' | 'upload'>(fileParam ? 'upload' : 'manual');
  const [text, setText] = useState(EXAMPLE);
  const [seriesKey, setSeriesKey] = useState<string>('');
  const [method, setMethod] = useState<Method>('linear');
  const [horizon, setHorizon] = useState<number | null>(6);
  const [conf, setConf] = useState<number | null>(0.95);
  const [window, setWindow] = useState<number | null>(3);
  const [alpha, setAlpha] = useState<number | null>(null);
  const [holdout, setHoldout] = useState<number | null>(null);

  const series = useAsync((signal) => api.get<{ series: Series[] }>('/api/uploads/series', { signal }), []);
  const options = series.data?.series ?? [];
  useEffect(() => {
    if (!seriesKey && options.length) {
      const pool = options.filter((s) => !fileParam || s.upload_id === fileParam);
      const pick = pool.find((s) => /revenue|sales/i.test(s.label)) ?? pool[0] ?? options[0];
      setSeriesKey(`${pick.upload_id}|${pick.sheet}|${pick.series_id}`);
    }
  }, [options, seriesKey, fileParam]);
  const chosen = options.find((s) => `${s.upload_id}|${s.sheet}|${s.series_id}` === seriesKey);

  const manualTokens = text.split(/[\s,;]+/).filter(Boolean);
  const manualValues = manualTokens.map(parseInputNumber);
  const manualBad = manualTokens.filter((_, i) => manualValues[i] === null);
  const values = source === 'upload' ? chosen?.values ?? [] : manualValues.filter(isNum);
  const labels = source === 'upload' ? chosen?.period_labels ?? [] : values.map((_, i) => `P${i + 1}`);
  const isExample = source === 'manual' && text === EXAMPLE;

  const body = useMemo(() => (values.length >= 2 && isNum(horizon) && isNum(conf) && (source === 'upload' || manualBad.length === 0) ? {
    series: values, method, horizon, confidence: conf, window: window ?? 3, alpha, holdout,
  } : null), [values.join(','), method, horizon, conf, window, alpha, holdout, source, manualBad.length]); // eslint-disable-line react-hooks/exhaustive-deps
  const req = useDebounced(body, 150);
  const res = useAsync((signal) => api.post<FcRes>('/api/finance/forecast', req, { signal }), [JSON.stringify(req)], !!req);
  const r = res.data;

  const chart = r ? [
    ...r.history.map((v, i) => ({ label: labels[i] ?? `P${i + 1}`, actual: v, fitted: r.fitted[i], forecast: i === r.history.length - 1 ? v : null, band: null as [number, number] | null })),
    ...r.forecast.map((v, i) => ({ label: `F+${i + 1}`, forecast: v, band: isNum(r.lower[i]) && isNum(r.upper[i]) ? [r.lower[i], r.upper[i]] as [number, number] : null })),
  ] : [];

  const exportCsv = () => {
    if (!r) return;
    const rows: unknown[][] = [['Forecast', METHODS.find((m) => m.value === r.method)?.label], ['Source', source === 'upload' ? chosen?.source : isExample ? 'EXAMPLE DATA' : 'Manual entry'],
      ['Confidence', r.confidence], [], ['Period', 'Type', 'Value', 'Lower', 'Upper', 'Source cell'],
      ...r.history.map((v, i) => [labels[i] ?? `P${i + 1}`, 'Actual', v, '', '', source === 'upload' ? chosen?.refs[i] : '']),
      ...r.forecast.map((v, i) => [`F+${i + 1}`, 'Forecast (estimate)', v, r.lower[i] ?? '', r.upper[i] ?? '', '']), [],
      ['Backtest MAE', r.backtest.mae ?? 'n/a'], ['Backtest RMSE', r.backtest.rmse ?? 'n/a'], ['Backtest MAPE %', r.backtest.mape ?? 'n/a'], ['Generated', new Date().toISOString()]];
    downloadFile('forecast.csv', toCSV(rows));
  };

  return (
    <div className="page">
      <PageHeader title="Forecasting" badge={isExample ? <Badge tone="sample">Example data</Badge> : undefined}
        subtitle="Project a revenue, expense or cash series. Accuracy is measured on a time-aware holdout (the model never sees the periods it is scored on)."
        actions={<button className="btn" onClick={exportCsv} disabled={!r}><Download size={15} />Export CSV</button>} />
      <div className="grid cols-3">
        <div className="stack">
          <Card title="Data">
            <Tabs label="Data source" value={source} onChange={setSource} options={[{ value: 'manual', label: 'Enter values' }, { value: 'upload', label: 'From an upload' }]} />
            <div className="mt">
              {source === 'manual' ? (
                <Field label="Historical values (oldest first)" hint="Separate with commas, spaces or new lines. Blank or text values are rejected, not treated as zero.">
                  <textarea className="input" rows={5} value={text} onChange={(e) => setText(e.target.value)} />
                </Field>
              ) : options.length === 0 ? (
                <Callout tone="info">No numeric series with 3+ values found in your uploads. <Link to="/upload">Upload a spreadsheet or CSV</Link>.</Callout>
              ) : (
                <Field label="Series" hint={chosen ? `Source: ${chosen.source}` : undefined}>
                  <select className="input" value={seriesKey} onChange={(e) => setSeriesKey(e.target.value)}>
                    {options.map((s) => <option key={`${s.upload_id}|${s.sheet}|${s.series_id}`} value={`${s.upload_id}|${s.sheet}|${s.series_id}`}>{s.file} › {s.sheet} › {s.label} ({s.values.length})</option>)}
                  </select>
                </Field>
              )}
              {manualBad.length > 0 && source === 'manual' && <div className="mt-sm"><Callout tone="error">Not a number: {manualBad.slice(0, 5).join(', ')}</Callout></div>}
              <div className="faint mt-sm" style={{ fontSize: 12 }}>{values.length} observations</div>
            </div>
          </Card>
          <Card title="Method">
            <div className="stack">
              <Field label="Forecast method">
                <select className="input" value={method} onChange={(e) => setMethod(e.target.value as Method)}>
                  {METHODS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                </select>
              </Field>
              <div className="form-grid">
                <NumberField label="Horizon (periods)" value={horizon} onChange={setHorizon} min={1} max={60} required />
                <NumberField label="Interval confidence" percent value={conf} onChange={setConf} min={50} max={99} required />
                {method === 'moving_average' && <NumberField label="Window" value={window} onChange={setWindow} min={1} required />}
                {method === 'ses' && <NumberField label="Alpha (blank = optimise)" value={alpha} onChange={setAlpha} min={0.01} max={1} />}
                <NumberField label="Holdout periods" value={holdout} onChange={setHoldout} min={1} hint="Blank = 25% of history" />
              </div>
            </div>
          </Card>
        </div>

        <div className="span-2 stack">
          {res.error && <ErrorBox error={res.error} />}
          <div className="grid cols-4">
            <Kpi label={`Backtest MAE (${r?.backtest.holdout ?? '—'} periods)`} value={r ? fmtNum(r.backtest.mae, 2) : '—'} />
            <Kpi label="Backtest RMSE" value={r ? fmtNum(r.backtest.rmse, 2) : '—'} />
            <Kpi label="Backtest MAPE" value={r ? (isNum(r.backtest.mape) ? fmtPctPoints(r.backtest.mape, 1) : 'n/a') : '—'} />
            <Kpi label={`Forecast F+${r?.forecast.length ?? ''}`} value={r ? fmtNum(r.forecast[r.forecast.length - 1], 1) : '—'} />
          </div>
          <Card title="History and forecast" subtitle="Forecast values are estimates, not guarantees.">
            <div className="chart tall">
              <ResponsiveContainer>
                <ComposedChart data={chart} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid {...gridProps} />
                  <XAxis dataKey="label" {...axisProps} minTickGap={12} />
                  <YAxis {...axisProps} width={56} tickFormatter={(v) => fmtCompact(v)} domain={['auto', 'auto']} />
                  <Tooltip content={<ChartTooltip format={(v) => fmtNum(v, 2)} />} />
                  {r && <ReferenceLine x={labels[r.history.length - 1] ?? `P${r.history.length}`} stroke="var(--border-strong)" strokeDasharray="3 3" />}
                  <Area dataKey="band" name={`${Math.round((r?.confidence ?? 0.95) * 100)}% interval`} stroke="none" fill={C.band} />
                  <Line dataKey="actual" name="Actual" stroke={C.c1} strokeWidth={2.4} dot={{ r: 2.5 }} />
                  <Line dataKey="fitted" name="Fitted" stroke={C.c3} strokeWidth={1.5} strokeDasharray="2 3" dot={false} />
                  <Line dataKey="forecast" name="Forecast" stroke={C.c2} strokeWidth={2.4} strokeDasharray="6 4" dot={{ r: 2.5 }} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <Legend items={[{ label: 'Actual', color: 'var(--chart-1)' }, { label: 'Fitted (in-sample)', color: 'var(--chart-3)', dashed: true },
              { label: 'Forecast', color: 'var(--chart-2)', dashed: true }, { label: 'Prediction interval', color: 'var(--chart-band)' }]} />
          </Card>
          {r && (
            <div className="grid cols-2">
              <Card title="Forecast values" flush>
                <div className="table-wrap" tabIndex={0} style={{ border: 0, borderRadius: 0, maxHeight: 300 }}>
                  <table className="data">
                    <thead><tr><th>Period</th><th className="r">Forecast</th><th className="r">Lower</th><th className="r">Upper</th></tr></thead>
                    <tbody>{r.forecast.map((v, i) => (
                      <tr key={i}><td>F+{i + 1}</td><td className="r">{fmtNum(v, 2)}</td><td className="r">{fmtNum(r.lower[i], 2)}</td><td className="r">{fmtNum(r.upper[i], 2)}</td></tr>
                    ))}</tbody>
                  </table>
                </div>
              </Card>
              <Card title="Model">
                {Object.entries(r.params).map(([k, v]) => (
                  <div key={k} className="metric-row"><span className="muted">{k.replace('_', ' ')}</span><span className="v">{k === 'growth_rate' ? fmtPct(v, 2) : fmtNum(v, 4)}</span></div>
                ))}
                <div className="mt"><Warnings items={r.notes} /></div>
              </Card>
            </div>
          )}
          <LearnBox title="Forecast methods and error metrics">
            <div className="stack" style={{ fontSize: 13 }}>
              <p><b>Linear trend</b> fits y = a + b·t by least squares; the interval widens with distance from the data. <b>Exponential smoothing</b> weights recent observations by α. <b>Moving average</b> projects a flat level. <b>CAGR</b> compounds the average growth between the first and last value.</p>
              <p><b>MAE</b> is the average absolute error; <b>RMSE</b> penalises large errors more; <b>MAPE</b> is the average % error (undefined if any actual is zero).</p>
              <p><b>Common mistake:</b> judging a model on the same data it was fitted to. The holdout here is the most recent periods, which the model never sees during fitting.</p>
            </div>
          </LearnBox>
        </div>
      </div>
    </div>
  );
}
