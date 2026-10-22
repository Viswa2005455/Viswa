import { AlertTriangle, Bot, ShieldAlert } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Badge, Callout, Card, EmptyState, ErrorBox, Formula, Kpi, LearnBox, NumberField, PageHeader, Skeleton } from '../components/ui';
import { api } from '../lib/api';
import { toCompany, useCompanySources, type CompanyData } from '../lib/company';
import { fmtNum, isNum } from '../lib/format';
import { loadRaw, save } from '../lib/storage';
import { useAsync, useDebounced } from '../lib/useApi';

interface Component { key: string; name: string; formula: string; value: number | null; inputs: Record<string, number | null>; missing: string[]; note: string }
interface Score {
  key: string; name: string; model: string; status: 'ok' | 'missing'; value: number | null; verdict: string | null; verdict_text: string;
  thresholds: string; formula: string; period: string; components: Component[]; missing: string[]; notes: string[]; limitations: string;
}
interface Report {
  periods: string[]; current: string; prior: string; beneish: Score; altman: Score[];
  piotroski: { status: string; period: string; score: number; tested: number; criteria: { name: string; test: string; result: 'pass' | 'fail' | 'missing'; detail: string }[]; verdict_text: string; notes: string[] };
  flags: { severity: 'high' | 'medium' | 'low'; title: string; detail: string; period: string | null }[];
  derived: string[]; disclaimer: string;
}

/** Fictional company used only when the user has no statements yet; always labelled as an example. */
const EXAMPLE: CompanyData = {
  periods: ['FY2023', 'FY2024', 'FY2025'],
  items: {
    revenue: [1000, 1200, 1500], cogs: [600, 700, 900], sga: [120, 140, 170], depreciation_amortization: [50, 60, 70],
    operating_income: [150, 200, 240], interest_expense: [20, 15, 10], other_income: [10, 12, 60], pretax_income: [140, 197, 290],
    net_income: [100, 140, 175], receivables: [150, 180, 300], inventory: [100, 120, 150], current_assets: [350, 420, 590],
    ppe: [600, 640, 690], total_assets: [1000, 1150, 1350], current_liabilities: [200, 230, 260], long_term_debt: [300, 290, 340],
    total_debt: [300, 290, 340], total_liabilities: [500, 570, 650], total_equity: [500, 580, 700], retained_earnings: [300, 380, 500],
    operating_cash_flow: [90, 120, 110],
  },
};

const ZONE_TONE: Record<string, 'accent' | 'warn' | 'neg'> = { safe: 'accent', no_flag: 'accent', grey: 'warn', distress: 'neg', flag: 'neg' };
const ZONE_LABEL: Record<string, string> = { safe: 'Safe zone', grey: 'Grey zone', distress: 'Distress zone', flag: 'Red flag', no_flag: 'No flag' };
const SEV_TONE = { high: 'neg', medium: 'warn', low: 'info' } as const;

