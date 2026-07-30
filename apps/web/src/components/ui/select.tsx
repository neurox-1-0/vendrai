import * as React from "react"
import { ChevronDown } from "lucide-react"

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  children: React.ReactNode;
}

/**
 * Styled native <select>. A native element is kept deliberately -- it gives
 * free keyboard/screen-reader behavior and needs no portal/positioning logic,
 * which matters more here than matching a custom-dropdown look pixel-for-pixel.
 */
const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, children, ...props }, ref) => (
    <div className="relative">
      <select
        ref={ref}
        className={`h-11 w-full appearance-none rounded-xl border border-[var(--color-border)] bg-white pl-4 pr-10 text-sm text-[var(--color-ink)] shadow-[var(--shadow-xs)] transition-colors duration-150 focus:outline-none focus:border-[var(--color-accent)] focus:ring-2 focus:ring-[var(--color-accent)]/25 disabled:cursor-not-allowed disabled:opacity-50 ${className ?? ""}`}
        {...props}
      >
        {children}
      </select>
      <ChevronDown
        aria-hidden="true"
        className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-muted)]"
      />
    </div>
  )
)
Select.displayName = "Select"

export { Select }
