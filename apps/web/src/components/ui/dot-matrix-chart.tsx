import * as React from "react"
import { Table, Thead, Th, Tr, Td } from "@/components/ui/table"

export interface DotMatrixPoint {
  label: string;
  /** Rendered as the darker, bottom series of dots. */
  a: number;
  /** Rendered as the paler, upper series of dots, stacked on top of `a`. */
  b: number;
}

export interface DotMatrixChartProps {
  data: DotMatrixPoint[];
  seriesALabel: string;
  seriesBLabel: string;
  /** Index of the column to render solid and call out with a value bubble. */
  highlightIndex?: number;
  formatValue?: (value: number) => string;
  ariaLabel: string;
}

const DOT_RADIUS = 3.5;
const DOT_GAP = 4;
const DOT_STEP = DOT_RADIUS * 2 + DOT_GAP;
const COLUMN_WIDTH = 22;
const CHART_HEIGHT = 220;
const MAX_ROWS = Math.floor(CHART_HEIGHT / DOT_STEP);

/**
 * Bespoke "dot-matrix" bar chart: each column is a bottom-up stack of small
 * circles rather than a solid bar. Deliberately custom rather than a recharts
 * shape -- this exact pixel/pin-art look has no off-the-shelf equivalent, and
 * it is reserved for this one dashboard metric (see the redesign plan) rather
 * than replacing the Analytics page's standard line/bar charts.
 */
function DotMatrixChart({
  data,
  seriesALabel,
  seriesBLabel,
  highlightIndex,
  formatValue = (value) => String(value),
  ariaLabel,
}: DotMatrixChartProps) {
  const maxTotal = Math.max(1, ...data.map((point) => point.a + point.b));
  const columnGap = 14;
  const width = data.length * COLUMN_WIDTH + Math.max(0, data.length - 1) * columnGap;

  return (
    <div>
      <div role="img" aria-label={ariaLabel} className="relative overflow-x-auto">
        <svg
          viewBox={`0 0 ${width} ${CHART_HEIGHT + 28}`}
          width="100%"
          height={CHART_HEIGHT + 28}
          preserveAspectRatio="xMidYMax meet"
          aria-hidden="true"
        >
          {data.map((point, index) => {
            const total = point.a + point.b;
            const rows = Math.min(MAX_ROWS, Math.round((total / maxTotal) * MAX_ROWS));
            const aRows = Math.round((point.a / Math.max(1, total)) * rows);
            const x = index * (COLUMN_WIDTH + columnGap) + COLUMN_WIDTH / 2;
            const highlighted = index === highlightIndex;
            const baseY = CHART_HEIGHT;

            const dots: React.ReactNode[] = [];
            for (let row = 0; row < rows; row += 1) {
              const isSeriesA = row < aRows;
              dots.push(
                <circle
                  key={row}
                  cx={x}
                  cy={baseY - row * DOT_STEP - DOT_RADIUS}
                  r={DOT_RADIUS}
                  className={
                    highlighted
                      ? "fill-[var(--color-accent)]"
                      : isSeriesA
                        ? "fill-emerald-500"
                        : "fill-emerald-200"
                  }
                />
              );
            }

            return (
              <g key={point.label}>
                {dots}
                {highlighted && rows > 0 && (
                  <line
                    x1={x}
                    y1={baseY - rows * DOT_STEP}
                    x2={x}
                    y2={0}
                    className="stroke-slate-300"
                    strokeWidth={1}
                    strokeDasharray="3 3"
                  />
                )}
                <text
                  x={x}
                  y={CHART_HEIGHT + 18}
                  textAnchor="middle"
                  className="fill-[var(--color-muted)] text-[10px] font-medium"
                >
                  {point.label}
                </text>
              </g>
            );
          })}
        </svg>
        {highlightIndex !== undefined && data[highlightIndex] && (
          <div
            className="pointer-events-none absolute -translate-x-1/2 -translate-y-full rounded-xl bg-slate-900 px-2.5 py-1.5 text-xs font-bold text-white shadow-[var(--shadow-md)]"
            style={{
              left: `${((highlightIndex * (COLUMN_WIDTH + columnGap) + COLUMN_WIDTH / 2) / width) * 100}%`,
              top: `${
                (1 -
                  Math.min(
                    MAX_ROWS,
                    Math.round(
                      ((data[highlightIndex].a + data[highlightIndex].b) / maxTotal) * MAX_ROWS,
                    ),
                  ) /
                    MAX_ROWS) *
                CHART_HEIGHT
              }px`,
            }}
          >
            {formatValue(data[highlightIndex].a + data[highlightIndex].b)}
          </div>
        )}
      </div>
      <div className="mt-4 flex items-center gap-5 text-xs text-[var(--color-muted)]">
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />{seriesALabel}</span>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-emerald-200" />{seriesBLabel}</span>
      </div>
      <Table className="sr-only">
        <caption>{ariaLabel}</caption>
        <Thead>
          <Tr>
            <Th>Date</Th>
            <Th>{seriesALabel}</Th>
            <Th>{seriesBLabel}</Th>
          </Tr>
        </Thead>
        <tbody>
          {data.map((point) => (
            <Tr key={point.label}>
              <Td>{point.label}</Td>
              <Td>{point.a}</Td>
              <Td>{point.b}</Td>
            </Tr>
          ))}
        </tbody>
      </Table>
    </div>
  );
}

export { DotMatrixChart };
