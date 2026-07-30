"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function ApprovalsDashboard() {
  const tasks = useQuery({ queryKey: ["approvals"], queryFn: api.listApprovals });
  return (
    <div className="min-h-full p-6 lg:p-12">
      <header className="mb-10">
        <p className="mb-1 text-sm font-bold text-[var(--color-accent)]">Human control point</p>
        <h1 className="font-display text-3xl font-bold">Approval queue</h1>
        <p className="mt-2 text-[var(--color-muted)]">Decisions are version-checked, evidence-bound and protected by segregation of duties.</p>
      </header>
      {tasks.isError && <p role="alert" className="mb-6 rounded-xl border border-rose-200 bg-rose-50 p-4 text-rose-900">Unable to load approvals: {tasks.error.message}</p>}
      <div className="grid gap-5 lg:grid-cols-2 xl:grid-cols-3">
        {tasks.isLoading && <p aria-live="polite">Loading approval tasks…</p>}
        {!tasks.isLoading && (tasks.data ?? []).length === 0 && (
          <Card className="lg:col-span-2 xl:col-span-3">
            <ShieldCheck className="mb-4 h-9 w-9 text-emerald-600" />
            <h2 className="font-bold">No pending decisions</h2>
            <p className="mt-2 text-sm text-[var(--color-muted)]">Cases will appear only after mandatory evidence checks complete.</p>
          </Card>
        )}
        {(tasks.data ?? []).map((task) => {
          const reasonCodes = Array.isArray(task.evidence_packet.reason_codes) ? task.evidence_packet.reason_codes.map(String) : [];
          return (
            <Link key={task.approval_task_id} href={`/cases/${task.case_id}`} className="block">
              <Card interactive className="flex h-full flex-col">
                <div className="mb-5 flex items-center justify-between">
                  <Badge tone="warning">Review required</Badge>
                  <span className="text-xs text-[var(--color-muted)]">v{task.case_version}</span>
                </div>
                <h2 className="font-display text-xl font-bold">{String(task.proposed_action.vendor_name ?? "Supplier approval")}</h2>
                <p className="mt-1 font-mono text-xs text-[var(--color-muted)]">{task.case_id}</p>
                <div className="my-6 flex-1 rounded-xl bg-[var(--color-surface-muted)] p-4">
                  <p className="text-xs font-bold uppercase tracking-wider text-[var(--color-muted)]">Reason codes</p>
                  <p className="mt-2 text-sm">{reasonCodes.length ? reasonCodes.join(" · ") : "Evidence packet ready for review"}</p>
                </div>
                <span className="inline-flex items-center gap-2 font-bold text-[var(--color-accent)]">
                  Review evidence <ArrowRight className="h-4 w-4" />
                </span>
              </Card>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
