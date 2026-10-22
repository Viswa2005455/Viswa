import { Activity, Bot, Calculator, Lock, RotateCcw, Send, ShieldCheck, Square, User } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { SafeMarkdown } from '../components/SafeMarkdown';
import { Badge, Callout, Card, ErrorBox, Field, PageHeader, Skeleton } from '../components/ui';
import { api, isAbort } from '../lib/api';
import { toCompany, useCompanySources, type StatementData } from '../lib/company';
import { useDCFModel } from '../lib/dcfModel';
import { loadRaw, save } from '../lib/storage';
import type { UploadSummary } from '../lib/types';
import { useAsync } from '../lib/useApi';

interface ModelInfo { id: string; label: string; note: string; default: boolean; refusal_fallback: boolean }
interface AIStatus { configured: boolean; provider: string; model: string | null; message: string; external: boolean; models?: ModelInfo[] }
interface ToolRun { name: string; ok: boolean; input?: unknown; output?: unknown; error?: string }
type Mode = 'ask' | 'red_flags' | 'model_check' | 'challenge' | 'peers' | 'research' | 'report';
interface Msg { role: 'user' | 'assistant'; content: string; tools?: ToolRun[]; cost?: number | null; model?: string; requested?: string; notice?: string | null; latency?: number; at?: string }
interface Reply { reply: string; stop_reason: string; model: string; requested_model: string; model_notice: string | null; fallbacks: { from: string; to: string }[];
  tools_used: ToolRun[]; usage: { input_tokens: number; output_tokens: number; estimated_cost_usd: number | null }; latency_ms: number; answered_at: string }

const MODES: { value: Mode; label: string; hint: string; prompts: string[] }[] = [
  { value: 'ask', label: 'Analyse my data', hint: 'Questions on statements, models and files', prompts: ['Summarise the trend in margins and returns, with the drivers.', 'What explains the change in ROE over the period (DuPont)?', 'Assess working-capital efficiency and cash conversion.'] },
  { value: 'red_flags', label: 'Earnings quality review', hint: 'Interpret the Beneish, Altman and Piotroski results', prompts: ['Interpret the red-flag results and rank the follow-ups by priority.', 'Which notes to the accounts should I review first, and what would resolve each flag?'] },
  { value: 'model_check', label: 'Model review', hint: 'Review notes on the Excel model checker findings', prompts: ['Write review notes for the high-severity issues with suggested fixes.', 'Propose formula rewrites for the hard-coded inputs.'] },
  { value: 'challenge', label: 'Challenge the valuation', hint: 'Stress the DCF assumptions against history', prompts: ['Challenge the DCF assumptions against the historical data.', 'What growth and margin does the market price imply, and is it supportable?'] },
  { value: 'peers', label: 'Peer benchmarking', hint: 'Relative performance and comparability', prompts: ['Benchmark the companies and explain the key differences.', 'Which differences may reflect accounting policy rather than performance?'] },
  { value: 'research', label: 'Technical research', hint: 'US GAAP / IFRS / Ind AS treatment with schedules', prompts: ['How should a lessee account for a 5-year lease with annual payments of 10,000 in advance at 6%? Show the schedule and entries under ASC 842 and IFRS 16.', 'Compute basic and diluted EPS: net income 1,000,000; preferred dividends 100,000; 500,000 weighted shares; 50,000 options at 20 with an average price of 25.', 'Explain the deferred tax on a PPE carrying amount of 100,000 with a tax base of 70,000 at 25%.'] },
  { value: 'report', label: 'Analysis memo', hint: 'Structured draft for review and editing', prompts: ['Draft a company-analysis memo from the attached data.'] },
];
const TOOL_LABEL: Record<string, string> = { ratio_analysis: 'Ratio engine', red_flag_scan: 'Red-flag scan', peer_compare: 'Peer comparison', dcf_value: 'DCF', reverse_dcf: 'Reverse DCF', npv_irr: 'NPV / IRR', cost_of_capital: 'CAPM / WACC',
  lease_schedule: 'Lease schedule', bond_amortisation: 'Bond amortisation', eps: 'EPS', deferred_tax: 'Deferred tax', materiality: 'Materiality', cvp: 'CVP', bond_analytics: 'Bond analytics', option_pricing: 'Option pricing' };
const TOPIC_MODE: Record<string, Mode> = { 'red-flags': 'red_flags', 'model-check': 'model_check', peers: 'peers', dcf: 'challenge' };

