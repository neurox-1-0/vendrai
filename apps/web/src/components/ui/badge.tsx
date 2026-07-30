import * as React from "react"
import type { LucideIcon } from "lucide-react"

export type BadgeTone = 'positive' | 'negative' | 'warning' | 'info' | 'neutral' | 'brand';

export interface BadgeProps {
  tone?: BadgeTone;
  icon?: LucideIcon;
  className?: string;
  children: React.ReactNode;
}

const TONE_CLASSES: Record<BadgeTone, string> = {
  positive: "bg-emerald-50 text-emerald-700",
  negative: "bg-rose-50 text-rose-700",
  warning: "bg-amber-50 text-amber-700",
  info: "bg-blue-50 text-blue-700",
  neutral: "bg-slate-100 text-slate-600",
  brand: "bg-gradient-to-r from-[var(--color-accent)] to-[var(--color-accent-secondary)] text-white",
};

/**
 * The one shared pill-badge primitive for every status/delta/tag indicator in
 * the app -- status chips, evidence provenance, approval state, severity,
 * exception/match status, and small numeric deltas all render through this
 * rather than each hand-coding its own `bg-*-100 text-*-900` pair.
 */
function Badge({ tone = 'neutral', icon: Icon, className, children }: BadgeProps) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold ${TONE_CLASSES[tone]} ${className ?? ""}`}>
      {Icon && <Icon aria-hidden="true" className="h-3.5 w-3.5" />}
      {children}
    </span>
  );
}

export { Badge };
