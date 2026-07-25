"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Bell, Clock3, FileText, Search, ShieldCheck } from "lucide-react";
import { useGetWorkQueueApiV1WorkQueueGet } from "@/generated/neurox";
import type { WorkQueueItem } from "@/generated/models";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusChip } from "@/components/status-chip";

const terminal = new Set(["COMPLETED", "REJECTED", "FAILED", "CANCELLED"]);
const defaultFilters = {
  status: "",
  caseType: "",
  priority: "",
  ownership: "ALL",
};

export default function Dashboard() {
  const [search, setSearch] = useState("");
  const [showNotifications, setShowNotifications] = useState(false);
  const [filters, setFilters] = useState(() => {
    if (typeof window === "undefined") return defaultFilters;
    const saved = window.localStorage.getItem("neurox-work-queue-filters");
    if (!saved) return defaultFilters;
    try {
      return {
        ...defaultFilters,
        ...JSON.parse(saved) as Partial<typeof defaultFilters>,
      };
    } catch {
      return defaultFilters;
    }
  });
  const queryClient = useQueryClient();
  const cases = useGetWorkQueueApiV1WorkQueueGet({
    status: filters.status || undefined,
    case_type: filters.caseType || undefined,
    priority: filters.priority || undefined,
    ownership: filters.ownership,
  });
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
  useEffect(() => {
    window.localStorage.setItem("neurox-work-queue-filters", JSON.stringify(filters));
  }, [filters]);
  useEffect(() => {
    const openPanel = (event: Event) => {
      const panel = (event as CustomEvent<{ panel?: string }>).detail?.panel;
      if (panel === "notifications") setShowNotifications(true);
    };
    window.addEventListener("neurox:open-panel", openPanel);
    return () => window.removeEventListener("neurox:open-panel", openPanel);
  }, []);

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
          <div className="relative" data-panel-id="notifications">
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

      {cases.isError && <div role="alert" className="mb-8 rounded-2xl border border-red-300 bg-red-50 p-4 text-red-900">Unable to load the work queue. Check your role and integration health.</div>}

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
          <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-5" aria-label="Saved work queue filters">
            <select
              aria-label="Case type"
              value={filters.caseType}
              onChange={(event) => setFilters((current) => ({ ...current, caseType: event.target.value }))}
              className="h-11 rounded-xl bg-white/60 px-3 text-sm shadow-[var(--shadow-inset-sm)]"
            >
              <option value="">All case types</option>
              <option value="VENDOR_ONBOARDING">Supplier onboarding</option>
              <option value="INVOICE_EXCEPTION">Invoice exception</option>
            </select>
            <select
              aria-label="Status"
              value={filters.status}
              onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}
              className="h-11 rounded-xl bg-white/60 px-3 text-sm shadow-[var(--shadow-inset-sm)]"
            >
              <option value="">All statuses</option>
              <option value="NEEDS_CLARIFICATION">Needs clarification</option>
              <option value="DUPLICATE_REVIEW">Duplicate review</option>
              <option value="RISK_REVIEW">Risk review</option>
              <option value="APPROVAL_PENDING">Approval pending</option>
              <option value="ERP_SYNC_FAILED">ERP retry</option>
              <option value="COMPLETED">Completed</option>
            </select>
            <select
              aria-label="Priority"
              value={filters.priority}
              onChange={(event) => setFilters((current) => ({ ...current, priority: event.target.value }))}
              className="h-11 rounded-xl bg-white/60 px-3 text-sm shadow-[var(--shadow-inset-sm)]"
            >
              <option value="">All priorities</option>
              <option value="URGENT">Urgent</option>
              <option value="HIGH">High</option>
              <option value="NORMAL">Normal</option>
              <option value="LOW">Low</option>
            </select>
            <select
              aria-label="Ownership"
              value={filters.ownership}
              onChange={(event) => setFilters((current) => ({ ...current, ownership: event.target.value }))}
              className="h-11 rounded-xl bg-white/60 px-3 text-sm shadow-[var(--shadow-inset-sm)]"
            >
              <option value="ALL">All ownership</option>
              <option value="MINE">Mine</option>
              <option value="UNCLAIMED">Unclaimed</option>
            </select>
            <Button type="button" variant="secondary" onClick={() => setFilters(defaultFilters)}>
              Reset saved view
            </Button>
          </div>
        </div>
        <div className="divide-y divide-white/40">
          {cases.isLoading && <p className="p-6" aria-live="polite">Loading live cases…</p>}
          {!cases.isLoading && filtered.length === 0 && <p className="p-6 text-[var(--color-muted)]">No supplier cases match this view.</p>}
          {filtered.map((item: WorkQueueItem) => (
            <Link key={item.case_id} href={`/cases/${item.case_id}`} className="grid gap-3 p-6 transition-colors hover:bg-white/20 md:grid-cols-[1.3fr_1fr_auto] md:items-center">
              <div>
                <p className="text-xs font-bold text-[var(--color-muted)]">{item.case_number}</p>
                <p className="mt-1 font-bold">{item.title}</p>
              </div>
              <div className="text-sm text-[var(--color-muted)]">
                <p>{item.priority} priority</p>
                <p>{item.ownership.toLowerCase()} · {Math.max(1, Math.round(item.age_seconds / 3600))}h old</p>
              </div>
              <StatusChip status={item.status} />
            </Link>
          ))}
        </div>
      </Card>
    </div>
  );
}
