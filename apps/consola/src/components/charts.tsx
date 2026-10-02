/**
 * Chart conventions (dataviz guide): one y-axis, thin marks with 4px rounded data-ends,
 * recessive grid/axes, hover tooltip on every chart, legend for >= 2 series, text in text
 * tokens (never the series colour). Series colours are the validated --series-* tokens.
 */
import type { ReactNode } from 'react'

export const AXIS = {
  tickLine: false,
  axisLine: false,
  tick: { fill: 'var(--muted-foreground)', fontSize: 11 },
} as const
export const GRID = { vertical: false, stroke: 'var(--border)' } as const
export const SERIES = ['var(--series-1)', 'var(--series-2)'] as const
export const CURSOR = { fill: 'var(--muted)', opacity: 0.6 }

interface TooltipRow {
  name?: string | number
  value?: number | string
  color?: string
  payload?: Record<string, unknown>
}

/** Tooltip body: header + one row per series, values formatted by `format`. */
export function ChartTooltip({
  active,
  payload,
  label,
  format,
  labelFormat,
}: {
  active?: boolean
  payload?: TooltipRow[]
  label?: string | number
  format: (v: number) => string
  labelFormat?: (l: string | number) => string
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border bg-card px-3 py-2 text-xs shadow-md">
      <p className="mb-1 font-semibold">
        {label != null ? (labelFormat ? labelFormat(label) : label) : ''}
      </p>
      {payload.map((p) => (
        <p key={String(p.name)} className="flex items-center gap-2">
          <span
            className="inline-block size-2 rounded-full"
            style={{ background: p.color }}
            aria-hidden
          />
          <span className="text-muted-foreground">{p.name}</span>
          <span className="ml-auto font-medium tabular-nums">{format(Number(p.value))}</span>
        </p>
      ))}
    </div>
  )
}

export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <ul className="flex flex-wrap gap-4 text-xs text-muted-foreground" aria-label="Leyenda">
      {items.map((i) => (
        <li key={i.label} className="flex items-center gap-1.5">
          <span
            className="inline-block h-2 w-4 rounded-sm"
            style={{ background: i.color }}
            aria-hidden
          />
          {i.label}
        </li>
      ))}
    </ul>
  )
}

/** Wraps a chart with an accessible name and a data table alternative for screen readers. */
export function ChartFrame({
  label,
  height = 'h-64',
  table,
  children,
}: {
  label: string
  height?: string
  table: { headers: string[]; rows: (string | number)[][] }
  children: ReactNode
}) {
  return (
    <figure className="m-0">
      <div className={height} role="img" aria-label={label}>
        {children}
      </div>
      <table className="sr-only">
        <caption>{label}</caption>
        <thead>
          <tr>
            {table.headers.map((h) => (
              <th key={h} scope="col">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((r, i) => (
            <tr key={i}>
              {r.map((c, j) => (
                <td key={j}>{c}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  )
}
