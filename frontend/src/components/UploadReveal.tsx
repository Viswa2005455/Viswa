import { ArrowRight, Calculator, CheckCircle2, Database, MinusCircle, XCircle } from 'lucide-react';
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../lib/api';
import { fmtBytes, fmtNum, isNum } from '../lib/format';
import { useProjects } from '../lib/project';
import {
  accepted, buildBlocks, inputFromScreener, inputFromUpload, mapRows, type Block, type Decision, type Mapping, type Recommendation,
  type ScreenerImport, type SheetData, type SuggestedStatement, type VarianceSuggestion,
} from '../lib/reveal';
import { loadRaw, save } from '../lib/storage';
import { useAsync } from '../lib/useApi';
import { SheetPreview, type Sheet } from './SheetPreview';
import { Badge, Callout, Card, ErrorBox, Skeleton, Warnings } from './ui';

export interface RevealUpload {
  id: string; name: string; label: string; extension: string; size: number; status: string; project_id?: string | null;
  recommendations: Recommendation[]; statement_mapping: Mapping[]; statements: SuggestedStatement[] | null; variance_lines: VarianceSuggestion | null;
  analysis: { kind: string; warnings?: string[]; sheets?: (Sheet & SheetData)[]; context?: { currencies: Record<string, number>; units: Record<string, number>; periods: string[] } };
}

