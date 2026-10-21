import { Bot, FileSpreadsheet, FileText, Printer } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { SafeMarkdown } from '../components/SafeMarkdown';
import { Badge, Callout, Card, EmptyState, ErrorBox, Field, PageHeader, Skeleton } from '../components/ui';
import { api, downloadPost } from '../lib/api';
import { useAuth } from '../lib/auth';
import { toCompany, useCompanySources, type StatementData } from '../lib/company';
import { useDCFModel } from '../lib/dcfModel';
import { fmtNum, fmtPct, fmtScaled, isNum, type UnitScale } from '../lib/format';
import { useSettings } from '../lib/settings';
import { loadRaw, save } from '../lib/storage';
import { useToast } from '../lib/toast';
import { useAsync } from '../lib/useApi';

type Section = 'statements' | 'ratios' | 'red_flags' | 'valuation' | 'memo';
const SECTIONS: [Section, string, string][] = [
  ['statements', 'Statements', 'Source figures with cell references'],
  ['ratios', 'Ratios', 'Live Excel formulas linked to the statements'],
  ['red_flags', 'Red flags', 'Beneish, Altman, Piotroski and warning signs'],
  ['valuation', 'DCF valuation', 'Live formula model from the DCF page'],
  ['memo', 'Analyst memo', 'Your commentary, or an AI draft you have reviewed'],
];
interface Profile { periods: string[]; series: Record<string, (number | null)[]>; metrics: Record<string, { label: string; unit: string }>; highlights: string[];
  scores: Record<string, { value: number | null; verdict?: string | null; tested?: number }> }
interface DCFOut { enterprise_value: number; equity_value: number; value_per_share: number | null; terminal_value_share_of_ev: number }

