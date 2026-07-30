import * as React from "react"

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'icon' | 'ghost' | 'destructive';
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'secondary', ...props }, ref) => {

    const baseStyles = "inline-flex items-center justify-center rounded-xl font-medium transition-all duration-200 ease-out focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]/40 focus:ring-offset-2 focus:ring-offset-[var(--color-bg)] active:scale-[0.98] disabled:opacity-50 disabled:active:scale-100";

    const variants = {
      // Gradient runs dark -> brand rather than brand -> light: both stops clear
      // 4.5:1 against white text, which a lighter endpoint would not.
      primary: "bg-gradient-to-r from-[var(--color-accent-dark)] to-[var(--color-accent)] text-white shadow-[var(--shadow-sm)] hover:-translate-y-0.5 hover:brightness-110 hover:shadow-[var(--shadow-accent-lg)] disabled:hover:translate-y-0 disabled:hover:brightness-100",
      secondary: "bg-white text-[var(--color-ink)] border border-[var(--color-border)] shadow-[var(--shadow-xs)] hover:border-[var(--color-accent)]/30 hover:bg-[var(--color-surface-muted)]",
      icon: "h-11 w-11 rounded-full bg-white text-[var(--color-ink)] border border-[var(--color-border)] shadow-[var(--shadow-xs)] hover:bg-[var(--color-surface-muted)]",
      ghost: "bg-transparent text-[var(--color-muted)] hover:bg-[var(--color-surface-muted)] hover:text-[var(--color-ink)]",
      destructive: "bg-white text-rose-700 border border-rose-200 shadow-[var(--shadow-xs)] hover:bg-rose-50",
    }

    return (
      <button
        ref={ref}
        className={`${baseStyles} ${variants[variant]} ${variant !== 'icon' ? 'px-5 py-2.5' : ''} ${className ?? ""}`}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button }
