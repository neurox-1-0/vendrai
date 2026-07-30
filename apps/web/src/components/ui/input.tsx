import * as React from "react"

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={`flex h-11 w-full rounded-xl border border-[var(--color-border)] bg-white px-4 py-2 text-[var(--color-ink)] shadow-[var(--shadow-xs)] transition-colors duration-150 placeholder:text-[var(--color-muted)] focus:outline-none focus:border-[var(--color-accent)] focus:ring-2 focus:ring-[var(--color-accent)]/25 disabled:cursor-not-allowed disabled:opacity-50 ${className ?? ""}`}
        ref={ref}
        {...props}
      />
    )
  }
)
Input.displayName = "Input"

export { Input }
