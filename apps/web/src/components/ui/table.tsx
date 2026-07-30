import * as React from "react"

const Table = React.forwardRef<HTMLTableElement, React.TableHTMLAttributes<HTMLTableElement>>(
  ({ className, ...props }, ref) => (
    <table ref={ref} className={`w-full border-collapse text-sm ${className ?? ""}`} {...props} />
  )
);
Table.displayName = "Table";

const Thead = React.forwardRef<HTMLTableSectionElement, React.HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => (
    <thead ref={ref} className={className} {...props} />
  )
);
Thead.displayName = "Thead";

const Th = React.forwardRef<HTMLTableCellElement, React.ThHTMLAttributes<HTMLTableCellElement>>(
  ({ className, ...props }, ref) => (
    <th
      ref={ref}
      className={`border-b border-[var(--color-border)] px-4 py-3 text-left text-xs font-bold uppercase tracking-wide text-[var(--color-muted)] ${className ?? ""}`}
      {...props}
    />
  )
);
Th.displayName = "Th";

const Tr = React.forwardRef<HTMLTableRowElement, React.HTMLAttributes<HTMLTableRowElement>>(
  ({ className, ...props }, ref) => (
    <tr
      ref={ref}
      className={`border-b border-[var(--color-border)] last:border-0 hover:bg-[var(--color-surface-muted)] ${className ?? ""}`}
      {...props}
    />
  )
);
Tr.displayName = "Tr";

const Td = React.forwardRef<HTMLTableCellElement, React.TdHTMLAttributes<HTMLTableCellElement>>(
  ({ className, ...props }, ref) => (
    <td ref={ref} className={`px-4 py-3 ${className ?? ""}`} {...props} />
  )
);
Td.displayName = "Td";

export { Table, Thead, Th, Tr, Td };
