"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Bell, Clock3, FileText, Search, ShieldCheck } from "lucide-react";
import { api, type VendorCase } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusChip } from "@/components/status-chip";

const terminal = new Set(["COMPLETED", "REJECTED", "FAILED", "CANCELLED"]);

export default function Dashboard() {
  const [search, setSearch] = useState("");
  const [showNotifications, setShowNotifications] = useState(false);
  const queryClient = useQueryClient();
  const cases = useQuery({ queryKey: ["cases"], queryFn: api.listCases });
  const notifications = useQuery({ queryKey: ["notifications"], queryFn: api.listNotifications });
  const markRead = useMutation({
    mutationFn: api.markNotificationRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return (cases.data?.items ?? []).filter((item) =>
      !needle || item.title.toLowerCase().includes(needle) || item.case_number.toLowerCase().includes(needle));
  }, [cases.data, search]);
  const pending = filtered.filter((item) => !terminal.has(item.status)).length;
  const approvals = filtered.filter((item) => item.status === "APPROVAL_PENDING").length;
  const blocked = filtered.filter((item) => ["NEEDS_CLARIFICATION", "RISK_REVIEW", "DUPLICATE_REVIEW", "VERIFICATION_FAILED", "ERP_SYNC_FAILED"].includes(item.status)).length;
  const unread = (notifications.data ?? []).filter((item) => !item.read_at).length;

  return (
    <div className="min-h-full p-6 lg:p-12">
      <header className="mb-10 flex flex-col justify-between gap-6 xl:flex-row xl:items-center">
        <div>
          <p className="mb-2 text-sm font-bold uppercase tracking-[0.2em] text-[var(--color-accent)]">Supplier onboarding control room</p>
          <h1 className="font-display text-3xl font-bold">Operational overview</h1>
          <p className="mt-2 text-[var(--color-muted)]">Live case state from the durable workflow—no simulated agent trace.</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative min-w-64 flex-1">
            <Search className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-muted)]" aria-hidden="true" />
            <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search cases" aria-label="Search cases" className="pl-11" />
          </div>
          <div className="relative">
            <Button type="button" variant="icon" onClick={() => setShowNotifications((value) => !value)} aria-label={`${unread} unread notifications`} aria-expanded={showNotifications}>
              <Bell className="h-5 w-5" />
              {unread > 0 && <span className="absolute right-1 top-1 min-w-5 rounded-full bg-red-600 px-1 text-[10px] text-white">{unread}</span>}
            </Button>
            {showNotifications && (
              <Card className="absolute right-0 z-30 mt-3 w-80 p-4">
                <h2 className="mb-3 font-bold">Notifications</h2>
                <div className="max-h-80 space-y-3 overflow-y-auto">
                  {(notifications.data ?? []).length === 0 && <p className="text-sm text-[var(--color-muted)]">No notifications.</p>}
                  {(notifications.data ?? []).map((item) => (
                    <button key={item.notification_id} type="button" onClick={() => !item.read_at && markRead.mutate(item.notification_id)} className="w-full rounded-xl p-3 text-left shadow-[var(--shadow-inset-sm)]">
                      <span className="block text-sm font-bold">{item.title}</span>
                      <span className="mt-1 block text-xs text-[var(--color-muted)]">{item.body}</span>
                    </button>
                  ))}
                </div>
              </Card>
            )}
          </div>
          <Link href="/cases/new"><Button variant="primary">New supplier</Button></Link>
        </div>
      </header>

      {cases.isError && <div role="alert" className="mb-8 rounded-2xl border border-red-300 bg-red-50 p-4 text-red-900">Unable to load cases: {cases.error.message}</div>}

      <section className="mb-10 grid grid-cols-1 gap-6 sm:grid-cols-3" aria-label="Case metrics">
        {[
          { label: "Active cases", value: pending, icon: Clock3, detail: "Across all processing states" },
          { label: "Awaiting approval", value: approvals, icon: ShieldCheck, detail: "Evidence-bound human decisions" },
          { label: "Needs attention", value: blocked, icon: FileText, detail: "Blocked without stopping other services" },
        ].map((metric) => (
          <Card key={metric.label} className="p-6">
            <metric.icon className="mb-4 h-6 w-6 text-[var(--color-accent)]" aria-hidden="true" />
            <p className="text-sm font-bold text-[var(--color-muted)]">{metric.label}</p>
            <p className="my-1 font-display text-4xl font-extrabold">{metric.value}</p>
            <p className="text-xs text-[var(--color-muted)]">{metric.detail}</p>
          </Card>
        ))}
      </section>

      <Card className="p-0">
        <div className="border-b border-white/40 p-6">
          <h2 className="font-display text-xl font-bold">Case work queue</h2>
          <p className="mt-1 text-sm text-[var(--color-muted)]">Status, ownership age and safe next action are sourced from the API.</p>
        </div>
        <div className="divide-y divide-white/40">
          {cases.isLoading && <p className="p-6" aria-live="polite">Loading live cases…</p>}
          {!cases.isLoading && filtered.length === 0 && <p className="p-6 text-[var(--color-muted)]">No supplier cases match this view.</p>}
          {filtered.map((item: VendorCase) => (
            <Link key={item.case_id} href={`/cases/${item.case_id}`} className="grid gap-3 p-6 transition-colors hover:bg-white/20 md:grid-cols-[1.3fr_1fr_auto] md:items-center">
              <div>
                <p className="text-xs font-bold text-[var(--color-muted)]">{item.case_number}</p>
                <p className="mt-1 font-bold">{item.title}</p>
              </div>
              <div className="text-sm text-[var(--color-muted)]">
                <p>{item.priority} priority</p>
                <p>Updated {new Date(item.updated_at).toLocaleString()}</p>
              </div>
              <StatusChip status={item.status} />
            </Link>
          ))}
        </div>
      </Card>
    </div>
  );
}
