"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Clock3, FileText, Search, ShieldCheck } from "lucide-react";
import { useGetWorkQueueApiV1WorkQueueGet } from "@/generated/neurox";
import type { WorkQueueItem } from "@/generated/models";
import { api, type VendorCase } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { StatusChip } from "@/components/status-chip";
import { DotMatrixChart } from "@/components/ui/dot-matrix-chart";
import { DockedAssistantCard } from "@/components/docked-assistant-card";
import { useAssistanceTarget } from "@/components/assistance-registry";

const terminal = new Set(["COMPLETED", "REJECTED", "FAILED", "CANCELLED"]);
const successStatuses = new Set(["COMPLETED", "APPROVED", "AUTO_RESOLVED"]);
const defaultFilters = {
  status: "",
  caseType: "",
  priority: "",
  ownership: "ALL",
};

/** Bucket cases by created_at day, for the trailing `days` days ending today. */
function bucketByDay(cases: VendorCase[], days: number) {
  const buckets = new Map<string, { a: number; b: number }>();
  const today = new Date();
  for (let offset = days - 1; offset >= 0; offset -= 1) {
    const date = new Date(today);
    date.setDate(date.getDate() - offset);
    buckets.set(date.toISOString().slice(0, 10), { a: 0, b: 0 });
  }
  for (const item of cases) {
    const day = item.created_at.slice(0, 10);
    const bucket = buckets.get(day);
    if (!bucket) continue;
    if (successStatuses.has(item.status)) bucket.a += 1;
    else bucket.b += 1;
  }
  return [...buckets.entries()].map(([day, counts]) => ({
    label: new Date(day).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
    ...counts,
  }));
}

/** Cases created in the last `days` days, vs. the `days` before that. */
function periodDelta(cases: VendorCase[], predicate: (item: VendorCase) => boolean, days = 7) {
  const now = Date.now();
  const dayMs = 24 * 60 * 60 * 1000;
  let recent = 0;
  let prior = 0;
  for (const item of cases) {
    if (!predicate(item)) continue;
    const age = now - new Date(item.created_at).getTime();
    if (age <= days * dayMs) recent += 1;
    else if (age <= days * 2 * dayMs) prior += 1;
  }
  return recent - prior;
}

function DeltaBadge({ delta }: { delta: number }) {
  if (delta === 0) return null;
  return (
    <Badge tone={delta > 0 ? "positive" : "negative"}>
      {delta > 0 ? "+" : ""}
      {delta}
    </Badge>
  );
}