const SCALE = /\b(?:in\s+)?(?:₹|rs\.?|inr|usd|\$|eur|€|gbp|£)?\s*(lakhs?|crores?|cr\.?|millions?|mn|thousands?|'000|billions?|bn)\b/i;
const SYMBOL = /₹|\[\$₹|\$|€|£|¥/;

/** Facts the file itself states, for the summary: currency and units come only from the file; nothing is assumed. */
function facts(u: RevealUpload, screener: ScreenerImport | null) {
  const sheets = u.analysis.sheets ?? [];
  const cur = new Set(Object.keys(u.analysis.context?.currencies ?? {}));
  sheets.forEach((s) => s.columns.forEach((c) => { const m = c.number_format?.match(SYMBOL); if (m) cur.add(m[0].replace('[$', '')); }));
  const units = new Set(Object.keys(u.analysis.context?.units ?? {}));
  if (screener) units.add(screener.units);
  // Titles such as "Statement of profit and loss (₹ in lakhs)" state the currency and units in words.
  sheets.forEach((s) => [s.name, ...s.columns.map((c) => c.name), ...s.preview.rows.slice(0, 6).flat().map((v) => (typeof v === 'string' ? v : ''))]
    .forEach((t) => {
      const m = t.match(SCALE); if (m) units.add(m[1].toLowerCase());
      const c = t.match(/₹|\bINR\b|\bRs\.?(?=\s|\d)|\$|\bUSD\b|€|\bEUR\b|£|\bGBP\b/i); if (c) cur.add(c[0].toUpperCase() === 'RS' || /^rs/i.test(c[0]) || c[0].toUpperCase() === 'INR' ? '₹' : c[0]);
    }));
  const periods: string[] = screener?.periods ?? [];
  if (!periods.length) (u.statements ?? []).forEach((s) => s.periods.forEach((p) => { if (!periods.includes(p)) periods.push(p); }));
  if (!periods.length) periods.push(...(u.analysis.context?.periods ?? []));
  return { currency: [...cur], units: [...units], periods };
}

const unitOf = (sheet: SheetData, refs: string[]) => {
  const letters = new Set(refs.map((r) => r.match(/^[A-Z]+/)?.[0]).filter(Boolean));
  const fmt = sheet.columns.find((c) => letters.has(c.letter) && c.number_format)?.number_format ?? '';
  return fmt.includes('%') ? '%' : fmt.match(SYMBOL)?.[0].replace('[$', '') ?? '—';
};
const val = (v: number | null | undefined) => (isNum(v) ? fmtNum(v, Math.abs(v) >= 1000 || Number.isInteger(v) ? 0 : 2) : '—');

/** Everything the parser extracted from one upload, then the calculations the engines ran on it. */
export function UploadReveal({ u, preview }: { u: RevealUpload; preview: ReactNode }) {
  // Spreadsheets, and documents (e.g. an annual report PDF) whose statements were read with their years.
  const tabular = u.status === 'processed' && !!u.analysis.sheets?.length &&
    (u.analysis.kind === 'tabular' || !!u.statements?.length || !!u.statement_mapping?.length);
  const leftOut = [...new Set((u.statements ?? []).flatMap((s) => s.projected_left_out ?? []))];
  const isScreener = tabular && !!u.analysis.sheets?.some((s) => s.name.toLowerCase() === 'data sheet');
  const items = useAsync((signal) => api.get<{ items: Record<string, { label: string }> }>('/api/finance/statements/items', { signal }), [], tabular);
  const screener = useAsync((signal) => api.post<ScreenerImport>(`/api/analysis/screener/${u.id}`, {}, { signal }), [u.id], isScreener);
  const key = `fis.reveal.${u.id}`;
  const [state, setState] = useState<{ decisions: Record<string, Decision>; optIn: string[] }>(() => loadRaw(key, { decisions: {}, optIn: [] }));
  useEffect(() => setState(loadRaw(key, { decisions: {}, optIn: [] })), [key]);
  const update = (s: typeof state) => { setState(s); save(key, s); };

  const labels = useMemo(() => Object.fromEntries(Object.entries(items.data?.items ?? {}).map(([k, v]) => [k, v.label])), [items.data]);
  const rows = useMemo(() => mapRows(u.statement_mapping ?? [], u.statements ?? [], labels, u.analysis.sheets ?? []), [u, labels]);
  const sc = isScreener ? screener.data : null;
  const f = facts(u, sc);
  const sheets = u.analysis.sheets ?? [];
  const series = sheets.flatMap((s) => (s.series ?? []).map((x) => ({ sheet: s, s: x })));
  const formulas = sheets.reduce((a, s) => a + (s.formula_count ?? 0), 0);
  const warnings = [...(u.analysis.warnings ?? []), ...sheets.flatMap((s) => s.warnings.map((w) => (sheets.length > 1 ? `${s.name}: ${w}` : w)))];

  return (
    <>
      <Card title={<span className="row"><Database size={17} className="pos" />Data found in this file</span>}
        subtitle="Exactly what was read, with the worksheet and cell each value came from. Please check it before relying on the calculations.">
        <div className="reveal-stats">
          <Stat label="Tables" value={String(sheets.length)} />
          <Stat label="Number series" value={String(series.length)} />
          <Stat label="Formulas found" value={String(formulas)} />
          <Stat label="Periods" value={f.periods.length ? `${f.periods[0]} – ${f.periods[f.periods.length - 1]}` : 'Not detected'} />
          <Stat label="Warnings" value={String(warnings.length)} tone={warnings.length ? 'warn' : undefined} />
        </div>
        <dl className="facts mt">
          <div><dt>File</dt><dd>{u.name}</dd></div>
          <div><dt>Type</dt><dd>{u.label} · {u.analysis.kind}</dd></div>
          <div><dt>Size</dt><dd>{fmtBytes(u.size)}</dd></div>
          <div><dt>Currency</dt><dd>{f.currency.length ? `${f.currency.join(', ')} (from the file — please confirm)` : 'Not stated in the file'}</dd></div>
          <div><dt>Units</dt><dd>{f.units.length ? `${f.units.join(', ')} (from the file — please confirm)` : 'Not stated in the file'}</dd></div>
          <div><dt>Periods</dt><dd>{f.periods.length ? f.periods.join(', ') : 'Not detected'}</dd></div>
          {leftOut.length > 0 && <div><dt>Projections left out</dt><dd>{leftOut.join(', ')} — the model's own forecasts; calculations use the actual years only</dd></div>}
          <div><dt>Status</dt><dd>{u.status === 'processed' ? 'Read successfully' : 'Could not be read'}</dd></div>
        </dl>
        {warnings.length > 0 && <div className="mt"><Warnings items={warnings} /></div>}

        {!tabular ? (
          <div className="mt stack">
            {preview}
            <Callout tone="info">No financial statement or number series was recognised in this file, so no calculations were run.</Callout>
          </div>
        ) : (
          <>
            <h3 className="section-title">Tables</h3>
            <SheetPreview sheets={sheets} excel={['.xlsx', '.xlsm', '.xls'].includes(u.extension)} />

            <h3 className="section-title">Number series ({series.length})</h3>
            {series.length ? <SeriesTable series={series} /> : <p className="faint">No row or column with two or more numbers was found.</p>}

            <h3 className="section-title">How lines were matched to standard items</h3>
            {isScreener ? (
              screener.error ? <ErrorBox error={screener.error} /> : !sc ? <Skeleton h={80} /> :
                <ScreenerMapping sc={sc} optIn={state.optIn} setOptIn={(o) => update({ ...state, optIn: o })} />
            ) : rows.length ? (
              <MappingTable rows={rows} decisions={state.decisions} setDecision={(k, d) => update({ ...state, decisions: { ...state.decisions, [k]: d } })} />
            ) : <p className="faint">No line matched a standard statement item (for example Revenue, Net income, Total assets). Ratios need these.</p>}
          </>
        )}
      </Card>

      <Calculations u={u} tabular={tabular} rowsReady={!tabular || (!!items.data || !!items.error)} sc={sc} screenerPending={isScreener && !sc && !screener.error}
        mapping={rows} decisions={state.decisions} optIn={state.optIn} />
    </>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: 'warn' }) {
  return <div className={`reveal-stat ${tone ?? ''}`}><span>{label}</span><b className="num">{value}</b></div>;
}

function SeriesTable({ series }: { series: { sheet: SheetData; s: NonNullable<SheetData['series']>[number] }[] }) {
  const [all, setAll] = useState(false);
  const shown = all ? series : series.slice(0, 15);
  return (
    <>
      <div className="table-wrap" tabIndex={0}>
        <table className="data">
          <thead><tr><th>Label</th><th>Unit</th><th>First period</th><th>Last period</th><th className="r">First value</th><th className="r">Last value</th><th className="r">Values</th><th>Sheet</th><th>Cells</th></tr></thead>
          <tbody>{shown.map(({ sheet, s }) => (
            <tr key={sheet.name + s.id}>
              <td style={{ whiteSpace: 'normal', minWidth: 140 }}>{s.label}{!!s.calculated_values && <Badge tone="warn">{s.calculated_values} calculated</Badge>}</td>
              <td>{unitOf(sheet, s.refs)}</td><td>{s.period_labels[0]}</td><td>{s.period_labels[s.period_labels.length - 1]}</td>
              <td className="r num">{val(s.values[0])}</td><td className="r num">{val(s.values[s.values.length - 1])}</td><td className="r">{s.values.length}</td>
              <td>{sheet.name}</td><td className="mono">{s.refs[0]}{s.refs.length > 1 ? ` – ${s.refs[s.refs.length - 1]}` : ''}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      {series.length > 15 && <button className="btn sm mt-sm" onClick={() => setAll(!all)}>{all ? 'Show fewer' : `Show all ${series.length} series`}</button>}
    </>
  );
}

function MappingTable({ rows, decisions, setDecision }: { rows: ReturnType<typeof mapRows>; decisions: Record<string, Decision>; setDecision: (k: string, d: Decision) => void }) {
  return (
    <>
      <div className="table-wrap" tabIndex={0}>
        <table className="data">
          <thead><tr><th>Line in your file</th><th>Standard item</th><th>Match</th><th className="r">Latest value</th><th>Period</th><th>Cell</th><th>Use in calculations</th></tr></thead>
          <tbody>{rows.map((r) => {
            const on = accepted(r, decisions);
            const d = decisions[r.key];
            return (
              <tr key={r.key}>
                <td>{r.sourceLabel}</td><td>{r.itemLabel}</td>
                <td>{r.certainty === 'reported' ? <Badge tone="pos">Reported (same name)</Badge> : <Badge tone="warn">Suggested (similar name)</Badge>}</td>
                <td className="r num">{val(r.value)}</td><td>{r.period ?? '—'}</td><td className="mono">{r.sheet && r.cell ? `${r.sheet} · ${r.cell}` : r.sheet ?? '—'}</td>
                <td>
                  <div className="row" style={{ gap: 6, flexWrap: 'nowrap' }}>
                    <button className={`btn sm ${on ? 'primary' : ''}`} aria-pressed={on} onClick={() => setDecision(r.key, 'confirmed')}>{on ? 'Used' : 'Confirm'}</button>
                    <button className={`btn sm ${d === 'rejected' ? 'danger' : 'ghost'}`} aria-pressed={d === 'rejected'} onClick={() => setDecision(r.key, 'rejected')}>Reject</button>
                  </div>
                </td>
              </tr>
            );
          })}</tbody>
        </table>
      </div>
      <p className="faint mt-sm" style={{ fontSize: 12.5 }}>Lines named exactly like the standard item are used straight away. Lines matched by a similar name are used only after you press Confirm. Rejected lines are never used.</p>
    </>
  );
}

function ScreenerMapping({ sc, optIn, setOptIn }: { sc: ScreenerImport; optIn: string[]; setOptIn: (o: string[]) => void }) {
  const last = sc.periods.length - 1;
  return (
    <>
      <div className="table-wrap" tabIndex={0}>
        <table className="data">
          <thead><tr><th>Line</th><th>Type</th><th className="r">{sc.periods[last]}</th><th>Source</th></tr></thead>
          <tbody>
            {sc.lines.map((l) => (
              <tr key={l.label}>
                <td style={{ whiteSpace: 'normal' }}>{l.label}</td>
                <td>{l.source === 'derived' ? <Badge tone="info">Derived</Badge> : <Badge tone="pos">Reported</Badge>}</td>
                <td className="r num">{val(l.values[last])}</td>
                <td className="mono" style={{ fontSize: 11.5 }}>{l.source === 'derived' ? `Derived: ${l.label.match(/\(derived: ([^)]+)\)/)?.[1] ?? 'see label'}` : l.source}</td>
              </tr>
            ))}
            {Object.entries(sc.approximations).map(([k, l]) => (
              <tr key={k}>
                <td style={{ whiteSpace: 'normal' }}>{l.label}</td>
                <td><label className="row" style={{ gap: 6 }}><input type="checkbox" checked={optIn.includes(k)} onChange={(e) => setOptIn(e.target.checked ? [...optIn, k] : optIn.filter((x) => x !== k))} />Approximation (opt-in)</label></td>
                <td className="r num">{val(l.values[last])}</td><td className="faint">Not used unless you tick it</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {sc.notes.map((n) => <p key={n} className="faint mt-sm" style={{ fontSize: 12.5 }}>{n}</p>)}
    </>
  );
}

function Calculations({ u, tabular, rowsReady, sc, screenerPending, mapping, decisions, optIn }: {
  u: RevealUpload; tabular: boolean; rowsReady: boolean; sc: ScreenerImport | null; screenerPending: boolean;
  mapping: ReturnType<typeof mapRows>; decisions: Record<string, Decision>; optIn: string[];
}) {
  const { activeId, setActive } = useProjects();
  const [blocks, setBlocks] = useState<Block[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const ready = tabular && rowsReady && !screenerPending;
  const deps = JSON.stringify([u.id, decisions, optIn, !!sc, mapping.length]);

  useEffect(() => {
    if (!ready) return;
    const ctl = new AbortController();
    setBlocks(null); setError(null);
    const inp = sc ? inputFromScreener(sc, new Set(optIn)) : inputFromUpload(u.statements ?? [], u.analysis.sheets ?? [], mapping, decisions);
    buildBlocks({ inp: inp.lines.length ? inp : null, variance: u.variance_lines, recommendations: u.recommendations, routeFor: (r) => `${r}?file=${u.id}`, signal: ctl.signal })
      .then((b) => { if (!ctl.signal.aborted) setBlocks(b); })
      .catch((e) => { if (!ctl.signal.aborted) setError((e as Error).message); });
    return () => ctl.abort();
  }, [deps, ready]); // eslint-disable-line react-hooks/exhaustive-deps

  const openFull = () => { if (u.project_id && u.project_id !== activeId) setActive(u.project_id); };
  const ran = blocks?.filter((b) => b.status === 'ok').length ?? 0;

  return (
    <Card title={<span className="row"><Calculator size={17} className="pos" />Calculations done</span>}
      subtitle="Calculated by the app's tested engines from the data above. Each row shows the formula, the numbers used, the result and the source cells. Nothing is estimated or filled in.">
      {!tabular ? <p className="muted" style={{ margin: 0 }}>No statement series recognised — calculations not run.</p>
        : error ? <ErrorBox error={error} />
          : !blocks ? <Skeleton h={160} />
            : !blocks.length ? <p className="muted" style={{ margin: 0 }}>No calculation could be run: no line in this file matched a standard statement item, and no analysis was recommended.</p>
              : (
                <div className="stack">
                  <div className="faint" style={{ fontSize: 12.5 }}>{ran} calculation group{ran === 1 ? '' : 's'} run{blocks.length > ran ? ` · ${blocks.length - ran} not run (reasons below)` : ''}</div>
                  {blocks.map((b) => (
                    <section key={b.id} className={`calc-block ${b.status}`}>
                      <header className="row between">
                        <div className="row" style={{ gap: 8 }}>
                          {b.status === 'ok' ? <CheckCircle2 size={16} className="pos" /> : b.status === 'error' ? <XCircle size={16} className="neg" /> : <MinusCircle size={16} className="faint" />}
                          <b>{b.title}</b>
                          <Badge tone={b.status === 'ok' ? 'pos' : b.status === 'gap' ? 'warn' : b.status === 'error' ? 'neg' : undefined}>
                            {b.status === 'ok' ? 'Calculated' : b.status === 'gap' ? 'Inputs missing' : b.status === 'error' ? 'Not calculated' : 'Skipped'}
                          </Badge>
                        </div>
                        {b.route && <Link className="btn sm" to={b.route} onClick={openFull}>Open full page <ArrowRight size={13} /></Link>}
                      </header>
                      {b.rows.length > 0 && (
                        <div className="table-wrap mt-sm" tabIndex={0}>
                          <table className="data calc-table">
                            <thead><tr><th>Metric</th><th>Formula</th><th>Numbers used</th><th className="r">Result</th><th>Unit</th><th>Source</th></tr></thead>
                            <tbody>{b.rows.map((r, i) => (
                              <tr key={i}>
                                <td>{r.metric}{r.note && <div className="faint" style={{ fontSize: 11.5 }}>{r.note}</div>}</td>
                                <td>{r.formula}</td><td className="num">{r.substituted}</td><td className="r num"><b>{r.result}</b></td><td>{r.unit}</td>
                                <td className="mono" style={{ fontSize: 11.5 }}>{r.source}</td>
                              </tr>
                            ))}</tbody>
                          </table>
                        </div>
                      )}
                      {!!b.more && <div className="faint mt-sm" style={{ fontSize: 12 }}>{b.more} more on the full page.</div>}
                      {b.message && <div className={`mt-sm ${b.status === 'ok' ? 'faint' : ''}`} style={{ fontSize: 12.5 }}>{b.message}</div>}
                    </section>
                  ))}
                </div>
              )}
    </Card>
  );
}
