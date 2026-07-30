import * as React from "react"

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  padding?: 'none' | 'sm' | 'md' | 'lg';
  tint?: 'default' | 'accent' | 'warning';
  interactive?: boolean;
}

const PADDING = {
  none: "",
  sm: "p-4",
  md: "p-6",
  lg: "p-8",
};

const TINT = {
  default: "bg-[var(--color-surface)] border-[var(--color-border)]",
  accent: "bg-[var(--color-accent-light)] border-[var(--color-accent)]/15",
  warning: "bg-amber-50 border-amber-200",
};

const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, padding = 'md', tint = 'default', interactive = false, ...props }, ref) => (
    <div
      ref={ref}
      className={`rounded-2xl border shadow-[var(--shadow-md)] transition-all duration-200 ease-out ${TINT[tint]} ${PADDING[padding]} ${interactive ? "hover:-translate-y-0.5 hover:shadow-[var(--shadow-xl)]" : ""} ${className ?? ""}`}
      {...props}
    />
  )
)
Card.displayName = "Card"

export { Card }
