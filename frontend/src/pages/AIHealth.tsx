import { Activity, KeyRound, PlugZap, RefreshCw } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Badge, Callout, Card, ErrorBox, PageHeader, Skeleton } from '../components/ui';
import { api } from '../lib/api';
import { useAsync } from '../lib/useApi';

interface Health {
  state: 'untested' | 'ok' | 'failed'; kind?: string | null; checked_at?: string | null; latency_ms?: number | null; served_model?: string | null;
  error_category?: string | null; error_message?: string | null; last_success_at?: string | null; successes?: number; failures?: number;
}
interface ModelRow { id: string; label: string; note: string; default: boolean; refusal_fallback: boolean; prices_usd_per_mtok: Record<string, number>; health: Health }
interface HealthRes {
  configured: boolean; provider: string; model: string | null; message: string; external: boolean; credentials_present: boolean;
  timeout_seconds: number | null; max_retries: number | null; models: ModelRow[]; providers_supported: string[]; prices_checked_on: string; note: string;
}
interface MarketStatus { configured: boolean; provider: string | null; label: string | null; demo: boolean }

const fmtTime = (s?: string | null) => (s ? new Date(s).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'medium' }) : '—');
const KIND: Record<string, string> = { access: 'Access check', reply: 'Test reply', chat: 'Assistant question' };

function StateBadge({ h }: { h: Health }) {
  if (h.state === 'ok') return <Badge tone="pos">Working</Badge>;
  if (h.state === 'failed') return <Badge tone="neg">Failed</Badge>;
  return <Badge>Not tested yet</Badge>;
}

