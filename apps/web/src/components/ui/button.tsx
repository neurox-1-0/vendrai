import * as React from "react"

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'icon';
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'secondary', ...props }, ref) => {
    
    let baseStyles = "inline-flex items-center justify-center rounded-2xl font-medium transition-all duration-300 ease-out focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] focus:ring-offset-2 focus:ring-offset-[var(--color-clay)] active:translate-y-[1px]";
    
    let variants = {
      primary: "bg-[var(--color-accent)] text-white shadow-[var(--shadow-extruded)] hover:-translate-y-[1px] hover:shadow-[var(--shadow-extruded-hover)] active:shadow-[var(--shadow-inset-sm)]",
      secondary: "bg-[var(--color-clay)] text-[var(--color-primary)] shadow-[var(--shadow-extruded)] hover:-translate-y-[1px] hover:shadow-[var(--shadow-extruded-hover)] active:shadow-[var(--shadow-inset-sm)]",
      icon: "bg-[var(--color-clay)] text-[var(--color-primary)] shadow-[var(--shadow-extruded-sm)] hover:-translate-y-[1px] hover:shadow-[var(--shadow-extruded-hover)] active:shadow-[var(--shadow-inset-sm)] h-12 w-12 rounded-full",
    }
    
    return (
      <button
        ref={ref}
        className={`${baseStyles} ${variants[variant]} ${variant !== 'icon' ? 'px-6 py-3' : ''} ${className}`}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button }
