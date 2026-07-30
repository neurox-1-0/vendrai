import * as React from "react"
import { Check, CircleDashed, LoaderCircle, XCircle } from "lucide-react"

export interface ProgressStepsProps {
  steps: string[];
  /** null = not started; index = the step currently running (0-based). */
  currentIndex: number | null;
  error?: boolean;
}

/**
 * Replaces the "replace one line of text per step" submit-progress pattern
 * used by both intake forms with a persistent step list: earlier steps stay
 * visible as completed rather than disappearing when the next one starts.
 */
function ProgressSteps({ steps, currentIndex, error }: ProgressStepsProps) {
  if (currentIndex === null) return null;
  return (
    <ol aria-live="polite" className="space-y-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)] p-4">
      {steps.map((step, index) => {
        const done = index < currentIndex || (index === currentIndex && error === false);
        const active = index === currentIndex;
        const failed = active && error;
        return (
          <li key={step} className="flex items-center gap-3 text-sm">
            {failed ? (
              <XCircle className="h-4 w-4 shrink-0 text-rose-600" aria-hidden="true" />
            ) : done ? (
              <Check className="h-4 w-4 shrink-0 text-emerald-600" aria-hidden="true" />
            ) : active ? (
              <LoaderCircle className="h-4 w-4 shrink-0 animate-spin text-[var(--color-accent)]" aria-hidden="true" />
            ) : (
              <CircleDashed className="h-4 w-4 shrink-0 text-[var(--color-muted)]" aria-hidden="true" />
            )}
            <span className={active ? "font-bold text-[var(--color-ink)]" : done ? "text-[var(--color-ink)]" : "text-[var(--color-muted)]"}>
              {step}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export { ProgressSteps };
