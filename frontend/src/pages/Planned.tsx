import { Bot, ShieldCheck } from 'lucide-react';
import { Card, Badge, Callout, PageHeader, Skeleton, UnderDevelopment } from '../components/ui';
import { api } from '../lib/api';
import { useAsync } from '../lib/useApi';

export const Projects = () => (
  <UnderDevelopment title="My Projects" phase="Phase 7"
    summary="Projects group your files, assumptions, scenarios and reports under one name, with saved history."
    planned={['Create, rename and delete projects', 'Attach multiple uploads per project', 'Save DCF, scenario and budget models with version history',
      'Reopen previous analyses and reports', 'Per-account data isolation (authentication + PostgreSQL row-level security)',
      'Documented retention and deletion policy']}
    available={[{ to: '/upload', label: 'Upload & Analyse' }, { to: '/dcf', label: 'DCF (saved in this browser)' }]} />
);

export const CodeLab = () => (
  <UnderDevelopment title="Data & Code Lab" phase="Phase 5"
    summary="Explain, review and (only with your approval) run Python, SQL and Java in an isolated sandbox."
    planned={['Code editor with syntax highlighting, search, diff view', 'Python/SQL/Java explanations and debugging',
      'Sandboxed execution: container isolation, no network, CPU/memory/time limits, explicit approval before every run',
      'Corrected-file export']}
    available={[{ to: '/upload', label: 'Upload code for a syntax check & outline' }]} />
);

export const Reports = () => (
  <UnderDevelopment title="Reports & Exports" phase="Phase 6"
    summary="Executive summaries and analysis reports exported to Excel, PDF, Word and CSV with full traceability."
    planned={['Report builder for each analysis', 'Excel with live formulas, PDF and Word export', 'Methodology, assumptions, sources and limitations in every report']}
    available={[{ to: '/investment', label: 'CSV export: appraisal' }, { to: '/variance', label: 'CSV export: variance' }, { to: '/scenarios', label: 'CSV export: scenarios' }]} />
);

interface AIStatus { configured: boolean; provider: string; model: string | null; message: string; external: boolean }

export function Assistant() {
  const { data, loading } = useAsync(() => api.get<AIStatus>('/api/ai/status'), []);
  return (
    <div className="page">
      <PageHeader title="AI Finance Assistant" badge={<Badge tone="warn">Under development · Phase 6</Badge>}
        subtitle="Ask questions about your files and analyses. The assistant will call the same tested calculation functions — it never invents figures." />
      <div className="grid cols-2">
        <Card title="Provider status">
          {loading ? <Skeleton h={40} /> : data && (
            <Callout tone={data.configured ? 'success' : 'info'} title={data.configured ? `Connected: ${data.provider}` : 'No AI provider configured'}>
              {data.message}
            </Callout>
          )}
          <p className="muted mt">API keys stay on the server (backend/.env) and are never sent to the browser.</p>
        </Card>
        <Card title="Privacy rules this assistant will follow" actions={<ShieldCheck size={18} className="pos" />}>
          <ul style={{ margin: 0, paddingLeft: 18, display: 'grid', gap: 6 }}>
            <li>Files are sent to an external AI service only after you consent for that request.</li>
            <li>Numbers come from deterministic calculations with source references (sheet, cell, page).</li>
            <li>Explanations of variances are labelled as hypotheses unless supported by evidence.</li>
            <li>Educational analysis, not investment advice.</li>
          </ul>
        </Card>
        <Card title="Planned capabilities" className="span-all" actions={<Bot size={18} className="faint" />}>
          <div className="grid cols-3">
            {['Explain why expenses exceeded budget', 'Analyse an uploaded balance sheet', 'Run a DCF with my assumptions',
              'Explain a Python script line by line', 'Debug a SQL query', 'Summarise an uploaded PDF'].map((t) => (
              <div key={t} className="callout">{t}</div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
