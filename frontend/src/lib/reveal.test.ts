import { describe, expect, it } from 'vitest';
import { accepted, inputFromUpload, isExactMatch, mapRows, ratioData, type Mapping, type SuggestedStatement } from './reveal';

const mapping: Mapping[] = [
  { item: 'revenue', item_label: 'Revenue', source_label: 'Revenue', value: 12480, source: 'pl.xlsx › P&L › C2', period: 'FY2025', prior_value: 11000, prior_source: 'pl.xlsx › P&L › B2', prior_period: 'FY2024' },
  { item: 'receivables', item_label: 'Accounts receivable', source_label: 'Trade receivables', value: 1720, source: 'pl.xlsx › BS › C2', period: 'FY2025', prior_value: 1500, prior_source: null, prior_period: null },
];
const statements: SuggestedStatement[] = [{ sheet: 'P&L', statement: 'income', periods: ['FY2024', 'FY2025'], reordered: false, lines: [
  { label: 'Revenue', key: 'revenue', values: [11000, 12480], source: 'pl.xlsx › P&L › B2–C2' },
  { label: 'Trade receivables', key: 'receivables', values: [1500, 1720], source: null },
] }];

describe('upload reveal', () => {
  it('uses a line named like the standard item straight away and asks to confirm a similar name', () => {
    expect(isExactMatch('Total revenue', 'Revenue')).toBe(true);
    expect(isExactMatch('Operating income', 'Operating income (EBIT)')).toBe(true);
    expect(isExactMatch('Trade receivables', 'Accounts receivable')).toBe(false);
    const rows = mapRows(mapping, statements, {});
    const rev = rows.find((r) => r.key === 'revenue')!, rec = rows.find((r) => r.key === 'receivables')!;
    expect([rev.certainty, rec.certainty]).toEqual(['reported', 'suggested']);
    expect(accepted(rev, {})).toBe(true);
    expect(accepted(rec, {})).toBe(false);
    expect(accepted(rec, { receivables: 'confirmed' })).toBe(true);
    expect(accepted(rev, { revenue: 'rejected' })).toBe(false);
  });

  it('never sends a rejected or unconfirmed line to the engines', () => {
    const rows = mapRows(mapping, statements, {});
    const inp = inputFromUpload(statements, [], rows, { revenue: 'rejected' });
    expect(inp.lines.map((l) => l.key)).toEqual([null, null]);
    expect(ratioData(inp).data).toEqual({});
    const ok = inputFromUpload(statements, [], rows, { receivables: 'confirmed' });
    expect(ratioData(ok).data).toEqual({ revenue: 12480, receivables: 1720, receivables_prior: 1500 });
  });
});
