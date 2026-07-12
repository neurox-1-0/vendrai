import * as React from "react"

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={`flex h-12 w-full rounded-2xl bg-[var(--color-clay)] px-4 py-2 text-[var(--color-primary)] shadow-[var(--shadow-inset)] transition-all duration-300 placeholder:text-[var(--color-muted)] focus:outline-none focus:shadow-[var(--shadow-inset-deep)] focus:ring-2 focus:ring-[var(--color-accent)] focus:ring-offset-2 focus:ring-offset-[var(--color-clay)] disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
        ref={ref}
        {...props}
      />
    )
  }
)
Input.displayName = "Input"

export { Input }