export function RedFlags() {
  const { sources, error: srcError } = useCompanySources();
  const [sourceId, setSourceId] = useState<string>(() => loadRaw('fis.redflags.source', ''));
  const [company, setCompany] = useState<{ data: CompanyData; name: string; isExample: boolean } | null>(null);
  const [market, setMarket] = useState<Record<string, { price: number | null; shares: number | null }>>(() => loadRaw('fis.redflags.market', {}));

  const chosen = useMemo(() => sources?.find((s) => s.id === sourceId) ?? sources?.find((s) => !s.isExample) ?? sources?.[0], [sources, sourceId]);
  useEffect(() => {
    if (!sources) return;
    if (!chosen) { setCompany({ data: EXAMPLE, name: 'Example company (fictional)', isExample: true }); return; }
    chosen.load().then((d) => setCompany({ data: toCompany(d), name: chosen.name, isExample: chosen.isExample }))
      .catch(() => setCompany(null));
  }, [sources, chosen]);

  const setM = (p: string, k: 'price' | 'shares', v: number | null) => {
    const next = { ...market, [p]: { price: market[p]?.price ?? null, shares: market[p]?.shares ?? null, [k]: v } };
    setMarket(next);
    save('fis.redflags.market', next);
  };

  const body = useMemo(() => {
    if (!company) return null;
    const { periods, items } = company.data;
    const extra: Record<string, (number | null)[]> = {};
    const price = periods.map((p) => market[p]?.price ?? null);
    const shares = periods.map((p) => market[p]?.shares ?? null);
    if (price.some(isNum)) extra.share_price = price;
    if (shares.some(isNum)) extra.shares_outstanding = shares;
    return { periods, items: { ...items, ...extra } };
  }, [company, market]);
  const req = useDebounced(body, 150);
  const res = useAsync((signal) => api.post<Report>('/api/analysis/forensic', req, { signal }), [JSON.stringify(req)], !!req && (req?.periods.length ?? 0) >= 2);
  const r = res.data;
  const tooFew = !!company && company.data.periods.length < 2;

  return (
    <div className="page">
      <PageHeader title="Red-Flag Detector" badge={company?.isExample ? <Badge tone="sample">Example data</Badge> : company ? <Badge tone="accent">Your data</Badge> : undefined}
        subtitle="Screens a company's statements for warning signs: earnings manipulation (Beneish M-score), financial distress (Altman Z-score), financial strength (Piotroski F-score) and cash-quality checks."
        actions={r && <Link className="btn" to="/assistant?topic=red-flags"><Bot size={15} />Explain with AI</Link>} />

      <div className="grid cols-3 mt">
        <div className="stack">
          <Card title="Company data" subtitle="Uses the statements you imported or saved on the Financial Statements page">
            {!sources ? <Skeleton h={36} /> : (
              <div className="stack" style={{ gap: 10 }}>
                <select className="input" aria-label="Company data source" value={chosen?.id ?? ''} onChange={(e) => { setSourceId(e.target.value); save('fis.redflags.source', e.target.value); }}>
                  {!sources.length && <option value="">Example company (fictional)</option>}
                  {sources.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
                {srcError && <Callout tone="warn">Could not load saved statements: {srcError}</Callout>}
                <p className="faint" style={{ fontSize: 12.5 }}>
                  To analyse a real company, import its file on <Link to="/statements">Financial Statements</Link>, map the lines, and save it.
                  More mapped lines (receivables, SG&amp;A, reserves, long-term debt…) means more tests can run.
                </p>
              </div>
            )}
          </Card>
          {company && company.data.periods.length >= 2 && (
            <Card title="Market data (optional)" subtitle={company.data.items.share_price ? 'Taken from the imported file; type here to override' : 'Needed for the original Altman Z-score and the share-issue test'}>
              <div className="stack" style={{ gap: 8 }}>
                {company.data.periods.map((p) => (
                  <div key={p} className="grid cols-2" style={{ gap: 8 }}>
                    <NumberField label={`${p} share price`} value={market[p]?.price ?? null} onChange={(v) => setM(p, 'price', v)} min={0} />
                    <NumberField label="Shares outstanding" value={market[p]?.shares ?? null} onChange={(v) => setM(p, 'shares', v)} min={0}
                      hint="Same units as the statements (e.g. crores)" />
                  </div>
                ))}
              </div>
            </Card>
          )}
          <LearnBox title="How to read these screens">
            <div className="stack" style={{ fontSize: 13 }}>
              <p><b>Beneish M-score</b> combines eight ratios that moved unusually in companies later caught manipulating earnings. Higher is worse.</p>
              <p><b>Altman Z-score</b> predicts financial distress from liquidity, profitability, leverage and turnover. Higher is safer. Use <b>Z''</b> for IT, services and unlisted companies.</p>
              <p><b>Piotroski F-score</b> awards one point for each of nine signs of improving strength. 8–9 is strong, 0–2 is weak.</p>
              <p>None of these proves anything. They tell you <i>where to look</i> in the annual report.</p>
            </div>
          </LearnBox>
        </div>

        <div className="span-2 stack">
          {tooFew && <Callout tone="warn" title="Two or more periods needed">These screens compare years. Add at least two periods on the Financial Statements page.</Callout>}
          {res.error && <ErrorBox error={res.error} />}
          {!r && !res.error && !tooFew && <Skeleton h={120} />}
          {r && (
            <>
              <div className="grid cols-4">
                <ScoreKpi s={r.beneish} digits={2} />
                {r.altman.map((s) => <ScoreKpi key={s.key} s={s} digits={2} />)}
                <Kpi label={`Piotroski F-score (${r.current})`} value={r.piotroski.tested ? `${r.piotroski.score} / ${r.piotroski.tested}` : '—'}
                  hint={r.piotroski.tested < 9 ? `${9 - r.piotroski.tested} test(s) need more data` : 'All nine tests run'} />
              </div>

              <Card title="Warning signs" subtitle={`${r.flags.length} found across ${r.periods.length} periods`}>
                {r.flags.length === 0 ? <p className="muted">No cash-quality warning signs found in the data provided.</p> : (
                  <div className="stack" style={{ gap: 10 }}>
                    {r.flags.map((f, i) => (
                      <div key={i} className="row" style={{ alignItems: 'flex-start', gap: 10 }}>
                        <Badge tone={SEV_TONE[f.severity]}>{f.severity}</Badge>
                        <div><b>{f.title}</b>{f.period && <span className="faint"> · {f.period}</span>}<div style={{ fontSize: 13 }}>{f.detail}</div></div>
                      </div>
                    ))}
                  </div>
                )}
              </Card>

              {[r.beneish, ...r.altman].map((s) => <ScoreCard key={s.key} s={s} />)}

              <Card title={`Piotroski F-score · ${r.piotroski.period}`} subtitle={r.piotroski.verdict_text}>
                <div className="table-wrap" tabIndex={0}>
                  <table className="data">
                    <thead><tr><th>Test</th><th>Rule</th><th>Result</th><th>Detail</th></tr></thead>
                    <tbody>{r.piotroski.criteria.map((c) => (
                      <tr key={c.name}><td>{c.name}</td><td className="faint">{c.test}</td>
                        <td><Badge tone={c.result === 'pass' ? 'accent' : c.result === 'fail' ? 'neg' : 'warn'}>{c.result === 'missing' ? 'not tested' : c.result}</Badge></td>
                        <td className="mono" style={{ fontSize: 12, whiteSpace: 'normal' }}>{c.detail}</td></tr>
                    ))}</tbody>
                  </table>
                </div>
                {r.piotroski.notes.map((n) => <p key={n} className="faint mt-sm" style={{ fontSize: 12.5 }}>{n}</p>)}
              </Card>

              {r.derived.length > 0 && <Callout tone="info" title="Values worked out by the app">{r.derived.map((d) => <div key={d}>{d}</div>)}</Callout>}
              <Callout tone="warn" title="Important"><ShieldAlert size={14} style={{ verticalAlign: -2 }} /> {r.disclaimer}</Callout>
            </>
          )}
          {!company && sources && <EmptyState icon={<AlertTriangle size={22} />} title="Could not load that company">Choose another source.</EmptyState>}
        </div>
      </div>
    </div>
  );
}

function ScoreKpi({ s, digits }: { s: Score; digits: number }) {
  return (
    <Kpi label={`${s.name}`} value={s.status === 'ok' && isNum(s.value) ? fmtNum(s.value, digits) : '—'}
      delta={s.verdict ? <Badge tone={ZONE_TONE[s.verdict]}>{ZONE_LABEL[s.verdict]}</Badge> : <Badge tone="warn">Needs data</Badge>}
      hint={s.model !== '—' ? s.model : undefined} />
  );
}

function ScoreCard({ s }: { s: Score }) {
  return (
    <Card title={`${s.name} · ${s.period}`} subtitle={s.model !== '—' ? s.model : 'Not enough data'}
      actions={s.status === 'ok' && isNum(s.value) ? <b className="num" style={{ fontSize: 18 }}>{fmtNum(s.value, 2)}</b> : <Badge tone="warn">Missing inputs</Badge>}>
      <p style={{ fontSize: 13.5 }}>{s.verdict_text}</p>
      <Formula>{s.formula}</Formula>
      <p className="faint mt-sm" style={{ fontSize: 12.5 }}>{s.thresholds}</p>
      <div className="table-wrap mt-sm" tabIndex={0}>
        <table className="data">
          <thead><tr><th>Part</th><th className="r">Value</th><th>Inputs</th></tr></thead>
          <tbody>{s.components.map((c) => (
            <tr key={c.key + c.name}>
              <td style={{ whiteSpace: 'normal', minWidth: 220 }}><b>{c.key}</b> <span className="faint">{c.name}</span>
                <div className="mono faint" style={{ fontSize: 11.5 }}>{c.formula}</div></td>
              <td className="r">{isNum(c.value) ? fmtNum(c.value, 3) : <Badge tone="warn">missing</Badge>}</td>
              <td style={{ fontSize: 12, whiteSpace: 'normal', minWidth: 200 }}>
                {Object.entries(c.inputs).map(([k, v]) => <span key={k} className={isNum(v) ? '' : 'neg'}>{k}: {isNum(v) ? fmtNum(v, Math.abs(v) < 10 ? 3 : 0) : 'missing'}<br /></span>)}
                {c.note && <span className="faint">{c.note}</span>}
              </td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      {s.notes.map((n) => <p key={n} className="faint mt-sm" style={{ fontSize: 12.5 }}>{n}</p>)}
      <p className="faint mt-sm" style={{ fontSize: 12 }}><b>Limitations:</b> {s.limitations}</p>
    </Card>
  );
}