export function Reports() {
  const toast = useToast();
  const { user } = useAuth();
  const { settings } = useSettings();
  const { sources } = useCompanySources();
  const { model: dcf, isExample: dcfExample } = useDCFModel();
  const ai = useAsync(() => api.get<{ configured: boolean }>('/api/ai/status'), []);
  const real = (sources ?? []).filter((s) => !s.isExample);
  const [id, setId] = useState<string>(() => loadRaw('fis.dashboard.company', ''));
  const src = real.find((s) => s.id === id) ?? real[0];
  const [data, setData] = useState<StatementData | null>(null);
  const [sections, setSections] = useState<Section[]>(['statements', 'ratios', 'red_flags', 'valuation', 'memo']);
  const [memo, setMemo] = useState<string>(() => loadRaw('fis.reports.memo', ''));
  const [preparedBy, setPreparedBy] = useState(user?.display_name ?? '');
  const [busy, setBusy] = useState<string | null>(null);
  const [aiConsent, setAiConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { if (src) { setData(null); src.load().then(setData).catch(() => setData(null)); } }, [src]);
  const company = useMemo(() => (data ? toCompany(data) : null), [data]);
  const prof = useAsync(() => api.post<Profile>('/api/analysis/profile', company), [JSON.stringify(company)], !!company);
  const useDcf = sections.includes('valuation') && !dcfExample;
  const dcfRes = useAsync(() => api.post<DCFOut>('/api/finance/dcf', dcf), [JSON.stringify(dcf), useDcf], useDcf);
  const units = (data?.units as UnitScale | undefined) ?? settings.units;
  const name = data?.company || src?.name || 'Company';

  const body = () => data && ({
    company: name, periods: data.periods, units, currency: settings.currency, market: data.market ?? {},
    lines: data.lines.map((l) => ({ label: l.label, statement: l.statement, key: l.key, values: l.values, source: l.source ?? null })),
    dcf: useDcf ? dcf : null, memo: sections.includes('memo') && memo.trim() ? memo : null, prepared_by: preparedBy, sections,
  });
  const download = async (kind: 'excel' | 'word') => {
    const b = body();
    if (!b) return;
    setBusy(kind); setError(null);
    try { await downloadPost(`/api/reports/${kind}`, b, `analysis.${kind === 'excel' ? 'xlsx' : 'docx'}`); toast(`${kind === 'excel' ? 'Excel workbook' : 'Word report'} downloaded`); }
    catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  };
  const draftMemo = async () => {
    if (!data || !aiConsent) return;
    setBusy('ai'); setError(null);
    try {
      const r = await api.post<{ reply: string }>('/api/ai/chat', { mode: 'report', consent: true,
        attachments: [{ title: `Financial statements — ${name}`, kind: 'statements', data: { periods: data.periods, units, lines: data.lines, engine_items: company?.items } }],
        messages: [{ role: 'user', content: `Draft a concise analysis memo on ${name} for a professional reader.` }] });
      setMemo(r.reply); save('fis.reports.memo', r.reply);
      toast('AI draft added to the memo — review and edit it before exporting');
    } catch (e) { setError((e as Error).message); } finally { setBusy(null); setAiConsent(false); }
  };
  const toggle = (s: Section) => setSections(sections.includes(s) ? sections.filter((x) => x !== s) : [...sections, s]);
  const p = prof.data;
  const last = (p?.periods.length ?? 1) - 1;
  const fmt = (k: string, v: number | null | undefined) => {
    const u = p?.metrics[k]?.unit;
    if (!isNum(v)) return '—';
    return u === '%' ? fmtPct(v, 1) : u === 'amount' ? fmtScaled(v, units, settings.currency) : u === 'days' ? `${fmtNum(v, 0)} d` : `${fmtNum(v, 2)}×`;
  };

  if (!sources) return <div className="page"><Skeleton h={200} /></div>;
  if (!real.length) return (
    <div className="page">
      <PageHeader title="Reports & Exports" subtitle="Analysis packs in Excel (live formulas), Word and PDF." />
      <EmptyState icon={<FileText size={22} />} title="Import a company first" action={<Link className="btn primary" to="/statements">Go to Financial Statements</Link>}>
        Reports are built from a saved company. Import a Screener export or any statement file, then save it.
      </EmptyState>
    </div>
  );

  return (
    <div className="page">
      <div className="no-print">
        <PageHeader title="Reports & Exports" badge={<Badge tone="accent">Your data</Badge>}
          subtitle="Build a client-ready analysis pack: Excel with live formulas (ratios linked to the statements and a formula-driven DCF), a Word report, or a print-ready PDF."
          actions={<>
            <button className="btn" onClick={() => download('excel')} disabled={!data || !!busy}><FileSpreadsheet size={15} />{busy === 'excel' ? 'Building…' : 'Excel'}</button>
            <button className="btn" onClick={() => download('word')} disabled={!data || !!busy}><FileText size={15} />{busy === 'word' ? 'Building…' : 'Word'}</button>
            <button className="btn primary" onClick={() => window.print()} disabled={!p}><Printer size={15} />Print / PDF</button>
          </>} />
        {error && <ErrorBox error={error} />}
        <div className="grid cols-3">
          <Card title="Pack contents">
            <div className="stack" style={{ gap: 10 }}>
              <Field label="Company">
                <select className="input" value={src?.id} onChange={(e) => setId(e.target.value)}>{real.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
              </Field>
              <Field label="Prepared by"><input className="input" value={preparedBy} maxLength={120} onChange={(e) => setPreparedBy(e.target.value)} /></Field>
              {SECTIONS.map(([k, label, hint]) => (
                <label key={k} className="row" style={{ alignItems: 'flex-start', flexWrap: 'nowrap', fontSize: 13.5 }}>
                  <input type="checkbox" checked={sections.includes(k)} onChange={() => toggle(k)} />
                  <span><b>{label}</b><br /><span className="faint" style={{ fontSize: 12 }}>{hint}</span></span>
                </label>
              ))}
              {sections.includes('valuation') && dcfExample && <Callout tone="warn">The DCF page still has example assumptions, so the valuation section is left out. Enter your assumptions on <Link to="/dcf">DCF Valuation</Link>.</Callout>}
            </div>
          </Card>
          <Card title="Analyst memo" className="span-2" subtitle="Markdown-style headings (#) and bullets (-) are kept in Word and PDF">
            <textarea className="input" rows={10} value={memo} placeholder="Write your conclusions, or draft them with the AI and then edit." onChange={(e) => { setMemo(e.target.value); save('fis.reports.memo', e.target.value); }} />
            {ai.data?.configured && (
              <div className="row mt-sm" style={{ justifyContent: 'space-between' }}>
                <label className="row" style={{ fontSize: 12.5 }}><input type="checkbox" checked={aiConsent} onChange={(e) => setAiConsent(e.target.checked)} />Send {name}'s statements to Anthropic (Claude) to draft the memo.</label>
                <button className="btn" onClick={draftMemo} disabled={!aiConsent || !!busy}><Bot size={15} />{busy === 'ai' ? 'Drafting…' : 'Draft with AI'}</button>
              </div>
            )}
          </Card>
        </div>
        <h3 className="mt" style={{ fontSize: 14, color: 'var(--text-muted)', fontWeight: 600 }}>Preview (this is what Print / PDF produces)</h3>
      </div>

      <article className="print-report card">
        {!p ? <Skeleton h={200} /> : (
          <>
            <header className="pr-head">
              <div><h1>{name}</h1><div className="faint">Financial analysis · {p.periods[0]} – {p.periods[last]} · {settings.currency} {units}{preparedBy ? ` · Prepared by ${preparedBy}` : ''} · {new Date().toLocaleDateString()}</div></div>
            </header>
            <h2>Key metrics</h2>
            <table className="data">
              <thead><tr><th>Metric</th>{p.periods.slice(-5).map((x) => <th key={x} className="r">{x}</th>)}</tr></thead>
              <tbody>{['revenue', 'net_income', 'revenue_growth', 'ebitda_margin', 'net_margin', 'roe', 'roce', 'debt_equity', 'cash_conversion', 'pe']
                .filter((k) => p.series[k]?.some(isNum)).map((k) => (
                  <tr key={k}><td>{p.metrics[k].label}</td>{p.series[k].slice(-5).map((v, i) => <td key={i} className="r">{fmt(k, v)}</td>)}</tr>))}</tbody>
            </table>
            {p.highlights.length > 0 && <><h2>Highlights</h2><ul>{p.highlights.map((h) => <li key={h}>{h}</li>)}</ul></>}
            {sections.includes('red_flags') && (
              <><h2>Screening scores</h2>
                <ul>
                  <li>Beneish M-score: {isNum(p.scores.beneish?.value) ? fmtNum(p.scores.beneish.value, 2) : 'not calculated (inputs missing)'}{p.scores.beneish?.verdict ? ` — ${p.scores.beneish.verdict === 'flag' ? 'flag' : 'no flag'}` : ''}</li>
                  <li>Altman Z''-score: {isNum(p.scores.altman_z2?.value) ? `${fmtNum(p.scores.altman_z2.value, 2)} (${p.scores.altman_z2.verdict} zone)` : 'not calculated (inputs missing)'}</li>
                  <li>Piotroski F-score: {isNum(p.scores.piotroski?.value) ? `${p.scores.piotroski.value} of ${p.scores.piotroski.tested} tests` : '—'}</li>
                </ul></>
            )}
            {useDcf && dcfRes.data && (
              <><h2>Valuation (DCF)</h2>
                <p>Enterprise value {fmtNum(dcfRes.data.enterprise_value, 0, settings.currency)}; equity value {fmtNum(dcfRes.data.equity_value, 0, settings.currency)}
                  {isNum(dcfRes.data.value_per_share) ? `; value per share ${fmtNum(dcfRes.data.value_per_share, 2, settings.currency)}` : ''}. Terminal value is {fmtPct(dcfRes.data.terminal_value_share_of_ev, 0)} of enterprise value
                  (WACC {fmtPct(dcf.wacc, 2)}, terminal growth {fmtPct(dcf.terminal_growth, 2)}).</p></>
            )}
            {sections.includes('memo') && memo.trim() && <><h2>Analyst memo</h2><SafeMarkdown text={memo} /></>}
            <p className="faint pr-foot">Prepared with Finance Intelligence Studio. Derived and approximated lines are labelled in the data. Screening scores indicate where to investigate and are not evidence of misstatement or distress. Analysis, not investment advice.</p>
          </>
        )}
      </article>
    </div>
  );
}
