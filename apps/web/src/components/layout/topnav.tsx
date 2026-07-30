"use client";

import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  ClipboardList,
  FileText,
  LayoutDashboard,
  LogOut,
  Receipt,
  Settings,
  Users,
} from "lucide-react";
import { useAuth } from "@/app/providers";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Avatar } from "@/components/ui/avatar";
import { NotificationBell } from "@/components/notification-bell";

const NAV_ITEMS = [
  { value: "/", label: "Dashboard", href: "/", icon: LayoutDashboard },
  { value: "/cases/new", label: "Supplier Onboarding", href: "/cases/new", icon: FileText, roles: ["requester", "analyst", "admin"] },
  { value: "/invoices/new", label: "Invoice Exceptions", href: "/invoices/new", icon: Receipt, roles: ["requester", "analyst", "admin"] },
  { value: "/approvals", label: "Approvals", href: "/approvals", icon: Users, roles: ["analyst", "approver", "procurement_approver", "compliance_approver", "finance_approver", "auditor", "admin"] },
  { value: "/analytics", label: "Analytics", href: "/analytics", icon: Activity, roles: ["analyst", "auditor", "admin"] },
  { value: "/reports", label: "Reports", href: "/reports", icon: ClipboardList, roles: ["auditor", "admin"] },
];

function AvatarMenu() {
  const { roles, displayName, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const role = [...roles][0] ?? "user";

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-label="Account menu"
        aria-expanded={open}
        aria-haspopup="menu"
        className="rounded-full focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]/40 focus:ring-offset-2"
      >
        <Avatar name={displayName} size="md" />
      </button>
      {open && (
        <>
          <button
            type="button"
            aria-hidden="true"
            tabIndex={-1}
            className="fixed inset-0 z-20 cursor-default"
            onClick={() => setOpen(false)}
          />
          <div
            role="menu"
            className="absolute right-0 z-30 mt-3 w-56 rounded-2xl border border-white/70 bg-white/85 p-2 shadow-[0_12px_36px_rgba(17,24,39,0.14)] backdrop-blur-xl backdrop-saturate-150"
          >
            <div className="px-3 py-2">
              <p className="truncate font-bold text-[var(--color-ink)]">{displayName}</p>
              <p className="truncate text-xs capitalize text-[var(--color-muted)]">{role.replaceAll("_", " ")}</p>
            </div>
            <div className="my-1 h-px bg-[var(--color-border)]" />
            <Link
              href="/admin"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium text-[var(--color-ink)] hover:bg-[var(--color-surface-muted)]"
            >
              <Settings className="h-4 w-4" aria-hidden="true" />
              Help &amp; Support
            </Link>
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                logout();
              }}
              className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm font-medium text-rose-700 hover:bg-rose-50"
            >
              <LogOut className="h-4 w-4" aria-hidden="true" />
              Sign out
            </button>
          </div>
        </>
      )}
    </div>
  );
}

export function TopNav() {
  const pathname = usePathname();
  const { roles } = useAuth();

  const items = NAV_ITEMS.filter((item) => !item.roles || item.roles.some((role) => roles.has(role)));
  const active = items.find((item) => item.href === "/" ? pathname === "/" : pathname.startsWith(item.href))?.value ?? "/";

  return (
    /*
     * Floating frosted pill. The header stays in flow (position: sticky) so it
     * still reserves its own height, but the bar itself detaches from the page
     * edges and content scrolls through the gap behind it. `backdrop-saturate`
     * alongside the blur is what sells the glass -- blur alone reads as a flat
     * translucent wash, saturation is what makes colours bloom through it.
     */
    <header className="sticky top-0 z-30 px-3 pt-3 md:px-6 md:pt-4">
      <div className="mx-auto flex h-16 w-fit max-w-full items-center gap-3 rounded-full border border-white/70 bg-white/65 px-4 shadow-[0_8px_32px_rgba(17,24,39,0.10)] backdrop-blur-xl backdrop-saturate-150 md:px-5">
        <Link
          href="/"
          className="flex shrink-0 items-center gap-2 rounded-full transition-opacity duration-200 hover:opacity-80"
        >
          <Image src="/Full logo.svg" alt="" width={32} height={32} className="h-8 w-8 rounded-lg" priority />
          <span className="hidden font-display text-lg font-bold text-[var(--color-ink)] sm:inline">Vendrai</span>
        </Link>

        <nav
          aria-label="Primary"
          className="flex min-w-0 flex-1 gap-2 overflow-x-auto [scrollbar-width:none] md:flex-none md:overflow-visible [&::-webkit-scrollbar]:hidden"
        >
          <SegmentedControl
            items={items}
            value={active}
            track="transparent"
            className="snap-x"
            itemClassName="snap-start"
          />
        </nav>

        <div className="flex shrink-0 items-center gap-2">
          <NotificationBell />
          <AvatarMenu />
        </div>
      </div>
    </header>
  );
}
