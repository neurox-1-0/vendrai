import * as React from "react"

interface IconWellProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
}

const IconWell = React.forwardRef<HTMLDivElement, IconWellProps>(
  ({ className, children, ...props }, ref) => (
    <div
      ref={ref}
      className={`flex items-center justify-center rounded-2xl bg-[var(--color-accent-light)] h-14 w-14 text-[var(--color-accent)] ${className ?? ""}`}
      {...props}
    >
      {children}
    </div>
  )
)
IconWell.displayName = "IconWell"

export { IconWell }
