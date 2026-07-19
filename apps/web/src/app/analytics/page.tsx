"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Clock3, Layers3 } from "lucide-react";
import { api, type CaseStatus } from "@/lib/api";
import { Card } from "@/components/ui/card";

export default function AnalyticsPage() {
  const cases = useQuery({ queryKey: ["cases"], queryFn: api.listCases });
  const metrics = useMemo(() => {
    const items = cases.data?.items ?? [];
    const counts = items.reduce<Record<string, number>>((acc, item) => ({ ...acc, [item.status]: (acc[item.status] ?? 0) + 1 }), {});
    const complete = items.filter((item) => item.status === "COMPLETED");
    const averageHours = complete.length
      ? complete.reduce((sum, item) => sum + (new Date(item.updated_at).getTime() - new Date(item.created_at).getTime()) / 3_600_000, 0) / complete.length
      : null;
    return { items, counts, complete, averageHours };
  }, [cases.data]);

  return (
    <div className="min-h-full p-6 lg:p-12">
      <header className="mb-10"><p className="mb-2 text-sm font-bold uppercase tracking-[0.2em] text-[var(--color-accent)]">Event-derived reporting</p><h1 className="font-display text-3xl font-bold">Operational analytics</h1><p className="mt-2 text-[var(--color-muted)]">Metrics are computed from live case records. No invented OCR accuracy or autonomous-action counts.</p></header>
      {cases.isError && <p role="alert" className="mb-6 rounded-xl bg-red-50 p-4 text-red-900">Unable to load analytics: {cases.error.message}</p>}
      <section className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "Total cases", value: metrics.items.length, icon: Layers3, note: "All supplier-onboarding cases" },
          { label: "Completed", value: metrics.complete.length, icon: CheckCircle2, note: "ERP-confirmed completion" },
          { label: "Pending review", value: metrics.counts.APPROVAL_PENDING ?? 0, icon: Clock3, note: "Human decisions outstanding" },
          { label: "Attention states", value: metrics.items.filter((item) => ["FAILED", "ERP_SYNC_FAILED", "VERIFICATION_FAILED", "RISK_REVIEW"].includes(item.status)).length, icon: AlertTriangle, note: "Visible recovery required" },
        ].map((item) => <Card key={item.label} className="p-6"><item.icon className="mb-4 h-6 w-6 text-[var(--color-accent)]" /><p className="text-sm font-bold text-[var(--color-muted)]">{item.label}</p><p className="my-1 text-4xl font-extrabold">{item.value}</p><p className="text-xs text-[var(--color-muted)]">{item.note}</p></Card>)}
      </section>
      <section className="mt-8 grid gap-8 xl:grid-cols-[1.4fr_1fr]">
        <Card>
          <h2 className="mb-6 font-display text-xl font-bold">Pipeline distribution</h2>
          <div className="space-y-4">
            {(Object.entries(metrics.counts) as [CaseStatus, number][]).sort((a, b) => b[1] - a[1]).map(([status, count]) => {
              const percent = metrics.items.length ? Math.round(count / metrics.items.length * 100) : 0;
              return <div key={status}><div className="mb-1 flex justify-between text-sm"><span className="font-bold">{status.replaceAll("_", " ")}</span><span>{count} · {percent}%</span></div><div className="h-3 rounded-full shadow-[var(--shadow-inset-sm)]"><div className="h-3 rounded-full bg-[var(--color-accent)]" style={{ width: `${percent}%` }} /></div></div>;
            })}
            {!cases.isLoading && metrics.items.length === 0 && <p className="text-sm text-[var(--color-muted)]">No case data is available yet.</p>}
          </div>
        </Card>
        <Card>
          <h2 className="font-display text-xl font-bold">Resolution time</h2>
          <p className="mt-8 text-5xl font-extrabold">{metrics.averageHours === null ? "—" : `${metrics.averageHours.toFixed(1)}h`}</p>
          <p className="mt-2 text-sm text-[var(--color-muted)]">Average elapsed time for ERP-confirmed cases. This value stays unavailable until real completions exist.</p>
        </Card>
      </section>
    </div>
  );
}
