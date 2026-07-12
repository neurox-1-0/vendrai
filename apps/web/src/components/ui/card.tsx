import * as React from "react"

const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={`rounded-3xl bg-[var(--color-clay)] shadow-[var(--shadow-extruded)] p-8 transition-transform duration-300 ease-out hover:-translate-y-[2px] hover:shadow-[var(--shadow-extruded-hover)] ${className}`}
      {...props}
    />
  )
)
Card.displayName = "Card"

export { Card }