export default function Dashboard() {
  const queueAssistance = useAssistanceTarget({
    id: "dashboard.work-queue",
    title: "Case work queue",
    description:
      "Filter durable supplier and invoice work by status, priority and ownership, then open the case requiring attention.",
    tour: "dashboard.orientation",
    order: 10,
  });
  const [search, setSearch] = useState("");
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
  const cases = useGetWorkQueueApiV1WorkQueueGet({
    status: filters.status || undefined,
    case_type: filters.caseType || undefined,
    priority: filters.priority || undefined,
    ownership: filters.ownership,
  });
  const allCases = useQuery({ queryKey: ["cases"], queryFn: api.listCases });

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return (cases.data?.items ?? []).filter((item) =>
      !needle || item.title.toLowerCase().includes(needle) || item.case_number.toLowerCase().includes(needle));
  }, [cases.data, search]);
  const pending = filtered.filter((item) => !terminal.has(item.status)).length;
  const approvals = filtered.filter((item) => item.status === "APPROVAL_PENDING").length;
  const blocked = filtered.filter((item) => ["NEEDS_CLARIFICATION", "RISK_REVIEW", "DUPLICATE_REVIEW", "VERIFICATION_FAILED", "ERP_SYNC_FAILED"].includes(item.status)).length;

  const rows = allCases.data?.items ?? [];
  const chartData = useMemo(() => bucketByDay(rows, 14), [rows]);
  const highlightIndex = useMemo(() => {
    if (chartData.length === 0) return undefined;
    let bestIndex = 0;
    let bestTotal = -1;
    chartData.forEach((point, index) => {
      const total = point.a + point.b;
      if (total > bestTotal) {
        bestTotal = total;
        bestIndex = index;
      }
    });
    return bestTotal > 0 ? bestIndex : undefined;
  }, [chartData]);
  const insight = useMemo(() => {
    if (highlightIndex === undefined) return null;
    const peak = chartData[highlightIndex];
    const total = peak.a + peak.b;
    const pct = total > 0 ? Math.round((peak.a / total) * 100) : 0;
    return `${peak.label} had the highest volume with ${total} case${total === 1 ? "" : "s"}, ${pct}% resolved same-day.`;
  }, [chartData, highlightIndex]);

  const activeDelta = periodDelta(rows, (item) => !terminal.has(item.status));
  const approvalDelta = periodDelta(rows, (item) => item.status === "APPROVAL_PENDING");
  const blockedDelta = periodDelta(rows, (item) =>
    ["NEEDS_CLARIFICATION", "RISK_REVIEW", "DUPLICATE_REVIEW", "VERIFICATION_FAILED", "ERP_SYNC_FAILED"].includes(item.status));

  useEffect(() => {
    window.localStorage.setItem("neurox-work-queue-filters", JSON.stringify(filters));
  }, [filters]);

  return (
    <div className="min-h-full p-6 lg:p-12">
      <header className="mb-10 flex flex-col justify-between gap-6 xl:flex-row xl:items-center">
        <div>
          <p className="mb-1 text-sm font-bold text-[var(--color-accent)]">Supplier onboarding control room</p>
          <h1 className="font-display text-3xl font-bold">Operational overview</h1>
          <p className="mt-2 text-[var(--color-muted)]">Live case state from the durable workflow—no simulated agent trace.</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative min-w-64 flex-1">
            <Search className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-muted)]" aria-hidden="true" />
            <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search cases" aria-label="Search cases" className="pl-11" />
          </div>
          <Link href="/cases/new"><Button variant="primary">New supplier</Button></Link>
        </div>
      </header>

      {cases.isError && <div role="alert" className="mb-8 rounded-xl border border-rose-200 bg-rose-50 p-4 text-rose-900">Unable to load the work queue. Check your role and integration health.</div>}

      <section className="mb-8 grid grid-cols-1 gap-6 sm:grid-cols-3" aria-label="Case metrics">
        {[
          { label: "Active cases", value: pending, icon: Clock3, detail: "Across all processing states", delta: activeDelta },
          { label: "Awaiting approval", value: approvals, icon: ShieldCheck, detail: "Evidence-bound human decisions", delta: approvalDelta },
          { label: "Needs attention", value: blocked, icon: FileText, detail: "Blocked without stopping other services", delta: blockedDelta },
        ].map((metric) => (
          <Card key={metric.label}>
            <div className="flex items-start justify-between">
              <p className="text-sm font-bold text-[var(--color-muted)]">{metric.label}</p>
              <DeltaBadge delta={metric.delta} />
            </div>
            <p className="my-1 font-display text-4xl font-extrabold text-[var(--color-ink)]">{metric.value}</p>
            <p className="text-xs text-[var(--color-muted)]">{metric.detail}</p>
          </Card>
        ))}
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.6fr_1fr]">
        <div className="space-y-6">
          <Card>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="font-display text-lg font-bold">Case volume</h2>
                <p className="mt-1 text-sm text-[var(--color-muted)]">Last 14 days, resolved same-day vs still in flight.</p>
              </div>
            </div>
            {insight && (
              <div className="mt-4 flex items-start gap-2 rounded-xl bg-[var(--color-accent-light)] p-3 text-sm text-[var(--color-accent-dark)]">
                <span aria-hidden="true">✨</span>
                <p>{insight}</p>
              </div>
            )}
            <div className="mt-6">
              <DotMatrixChart
                data={chartData}
                seriesALabel="Resolved same-day"
                seriesBLabel="Still in flight"
                highlightIndex={highlightIndex}
                ariaLabel="Case volume over the last 14 days"
              />
            </div>
          </Card>

          <Card {...queueAssistance} padding="none">
            <div className="border-b border-[var(--color-border)] p-6">
              <h2 className="font-display text-xl font-bold">Case work queue</h2>
              <p className="mt-1 text-sm text-[var(--color-muted)]">Status, ownership age and safe next action are sourced from the API.</p>
              <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-5" aria-label="Saved work queue filters">
                <Select aria-label="Case type" value={filters.caseType} onChange={(event) => setFilters((current) => ({ ...current, caseType: event.target.value }))}>
                  <option value="">All case types</option>
                  <option value="VENDOR_ONBOARDING">Supplier onboarding</option>
                  <option value="INVOICE_EXCEPTION">Invoice exception</option>
                </Select>
                <Select aria-label="Status" value={filters.status} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}>
                  <option value="">All statuses</option>
                  <option value="NEEDS_CLARIFICATION">Needs clarification</option>
                  <option value="DUPLICATE_REVIEW">Duplicate review</option>
                  <option value="RISK_REVIEW">Risk review</option>
                  <option value="APPROVAL_PENDING">Approval pending</option>
                  <option value="ERP_SYNC_FAILED">ERP retry</option>
                  <option value="COMPLETED">Completed</option>
                </Select>
                <Select aria-label="Priority" value={filters.priority} onChange={(event) => setFilters((current) => ({ ...current, priority: event.target.value }))}>
                  <option value="">All priorities</option>
                  <option value="URGENT">Urgent</option>
                  <option value="HIGH">High</option>
                  <option value="NORMAL">Normal</option>
                  <option value="LOW">Low</option>
                </Select>
                <Select aria-label="Ownership" value={filters.ownership} onChange={(event) => setFilters((current) => ({ ...current, ownership: event.target.value }))}>
                  <option value="ALL">All ownership</option>
                  <option value="MINE">Mine</option>
                  <option value="UNCLAIMED">Unclaimed</option>
                </Select>
                <Button type="button" variant="ghost" onClick={() => setFilters(defaultFilters)}>
                  Reset saved view
                </Button>
              </div>
            </div>
            <div className="divide-y divide-[var(--color-border)]">
              {cases.isLoading && <p className="p-6" aria-live="polite">Loading live cases…</p>}
              {!cases.isLoading && filtered.length === 0 && <p className="p-6 text-[var(--color-muted)]">No supplier cases match this view.</p>}
              {filtered.map((item: WorkQueueItem) => (
                <Link key={item.case_id} href={`/cases/${item.case_id}`} className="grid gap-3 p-6 transition-colors hover:bg-[var(--color-surface-muted)] md:grid-cols-[1.3fr_1fr_auto] md:items-center">
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

        <div>
          <DockedAssistantCard />
        </div>
      </div>
    </div>
  );
}
