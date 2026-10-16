import { describe, expect, it } from 'vitest';
import { csvCell, fmtCompact, fmtMoney, fmtNum, fmtPct, fmtPctPoints, fmtScaled, parseInputNumber, setNumberStyle, toCSV } from './format';

describe('format', () => {
  it('formats decimals and percentage points distinctly', () => {
    expect(fmtPct(0.1234)).toBe('12.34%');
    expect(fmtPctPoints(12.34, 1)).toBe('12.3%');
    expect(fmtPct(-0.05, 1)).toBe('−5.0%');
    expect(fmtPct(null)).toBe('—');
    expect(fmtPct(Number.NaN)).toBe('—');
  });

  it('compacts INR in lakhs/crores', () => {
    expect(fmtCompact(250000, 'INR')).toBe('2.5L');
    expect(fmtCompact(32000000, 'INR')).toBe('3.2Cr');
    expect(fmtCompact(2500000, 'USD')).toBe('2.5M');
  });

  it('parses user-typed numbers without turning blanks into zero', () => {
    expect(parseInputNumber('1,234.5')).toBe(1234.5);
    expect(parseInputNumber('(500)')).toBe(-500);
    expect(parseInputNumber('₹ 2,000')).toBe(2000);
    expect(parseInputNumber('')).toBeNull();
    expect(parseInputNumber('abc')).toBeNull();
  });

  it('neutralises CSV formula injection but keeps negative numbers', () => {
    expect(csvCell('=HYPERLINK("x")')).toBe(`"'=HYPERLINK(""x"")"`);
    expect(csvCell('@SUM(A1)')).toBe(`"'@SUM(A1)"`);
    expect(csvCell('-12.5')).toBe('"-12.5"');
    expect(csvCell(-12.5)).toBe('"-12.5"');
    expect(toCSV([['a', 1], ['b', null]])).toBe('"a","1"\r\n"b",""');
  });

  it('groups digits the Indian or international way', () => {
    setNumberStyle('auto');
    expect(fmtNum(12345678, 0, 'INR')).toBe('1,23,45,678');
    expect(fmtNum(12345678, 0, 'USD')).toBe('12,345,678');
    setNumberStyle('indian');
    expect(fmtNum(12345678, 0, 'USD')).toBe('1,23,45,678');
    setNumberStyle('international');
    expect(fmtNum(12345678, 0, 'INR')).toBe('12,345,678');
    setNumberStyle('auto');
  });

  it('labels amounts stored in lakhs or crores', () => {
    expect(fmtScaled(255324, 'crores')).toBe(`${fmtMoney(255324)} Cr`);
    expect(fmtScaled(255324, 'crores')).toContain('2,55,324');
    expect(fmtScaled(null, 'crores')).toBe('—');
    expect(fmtScaled(1500, 'units')).toBe(fmtMoney(1500));
  });
});
