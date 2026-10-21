import { Bot, FileSearch, Play } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Badge, Callout, Card, EmptyState, ErrorBox, Kpi, LearnBox, PageHeader, Skeleton, Tabs } from '../components/ui';
import { api } from '../lib/api';
import { downloadFile, toCSV } from '../lib/format';
import type { UploadSummary } from '../lib/types';
import { useAsync } from '../lib/useApi';

interface Issue { category: string; severity: 'high' | 'medium' | 'low'; sheet: string; cell: string | null; message: string; suggestion: string; formula: string | null }
interface Report {
  upload_id: string; name: string; formulas_checked: number; sheets: { name: string; state: string; formulas: number; cells: number }[];
  counts: Record<string, number>; by_severity: Record<'high' | 'medium' | 'low', number>; issues: Issue[]; truncated_issues: number; notes: string[];
}

export const CATEGORY_LABEL: Record<string, string> = {
  error_value: 'Error values', broken_reference: 'Broken references (#REF!)', external_link: 'Links to other files',
  missing_sheet: 'References to missing sheets', circular_reference: 'Circular references', value_in_formula_range: 'Number typed over a formula',
  balance_check: 'Balance sheet does not balance', inconsistent_formula: 'Inconsistent formulas', hardcoded_number: 'Numbers typed inside formulas',
  hidden_sheet: 'Hidden sheets', truncated: 'Partly checked',
};
const SEV_TONE = { high: 'neg', medium: 'warn', low: 'info' } as const;
type Filter = 'all' | 'high' | 'medium' | 'low';

export function ModelCheck() {
  const uploads = useAsync(() => api.get<{ uploads: UploadSummary[] }>('/api/uploads'), []);
  const excel = (uploads.data?.uploads ?? []).filter((u) => /\.(xlsx|xlsm)$/i.test(u.name) && u.status === 'processed');
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>('all');

  const run = async (id: string) => {
    setBusy(id);
    setError(null);
    try {
      setReport(await api.post<Report>(`/api/analysis/model-check/${id}`, {}));
      setFilter('all');
    } catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  };
  const shown = useMemo(() => (report?.issues ?? []).filter((i) => filter === 'all' || i.severity === filter), [report, filter]);

  const exportCsv = () => {
    if (!report) return;
    downloadFile(`model-check-${report.name}.csv`, toCSV([['Excel model check', report.name], [],
      ['Severity', 'Check', 'Sheet', 'Cell', 'Problem', 'Suggestion', 'Formula'],
      ...report.issues.map((i) => [i.severity, CATEGORY_LABEL[i.category] ?? i.category, i.sheet, i.cell ?? '', i.message, i.suggestion, i.formula ?? '']),
      [], ['Generated', new Date().toISOString()]]));
  };

  return (
    <div className="page">
      <PageHeader title="Excel Model Checker"
        subtitle="Finds common modelling mistakes in your own Excel models: error values, broken links, circular references, numbers typed inside formulas, inconsistent formulas and balance sheets that do not balance."
        actions={report && <>
          <Link className="btn" to={`/assistant?topic=model-check&upload=${report.upload_id}`}><Bot size={15} />Explain with AI</Link>
          <button className="btn" onClick={exportCsv}>Export CSV</button>
        </>} />

      <div className="grid cols-3 mt">
        <div className="stack">
          <Card title="Choose a workbook" subtitle="Excel .xlsx or .xlsm files you have uploaded">
            {uploads.loading ? <Skeleton h={40} /> : uploads.error ? <ErrorBox error={uploads.error} /> : excel.length === 0 ? (
              <p className="muted">No Excel files yet. <Link to="/upload">Upload a model</Link>, then come back.</p>
            ) : (
              <div className="stack" style={{ gap: 8 }}>
                {excel.map((u) => (
                  <button key={u.id} className={`btn ${report?.upload_id === u.id ? 'primary' : ''}`} style={{ justifyContent: 'flex-start' }}
                    onClick={() => run(u.id)} disabled={!!busy}>
                    <Play size={14} />{busy === u.id ? 'Checking…' : u.name}
                  </button>
                ))}
              </div>
            )}
          </Card>
          <LearnBox title="Why these checks matter">
            <div className="stack" style={{ fontSize: 13 }}>
              <p><b>Numbers inside formulas</b> (=B5*1.18) hide assumptions. Put each assumption in its own labelled cell.</p>
              <p><b>Inconsistent formulas</b> usually mean a copy-across mistake: one year was edited and the others were not.</p>
              <p><b>A typed number in a formula row</b> often means someone pasted a value over a formula, so it no longer updates.</p>
              <p><b>Circular references</b> make results depend on calculation order. Use opening balances for interest instead.</p>
            </div>
          </LearnBox>
        </div>

        <div className="span-2 stack">
          {error && <ErrorBox error={error} />}
          {!report && !error && <EmptyState icon={<FileSearch size={22} />} title="Pick a workbook to check">Results appear here. Nothing in the file is run; formulas are read as text.</EmptyState>}
          {report && (
            <>
              <div className="grid cols-4">
                <Kpi label="Formulas checked" value={report.formulas_checked.toLocaleString()} hint={`${report.sheets.length} sheet(s)`} />
                <Kpi label="High" value={String(report.by_severity.high)} hint="Errors, broken links, circularity" />
                <Kpi label="Medium" value={String(report.by_severity.medium)} hint="Inconsistent formulas" />
                <Kpi label="Low" value={String(report.by_severity.low)} hint="Typed numbers, hidden sheets" />
              </div>
              {report.issues.length === 0 ? (
                <Callout tone="success" title="No issues found">None of the checks found a problem. This does not prove the model's logic is right, so still review the key assumptions.</Callout>
              ) : (
                <Card title={`Issues in ${report.name}`} subtitle={Object.entries(report.counts).map(([k, n]) => `${CATEGORY_LABEL[k] ?? k}: ${n}`).join(' · ')}
                  actions={<Tabs label="Severity" value={filter} onChange={setFilter} options={[{ value: 'all', label: 'All' }, { value: 'high', label: 'High' }, { value: 'medium', label: 'Medium' }, { value: 'low', label: 'Low' }]} />}>
                  <div className="table-wrap" style={{ maxHeight: 560 }}>
                    <table className="data">
                      <thead><tr><th>Severity</th><th>Where</th><th>Problem</th><th>What to do</th></tr></thead>
                      <tbody>{shown.map((i, n) => (
                        <tr key={n}>
                          <td><Badge tone={SEV_TONE[i.severity]}>{i.severity}</Badge></td>
                          <td className="mono" style={{ fontSize: 12 }}>{i.sheet}{i.cell ? `!${i.cell}` : ''}</td>
                          <td style={{ whiteSpace: 'normal', minWidth: 240, fontSize: 13 }}>
                            <b>{CATEGORY_LABEL[i.category] ?? i.category}</b><div>{i.message}</div>
                            {i.formula && <div className="mono faint" style={{ fontSize: 11.5 }}>{i.formula}</div>}
                          </td>
                          <td className="faint" style={{ whiteSpace: 'normal', minWidth: 200, fontSize: 12.5 }}>{i.suggestion}</td>
                        </tr>
                      ))}</tbody>
                    </table>
                  </div>
                  {report.truncated_issues > 0 && <p className="faint mt-sm" style={{ fontSize: 12.5 }}>{report.truncated_issues} more issues not shown.</p>}
                </Card>
              )}
              <Callout tone="info">{report.notes.map((n) => <div key={n}>{n}</div>)}</Callout>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
