import type { ReactNode } from 'react';

/** Shared chart styling so every Recharts chart reads as one system in both themes. */
export const C = {
  c1: 'var(--chart-1)',
  c2: 'var(--chart-2)',
  c3: 'var(--chart-3)',
  c4: 'var(--chart-4)',
  c5: 'var(--chart-5)',
  pos: 'var(--positive)',
  neg: 'var(--negative)',
  grid: 'var(--chart-grid)',
  axis: 'var(--chart-axis)',
  band: 'var(--chart-band)',
};

export const axisProps = {
  stroke: C.axis,
  tick: { fill: 'var(--chart-axis)', fontSize: 11.5 },
  tickLine: false,
  axisLine: { stroke: 'var(--chart-grid)' },
};

export const gridProps = { stroke: C.grid, strokeDasharray: '3 4', vertical: false };

interface TipPayload { name?: string | number; value?: number | string | (number | string)[]; color?: string; dataKey?: string | number; payload?: Record<string, unknown> }

export function ChartTooltip({ active, payload, label, format, labelFormat }: {
  active?: boolean; payload?: TipPayload[]; label?: string | number; format: (v: number, name: string) => string; labelFormat?: (l: string | number) => ReactNode;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <div className="t">{labelFormat && label !== undefined ? labelFormat(label) : label}</div>
      {payload.filter((p) => p.value !== null && p.value !== undefined).map((p) => (
        <div className="r" key={String(p.dataKey ?? p.name)}>
          <span><i className="sw" style={{ background: p.color }} />{p.name}</span>
          <b className="num">{Array.isArray(p.value) ? p.value.map((v) => format(Number(v), String(p.name))).join(' – ') : format(Number(p.value), String(p.name))}</b>
        </div>
      ))}
    </div>
  );
}

export function Legend({ items }: { items: { label: string; color: string; dashed?: boolean }[] }) {
  return (
    <div className="legend">
      {items.map((i) => (
        <span key={i.label} style={{ color: i.dashed ? i.color : undefined }}>
          <i className={i.dashed ? 'dash' : ''} style={{ background: i.color }} />
          <span style={{ color: 'var(--text-muted)' }}>{i.label}</span>
        </span>
      ))}
    </div>
  );
}