export function AIHealth() {
  const res = useAsync((signal) => api.get<HealthRes>('/api/ai/health', { signal }), []);
  const market = useAsync((signal) => api.get<MarketStatus>('/api/market/status', { signal }), []);
  const [pending, setPending] = useState<{ model: string; kind: 'access' | 'reply' } | null>(null);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const run = async () => {
    if (!pending) return;
    setRunning(true); setErr(null);
    try {
      await api.post('/api/ai/health/check', { ...pending, confirm: true }, { timeoutMs: 45_000 });
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setRunning(false); setPending(null); res.reload();
    }
  };

  const d = res.data;
  const providerState = !d ? null : d.provider === 'none' ? 'Not configured' : !d.credentials_present ? 'Configured, but no API key' : d.configured ? 'Configured' : 'Configuration problem';

  return (
    <div className="page">
      <PageHeader title="AI Model Health" badge={<Badge tone="info">Live checks only when you ask</Badge>}
        subtitle="Which AI provider and models this server can use, whether credentials are present, and the result, speed and time of the last real check or question. Nothing on this page contacts a provider until you press a button and confirm."
        actions={<button className="btn" onClick={() => res.reload()} disabled={res.loading}><RefreshCw size={15} />Refresh</button>} />
      <Callout tone="info" title="Not the Excel Model Checker">
        This page checks AI models. To check a spreadsheet model for errors, use the <Link to="/model-check">Excel Model Checker</Link>.
      </Callout>

      {res.error ? <div className="mt"><ErrorBox error={res.error} /></div> : !d ? <div className="mt"><Skeleton h={200} /></div> : (
        <>
          <div className="grid cols-4 mt">
            <Card title="Provider"><div className="kpi-value" style={{ fontSize: 18 }}>{d.provider === 'none' ? 'None' : 'Anthropic (Claude)'}</div><div className="faint" style={{ fontSize: 12 }}>{providerState}</div></Card>
            <Card title="API key on the server" actions={<KeyRound size={16} />}><div className="kpi-value" style={{ fontSize: 18 }}>{d.provider === 'none' ? '—' : d.credentials_present ? 'Present' : 'Missing'}</div><div className="faint" style={{ fontSize: 12 }}>The key itself is never shown or sent to the browser.</div></Card>
            <Card title="Default model"><div className="kpi-value" style={{ fontSize: 18 }}>{d.model ?? '—'}</div></Card>
            <Card title="Limits"><div style={{ fontSize: 13 }}>{d.timeout_seconds != null ? <>Timeout {d.timeout_seconds} s per attempt<br />Retries {d.max_retries} (rate limits, server errors, network)</> : '—'}</div></Card>
          </div>
          {!d.configured && <div className="mt"><Callout tone="warn" title="AI is not available">{d.message}</Callout></div>}

          <Card title="Models" subtitle={`Prices are list prices in US dollars per million tokens, checked ${d.prices_checked_on}.`} className="mt">
            {d.models.length === 0 ? <p className="faint" style={{ margin: 0 }}>No models are listed because no AI provider is configured on this server.</p> : (
            <div className="table-wrap" tabIndex={0}>
              <table className="data">
                <thead><tr><th>Model</th><th>Status</th><th>Last check</th><th className="r">Latency</th><th>Answered by</th><th>Last success</th><th className="r">OK / failed</th><th className="r">Price in / out</th><th>Check</th></tr></thead>
                <tbody>{d.models.map((m) => (
                  <tr key={m.id}>
                    <td style={{ whiteSpace: 'normal' }}><b>{m.label}</b>{m.default && <> <Badge tone="accent">default</Badge></>}<div className="faint" style={{ fontSize: 11.5 }}>{m.id}{m.refusal_fallback ? ' · refusal fallback on' : ' · no refusal fallback'}</div></td>
                    <td><StateBadge h={m.health} />{m.health.error_category && <div className="neg" style={{ fontSize: 11.5 }}>{m.health.error_category}: {m.health.error_message}</div>}</td>
                    <td>{m.health.checked_at ? <>{fmtTime(m.health.checked_at)}<div className="faint" style={{ fontSize: 11.5 }}>{KIND[m.health.kind ?? ''] ?? m.health.kind} · live</div></> : '—'}</td>
                    <td className="r">{m.health.latency_ms != null ? `${(m.health.latency_ms / 1000).toFixed(2)} s` : '—'}</td>
                    <td>{m.health.served_model ?? '—'}{m.health.served_model && m.health.served_model !== m.id && <div className="warn-text" style={{ fontSize: 11.5 }}>differs from the model chosen</div>}</td>
                    <td>{fmtTime(m.health.last_success_at)}</td>
                    <td className="r">{m.health.successes ?? 0} / {m.health.failures ?? 0}</td>
                    <td className="r">${m.prices_usd_per_mtok.input} / ${m.prices_usd_per_mtok.output}</td>
                    <td><div className="row" style={{ gap: 6, flexWrap: 'nowrap' }}>
                      <button className="btn sm" disabled={!d.credentials_present || running} onClick={() => setPending({ model: m.id, kind: 'access' })}><PlugZap size={13} />Access</button>
                      <button className="btn sm" disabled={!d.credentials_present || running} onClick={() => setPending({ model: m.id, kind: 'reply' })}><Activity size={13} />Test reply</button>
                    </div></td>
                  </tr>))}
                </tbody>
              </table>
            </div>)}
            <p className="faint mt-sm" style={{ fontSize: 12 }}>{d.note} "Access" looks the model up with your key (no tokens used). "Test reply" sends one short message and uses a few tokens. Checks are limited to 20 an hour.</p>
            {pending && (
              <div className="mt"><Callout tone="warn" title={`Run a ${pending.kind === 'reply' ? 'test reply' : 'access check'} on ${pending.model}?`}>
                This contacts Anthropic from the server{pending.kind === 'reply' ? ' and costs a few tokens (well under one US cent)' : ''}. No personal or company data is sent.
                <div className="row mt-sm"><button className="btn primary" onClick={run} disabled={running}>{running ? 'Checking…' : 'Yes, run the check'}</button><button className="btn" onClick={() => setPending(null)} disabled={running}>Cancel</button></div>
              </Callout></div>
            )}
            {err && <div className="mt-sm"><ErrorBox error={err} /></div>}
          </Card>

          <Card title="Market data provider" subtitle="Used by Markets & Risk for share prices" className="mt">
            {market.error ? <ErrorBox error={market.error} /> : !market.data ? <Skeleton h={40} /> : (
              <p style={{ margin: 0 }}>{market.data.configured ? <>{market.data.label} is configured{market.data.demo ? ' with its public demo key (a few symbols only)' : ''}. Each quote shows the provider's own time stamp and delay note; it is not tested from this page.</> : 'No market data provider is configured. Live prices are unavailable; you can still upload a price file on Markets & Risk.'}</p>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