export function Assistant() {
  const [params] = useSearchParams();
  const status = useAsync((signal) => api.get<AIStatus>('/api/ai/status', { signal }), []);
  const { model: dcf, isExample: dcfExample } = useDCFModel();
  const { sources } = useCompanySources();
  const uploads = useAsync((signal) => api.get<{ uploads: UploadSummary[] }>('/api/uploads', { signal }), []);
  const excel = (uploads.data?.uploads ?? []).filter((u) => /\.(xlsx|xlsm)$/i.test(u.name) && u.status === 'processed');
  const topic = params.get('topic') ?? '';

  const [mode, setMode] = useState<Mode>(TOPIC_MODE[topic] ?? 'ask');
  const [useDcf, setUseDcf] = useState(topic === 'dcf');
  const [stmtId, setStmtId] = useState<string>(topic === 'red-flags' ? loadRaw('fis.redflags.source', '') || 'first' : '');
  const [checkId, setCheckId] = useState<string>(params.get('upload') ?? '');
  const [usePeers, setUsePeers] = useState(topic === 'peers');
  const [consent, setConsent] = useState(false);
  const [input, setInput] = useState('');
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chosen, setChosen] = useState<string>(() => loadRaw('fis.ai.model', ''));
  const ctl = useRef<AbortController | null>(null);
  const models = status.data?.models ?? [];
  const model = models.find((m) => m.id === chosen) ?? models.find((m) => m.default) ?? models[0];
  const pickModel = (id: string) => { setChosen(id); save('fis.ai.model', id); };
  const endRef = useRef<HTMLDivElement>(null);
  const peerPicks = loadRaw<{ id: string; name: string }[]>('fis.peers.picked', []);
  const stmtSource = sources?.find((s) => s.id === stmtId) ?? (stmtId === 'first' ? sources?.find((s) => !s.isExample) ?? sources?.[0] : undefined);

  useEffect(() => { endRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' }); }, [msgs, busy]);

  const shared = useMemo(() => {
    const list: string[] = [];
    if (useDcf) list.push(`DCF assumptions${dcfExample ? ' (example)' : ''}`);
    if (stmtSource) list.push(`Statements: ${stmtSource.name}`);
    if (checkId) list.push(`Model-check results: ${excel.find((u) => u.id === checkId)?.name ?? 'workbook'}`);
    if (usePeers) list.push(`Peer companies: ${peerPicks.map((p) => p.name).join(', ') || 'none selected'}`);
    return list;
  }, [useDcf, dcfExample, stmtSource, checkId, usePeers, excel, peerPicks]);

  const buildAttachments = async () => {
    const atts: { title: string; kind: string; data: unknown }[] = [];
    if (useDcf) atts.push({ title: dcfExample ? 'DCF assumptions (example values, not real data)' : 'DCF assumptions', kind: 'dcf_model', data: dcf });
    if (stmtSource) {
      const d: StatementData = await stmtSource.load();
      atts.push({ title: `Financial statements — ${stmtSource.name}`, kind: 'statements', data: {
        periods: d.periods, lines: d.lines.map((l) => ({ label: l.label, key: l.key, values: l.values, source: l.source ?? null })),
        engine_items: toCompany(d).items } });
    }
    if (checkId) {
      const r = await api.post<{ name: string; counts: Record<string, number>; issues: unknown[] }>(`/api/analysis/model-check/${checkId}`, {});
      atts.push({ title: `Excel model check — ${r.name}`, kind: 'model_check', data: { counts: r.counts, issues: r.issues.slice(0, 120) } });
    }
    if (usePeers && sources) {
      const companies = [];
      for (const p of peerPicks) {
        const src = sources.find((s) => s.id === p.id);
        if (src) { const d = await src.load(); companies.push({ name: p.name, ...toCompany(d) }); }
      }
      if (companies.length) atts.push({ title: 'Peer companies', kind: 'peer_companies', data: companies });
    }
    return atts;
  };

  const send = async (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    if (!consent) { setError('Tick the box to agree to send your question and the listed data to Claude.'); return; }
    setError(null);
    const history: Msg[] = [...msgs, { role: 'user', content: q }];
    setMsgs(history);
    setInput('');
    setBusy(true);
    const c = new AbortController();
    ctl.current = c;
    try {
      const attachments = await buildAttachments();
      const r = await api.post<Reply>('/api/ai/chat', {
        mode, consent: true, attachments, model: model?.id, messages: history.map((m) => ({ role: m.role, content: m.content })),
      }, { signal: c.signal, timeoutMs: 330_000 });
      setMsgs([...history, { role: 'assistant', content: r.reply, tools: r.tools_used, cost: r.usage.estimated_cost_usd, model: r.model,
        requested: r.requested_model, notice: r.model_notice, latency: r.latency_ms, at: r.answered_at }]);
    } catch (e) {
      setError(isAbort(e) ? 'Cancelled. Nothing was answered; you can edit the question and send it again.' : (e as Error).message);
      setMsgs(msgs);
      setInput(q);
    } finally {
      ctl.current = null;
      setBusy(false);
      setConsent(false); // consent is given per request
    }
  };

  const total = msgs.reduce((a, m) => a + (m.cost ?? 0), 0);
  const configured = status.data?.configured;
  const modeInfo = MODES.find((m) => m.value === mode)!;

  return (
    <div className="page">
      <PageHeader title="AI Finance Assistant" badge={configured ? <Badge tone="accent">{model?.label ?? status.data?.model}</Badge> : <Badge tone="warn">Not set up</Badge>}
        subtitle="An analyst that works from your data and the app's tested calculators: every figure is computed by the engine and cited to its source, and accounting answers name the applicable standard."
        actions={<>
          <Link className="btn" to="/ai-health"><Activity size={15} />AI model health</Link>
          {msgs.length > 0 && <button className="btn" onClick={() => { setMsgs([]); setError(null); }}><RotateCcw size={15} />New conversation</button>}
        </>} />

      {status.loading ? <Skeleton h={60} /> : !configured && (
        <Callout tone="info" title="Set up the AI assistant (one time)">
          <ol style={{ margin: '6px 0 0', paddingLeft: 20, display: 'grid', gap: 4 }}>
            <li>Create an API key at <b>console.anthropic.com</b> → API keys, and add a small prepaid balance under Billing.</li>
            <li>Open the file <code>backend\.env</code> in the app folder (copy <code>.env.example</code> to <code>backend\.env</code> if it does not exist).</li>
            <li>Set <code>FIS_AI_PROVIDER=anthropic</code> and <code>ANTHROPIC_API_KEY=</code> followed by your key. Keep <code>FIS_AI_MODEL=claude-opus-5-5</code>.</li>
            <li>Close the BACKEND window and run <code>start-windows.bat</code> again.</li>
          </ol>
          <div className="mt-sm faint" style={{ fontSize: 12.5 }}>The key stays on your computer's backend and is never sent to the browser. Everything else in the app works without it. {status.data?.message}</div>
        </Callout>
      )}

      <div className="grid cols-3 mt">
        <div className="stack">
          {configured && models.length > 0 && (
            <Card title="Model">
              <Field label="AI model" hint={model ? `${model.note}${model.refusal_fallback ? ' If it declines a request, the provider may hand it to a fallback model; you will be told.' : ''}` : undefined}>
                <select className="input" value={model?.id ?? ''} onChange={(e) => pickModel(e.target.value)} disabled={busy}>
                  {models.map((m) => <option key={m.id} value={m.id}>{m.label}{m.default ? ' (default)' : ''}</option>)}
                </select>
              </Field>
            </Card>
          )}
          <Card title="What should the assistant do?">
            <div className="stack" style={{ gap: 6 }}>
              {MODES.map((m) => (
                <button key={m.value} className={`btn mode-btn ${mode === m.value ? 'primary' : ''}`} aria-pressed={mode === m.value} onClick={() => setMode(m.value)}>
                  <span><b>{m.label}</b><br /><span style={{ fontSize: 12 }}>{m.hint}</span></span>
                </button>
              ))}
            </div>
          </Card>
          <Card title="Data to share" subtitle="Only what you tick is sent with your question">
            <div className="stack" style={{ gap: 10, fontSize: 13.5 }}>
              <label className="row"><input type="checkbox" checked={useDcf} onChange={(e) => setUseDcf(e.target.checked)} />DCF assumptions{dcfExample && <Badge tone="sample">example</Badge>}</label>
              <Field label="Company statements">
                <select className="input" value={stmtSource?.id ?? ''} onChange={(e) => setStmtId(e.target.value)}>
                  <option value="">None</option>
                  {(sources ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </Field>
              <Field label="Excel model-check results">
                <select className="input" value={checkId} onChange={(e) => setCheckId(e.target.value)}>
                  <option value="">None</option>
                  {excel.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
                </select>
              </Field>
              <label className="row" style={{ alignItems: 'flex-start', flexWrap: 'nowrap' }}><input type="checkbox" checked={usePeers} onChange={(e) => setUsePeers(e.target.checked)} disabled={!peerPicks.length} />
                <span>Peer companies {peerPicks.length ? `(${peerPicks.length} from Peer Comparison)` : <span className="faint">— pick them on <Link to="/peers">Peer Comparison</Link></span>}</span></label>
            </div>
          </Card>
          <Card title="Privacy" actions={<ShieldCheck size={18} className="pos" />}>
            <ul style={{ margin: 0, paddingLeft: 18, display: 'grid', gap: 6, fontSize: 13 }}>
              <li>Your question and the ticked data are sent to Anthropic (Claude) only when you tick the consent box, for that one question.</li>
              <li>Numbers come from the app's calculators. Their exact results are shown under each answer, separately from the AI's explanation.</li>
              <li>Answers can still contain mistakes. Check important figures against the source.</li>
              <li>Conclusions on accounting treatment must be confirmed against the authoritative literature and the entity's facts.</li>
            </ul>
          </Card>
        </div>

        <div className="span-2 stack assistant-chat">
          <Card title={modeInfo.label} subtitle={modeInfo.hint} className="chat-card">
            <div className="chat" aria-live="polite">
              {msgs.length === 0 && (
                <div className="stack" style={{ gap: 8 }}>
                  <p className="muted" style={{ fontSize: 13.5 }}>Try one of these:</p>
                  {modeInfo.prompts.map((p) => <button key={p} className="btn sm" style={{ justifyContent: 'flex-start' }} onClick={() => setInput(p)}>{p}</button>)}
                </div>
              )}
              {msgs.map((m, i) => (
                <div key={i} className={`chat-msg ${m.role}`}>
                  <div className="chat-avatar">{m.role === 'user' ? <User size={15} /> : <Bot size={15} />}</div>
                  <div className="chat-bubble">
                    {m.notice && <div className="mb-sm"><Callout tone="warn">{m.notice}</Callout></div>}
                    {m.role === 'assistant' ? <SafeMarkdown text={m.content} /> : <p style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{m.content}</p>}
                    {m.role === 'assistant' && m.tools && m.tools.length > 0 && <ToolResults tools={m.tools} />}
                    {m.role === 'assistant' && (
                      <div className="row faint" style={{ fontSize: 11.5, marginTop: 8, gap: 6 }}>
                        <span>AI explanation by {m.model}{m.requested && m.requested !== m.model ? ` (you chose ${m.requested})` : ''}</span>
                        {typeof m.latency === 'number' && <span>· {(m.latency / 1000).toFixed(1)} s</span>}
                        {typeof m.cost === 'number' && <span>· estimated cost ${m.cost.toFixed(4)}</span>}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {busy && <div className="chat-msg assistant"><div className="chat-avatar"><Bot size={15} /></div><div className="chat-bubble"><Skeleton h={14} w={220} /><div className="faint mt-sm" style={{ fontSize: 12 }}>Thinking and running calculations…</div></div></div>}
              <div ref={endRef} />
            </div>
            {error && <div className="mt-sm"><ErrorBox error={error} /></div>}
            <div className="stack mt" style={{ gap: 8 }}>
              <textarea className="input" rows={3} placeholder={configured ? 'Ask a question…' : 'Set up the assistant first (see the steps above).'} value={input}
                onChange={(e) => setInput(e.target.value)} disabled={!configured || busy} maxLength={4000}
                onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) send(input); }} aria-label="Your question" />
              <label className="row" style={{ fontSize: 12.5, alignItems: 'flex-start' }}>
                <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} disabled={!configured} />
                <span><Lock size={12} style={{ verticalAlign: -1 }} /> Send my question{shared.length ? ' and this data' : ''} to Anthropic (Claude) to answer it{shared.length ? `: ${shared.join('; ')}` : ' (no data is attached)'}.</span>
              </label>
              <div className="row between">
                <span className="faint" style={{ fontSize: 12 }}>{total > 0 ? `This conversation: estimated $${total.toFixed(4)} (list prices, US dollars)` : 'Ctrl + Enter to send'}</span>
                {busy
                  ? <button className="btn" onClick={() => ctl.current?.abort()}><Square size={14} />Cancel</button>
                  : <button className="btn primary" onClick={() => send(input)} disabled={!configured || !input.trim()}><Send size={15} />Send</button>}
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

/** Deterministic results from the app's engine, shown apart from the AI's wording so figures can be checked. */
function ToolResults({ tools }: { tools: ToolRun[] }) {
  return (
    <details className="tool-results mt-sm">
      <summary><Calculator size={12} style={{ verticalAlign: -1 }} /> Calculated by the app's engine (not by the AI): {[...new Set(tools.map((t) => TOOL_LABEL[t.name] ?? t.name))].join(', ')}</summary>
      {tools.map((t, i) => (
        <div key={i} className="mt-sm">
          <div style={{ fontSize: 12, fontWeight: 600 }}>{TOOL_LABEL[t.name] ?? t.name} {t.ok ? <Badge tone="pos">ok</Badge> : <Badge tone="neg">input error</Badge>}</div>
          {t.ok ? <pre className="code-block">{JSON.stringify(t.output, null, 2)}</pre> : <div className="neg" style={{ fontSize: 12 }}>{t.error}</div>}
          {t.input != null && <details><summary className="faint" style={{ fontSize: 11.5 }}>Inputs used</summary><pre className="code-block">{JSON.stringify(t.input, null, 2)}</pre></details>}
        </div>
      ))}
    </details>
  );
}
