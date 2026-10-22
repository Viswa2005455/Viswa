import { useState } from 'react';
import { Badge, Warnings } from './ui';

export interface Sheet {
  name: string; n_rows: number; n_cols: number; header_row: number | null;
  columns: { index: number; letter: string; name: string; dtype: string; missing: number; numeric: number; numbers_stored_as_text: number; number_format?: string }[];
  preview: { rows: (string | number | null)[][]; column_letters: string[] };
  formula_count: number; formula_samples: { cell: string; formula: string }[]; formulas_without_cached_value: number;
  formulas_calculated?: number; calculated_cells?: string[];
  duplicate_rows: number; warnings: string[]; source?: { page?: number; table?: number };
}

/** Table preview with spreadsheet-style row numbers and column letters for traceability. */
export function SheetPreview({ sheets, excel }: { sheets: Sheet[]; excel: boolean }) {
  const [idx, setIdx] = useState(0);
  const sheet = sheets[Math.min(idx, sheets.length - 1)];
  if (!sheet) return null;
  const calculated = new Set(sheet.calculated_cells ?? []);
  return (
    <div className="stack">
      {sheets.length > 1 && (
        <div className="row">
          <label className="field-label" htmlFor="sheet-select">{excel ? 'Worksheet' : 'Table'}</label>
          <select id="sheet-select" className="input compact" style={{ maxWidth: 320 }} value={idx} onChange={(e) => setIdx(Number(e.target.value))}>
            {sheets.map((s, i) => <option key={s.name + i} value={i}>{s.name} ({s.n_rows} rows)</option>)}
          </select>
        </div>
      )}
      <div className="row" style={{ fontSize: 12.5 }}>
        <Badge>{sheet.n_rows.toLocaleString()} rows × {sheet.n_cols} cols</Badge>
        {sheet.header_row && <Badge>Header row {sheet.header_row}</Badge>}
        {excel && <Badge tone={sheet.formula_count ? 'info' : undefined}>{sheet.formula_count} formulas</Badge>}
        {!!sheet.formulas_calculated && <Badge tone="warn">{sheet.formulas_calculated} calculated by the app</Badge>}
        {sheet.duplicate_rows > 0 && <Badge tone="warn">{sheet.duplicate_rows} duplicate rows</Badge>}
        {sheet.source?.page && <Badge>Source: page {sheet.source.page}</Badge>}
      </div>
      <Warnings items={sheet.warnings} />
      <div className="table-wrap" tabIndex={0} style={{ maxHeight: 380 }}>
        <table className="data">
          <thead>
            <tr><th className="rownum" />{sheet.preview.column_letters.map((l) => <th key={l}>{excel ? l : ''}</th>)}</tr>
          </thead>
          <tbody>
            {sheet.preview.rows.map((r, i) => (
              <tr key={i} style={sheet.header_row === i + 1 ? { fontWeight: 650 } : undefined}>
                <td className="rownum">{i + 1}</td>
                {sheet.preview.column_letters.map((l, c) => {
                  const v = r[c];
                  const calc = calculated.has(`${l}${i + 1}`);
                  const cls = [typeof v === 'number' ? 'r' : '', calc ? 'calculated' : ''].filter(Boolean).join(' ');
                  return (
                    <td key={c} className={cls || undefined}
                      title={calc ? 'Calculated by Finance Intelligence Studio: the file had no saved result for this formula. Verify in Excel.' : undefined}>
                      {v === null || v === undefined ? '' : String(v)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {calculated.size > 0 && <div className="faint" style={{ fontSize: 12 }}><span className="calculated-key" /> Highlighted cells were calculated by the app.</div>}
      {sheet.n_rows > sheet.preview.rows.length && <div className="faint" style={{ fontSize: 12 }}>Showing the first {sheet.preview.rows.length} rows.</div>}
      <details className="disclosure">
        <summary>Column profile</summary>
        <div className="body table-wrap">
          <table className="data">
            <thead><tr><th>Col</th><th>Name</th><th>Type</th><th className="r">Numeric</th><th className="r">Missing</th><th className="r">Text→number</th><th>Format</th></tr></thead>
            <tbody>
              {sheet.columns.map((c) => (
                <tr key={c.index}><td>{c.letter}</td><td>{c.name}</td><td>{c.dtype}</td><td className="r">{c.numeric}</td>
                  <td className="r">{c.missing}</td><td className="r">{c.numbers_stored_as_text || ''}</td><td className="mono">{c.number_format ?? ''}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
      {sheet.formula_samples.length > 0 && (
        <details className="disclosure">
          <summary>Formulas found ({sheet.formula_count})</summary>
          <div className="body">
            {sheet.formula_samples.map((f) => <div key={f.cell} className="mono" style={{ fontSize: 12.5 }}><b>{f.cell}</b> {f.formula}</div>)}
          </div>
        </details>
      )}
    </div>
  );
}
