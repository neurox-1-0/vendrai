import * as React from "react"

export interface JsonViewerProps {
  data: unknown;
  title?: string;
  collapsed?: boolean;
  className?: string;
}

function Pre({ data, className }: { data: unknown; className?: string }) {
  return (
    <pre
      className={`overflow-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)] p-3 font-mono text-xs text-[var(--color-ink)] ${className ?? ""}`}
    >
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

/**
 * Replaces the app's various raw `<pre className="bg-slate-900...">` JSON
 * dumps (workflow events, evidence signals, OCR page text, diagnostics) with
 * one consistent, on-brand block. `collapsed` wraps it in a native
 * <details> so long dumps (OCR text, diagnostics) don't dominate the page.
 */
function JsonViewer({ data, title, collapsed, className }: JsonViewerProps) {
  if (collapsed) {
    return (
      <details className="text-xs text-[var(--color-muted)]">
        <summary className="cursor-pointer font-bold text-[var(--color-ink)]">
          {title ?? "Details"}
        </summary>
        <div className="mt-2">
          <Pre data={data} className={className} />
        </div>
      </details>
    );
  }
  return (
    <div>
      {title && <p className="mb-2 text-xs font-bold uppercase tracking-wide text-[var(--color-muted)]">{title}</p>}
      <Pre data={data} className={className} />
    </div>
  );
}

export { JsonViewer };
