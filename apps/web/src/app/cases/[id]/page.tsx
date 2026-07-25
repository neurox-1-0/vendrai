"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, FileSearch, ShieldAlert, XCircle } from "lucide-react";
import { api, type ApprovalTask } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StatusChip } from "@/components/status-chip";

export default function CaseDetail() {
  const caseId = String(useParams().id);
  const queryClient = useQueryClient();
  const [comment, setComment] = useState("");
  const [decisionError, setDecisionError] = useState("");
  const caseQuery = useQuery({ queryKey: ["case", caseId], queryFn: () => api.getCase(caseId) });
  const events = useQuery({ queryKey: ["events", caseId], queryFn: () => api.getEvents(caseId) });
  const evidence = useQuery({ queryKey: ["evidence", caseId], queryFn: () => api.getEvidence(caseId) });
  const approvals = useQuery({ queryKey: ["approvals"], queryFn: api.listApprovals });
  const task = useMemo(() => (approvals.data ?? []).find((item) => item.case_id === caseId), [approvals.data, caseId]);
  const runId = useMemo(() => {
    const submitted = (events.data ?? []).find((event) => event.event_type === "CASE_SUBMITTED");
    return typeof submitted?.payload.run_id === "string" ? submitted.payload.run_id : null;
  }, [events.data]);
  useEffect(() => {
    if (!runId) return;
    const controller = new AbortController();
    api.subscribeRunEvents(runId, controller.signal, () => {
      queryClient.invalidateQueries({ queryKey: ["events", caseId] });
      queryClient.invalidateQueries({ queryKey: ["case", caseId] });
      queryClient.invalidateQueries({ queryKey: ["evidence", caseId] });
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
    }).catch((error) => {
      if (!controller.signal.aborted) console.error("SSE connection failed", error);
    });
    return () => controller.abort();
  }, [caseId, queryClient, runId]);
  const decide = useMutation({
    mutationFn: ({ task, decision }: { task: ApprovalTask; decision: "APPROVED" | "REJECTED" }) => api.decideApproval(task, decision, comment),
    onSuccess: async () => {
      setComment("");
      setDecisionError("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["case", caseId] }),
        queryClient.invalidateQueries({ queryKey: ["events", caseId] }),
        queryClient.invalidateQueries({ queryKey: ["approvals"] }),
      ]);
    },
    onError: (error) => setDecisionError(error.message),
  });

  if (caseQuery.isLoading) return <p className="p-12" aria-live="polite">Loading case…</p>;
  if (caseQuery.isError || !caseQuery.data) return <p className="p-12 text-red-800" role="alert">Unable to load case: {caseQuery.error?.message}</p>;
  const currentCase = caseQuery.data;
  const currencyCode = task?.evidence_packet.extracted_invoice?.currency || "USD";
  const formatCurrency = (amount: number | string | undefined | null) => {
    if (amount == null || amount === "-") return "-";
    const num = typeof amount === 'string' ? parseFloat(amount) : amount;
    if (isNaN(num)) return String(amount);
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: currencyCode }).format(num);
  };

  return (
    <div className="min-h-full p-6 lg:p-12">
      <header className="mb-10 flex flex-col justify-between gap-6 xl:flex-row xl:items-center">
        <div className="flex items-center gap-4">
          <Link href="/"><Button variant="icon" aria-label="Back to dashboard"><ArrowLeft className="h-5 w-5" /></Button></Link>
          <div>
            <p className="text-xs font-bold text-[var(--color-muted)]">{currentCase.case_number}</p>
            <h1 className="font-display text-3xl font-bold">{currentCase.title}</h1>
            <p className="mt-1 text-sm text-[var(--color-muted)]">Version {currentCase.current_version} · Updated {new Date(currentCase.updated_at).toLocaleString()}</p>
          </div>
        </div>
        <StatusChip status={currentCase.status} />
      </header>

      <div className="grid gap-8 xl:grid-cols-[1.25fr_1fr]">
        <div className="space-y-8">
          <Card>
            <div className="mb-6 flex items-center gap-3"><FileSearch className="h-6 w-6 text-[var(--color-accent)]" /><h2 className="font-display text-xl font-bold">Observable workflow events</h2></div>
            <ol className="space-y-5">
              {(events.data ?? []).map((event) => (
                <li key={event.event_id} className="grid grid-cols-[auto_1fr] gap-4">
                  <div className="mt-1 h-3 w-3 rounded-full bg-[var(--color-accent)]" aria-hidden="true" />
                  <div>
                    <div className="flex flex-wrap items-center justify-between gap-2"><span className="font-bold">{event.event_type.replaceAll("_", " ")}</span><time className="text-xs text-[var(--color-muted)]">{new Date(event.created_at).toLocaleString()}</time></div>
                    {Object.keys(event.payload).length > 0 && <pre className="mt-2 overflow-x-auto whitespace-pre-wrap rounded-xl bg-slate-900 p-3 text-xs text-slate-200">{JSON.stringify(event.payload, null, 2)}</pre>}
                  </div>
                </li>
              ))}
              {!events.isLoading && (events.data ?? []).length === 0 && <li className="text-sm text-[var(--color-muted)]">No workflow events have been recorded.</li>}
            </ol>
          </Card>
          <Card>
            <div className="mb-6 flex items-center gap-3"><ShieldAlert className="h-6 w-6 text-[var(--color-accent)]" /><h2 className="font-display text-xl font-bold">Evidence and explanations</h2></div>
            <div className="space-y-4">
              {(evidence.data?.items ?? []).map((item) => (
                <article key={item.evidence_item_id} className="rounded-2xl p-5 shadow-[var(--shadow-inset-sm)]">
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2"><span className="rounded-full bg-slate-200 px-3 py-1 text-xs font-bold">{item.reason_code}</span>{item.confidence !== null && <span className="text-xs text-[var(--color-muted)]">Confidence {(item.confidence * 100).toFixed(0)}%</span>}</div>
                  <p className="text-sm">{item.claim}</p>
                  <p className="mt-2 text-xs text-[var(--color-muted)]">Source: {item.source_type}{item.source_id ? ` · ${item.source_id}` : ""}</p>
                </article>
              ))}
              {!evidence.isLoading && (evidence.data?.items ?? []).length === 0 && <p className="text-sm text-[var(--color-muted)]">Evidence is not ready yet. The case will remain visibly blocked if a mandatory source is unavailable.</p>}
            </div>
          </Card>
          
          {currentCase.case_type === "INVOICE_EXCEPTION" && task?.evidence_packet && (
            <Card>
              <div className="mb-6 flex items-center gap-3"><FileSearch className="h-6 w-6 text-[var(--color-accent)]" /><h2 className="font-display text-xl font-bold">Invoice Analysis Details</h2></div>
              <div className="space-y-6">
                
                {/* Exceptions */}
                {Array.isArray(task.evidence_packet.exception) && task.evidence_packet.exception.length > 0 && (
                  <div>
                    <h3 className="font-bold text-sm mb-2 text-red-600">Detected Exceptions</h3>
                    <ul className="space-y-2">
                      {task.evidence_packet.exception.map((exception, index) => (
                        <li key={`${exception.exception_type}-${index}`} className="text-sm bg-red-50 p-3 rounded-lg border border-red-100">
                          <span className="font-bold">{exception.exception_type}</span> ({exception.severity})
                          <p className="text-xs mt-1">{exception.mismatch_details?.message}</p>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                
                {/* 3-Way Match Result */}
                {!!task.evidence_packet.match_result && (
                  <div>
                    <h3 className="font-bold text-sm mb-2">3-Way Match Result: {task.evidence_packet.match_result.match_status}</h3>
                    <p className="text-sm text-[var(--color-muted)]">Total Variance: {formatCurrency(task.evidence_packet.match_result.overall_variance_amount)} ({task.evidence_packet.match_result.overall_variance_pct?.toFixed(2)}%)</p>
                    
                    <div className="mt-4 overflow-x-auto">
                      <table className="w-full text-sm text-left">
                        <thead className="text-xs uppercase bg-slate-100">
                          <tr>
                            <th className="px-4 py-2">Line</th>
                            <th className="px-4 py-2">Description</th>
                            <th className="px-4 py-2">Inv Qty</th>
                            <th className="px-4 py-2">PO/GRN Qty</th>
                            <th className="px-4 py-2">Inv Price</th>
                            <th className="px-4 py-2">PO Price</th>
                            <th className="px-4 py-2">Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(task.evidence_packet.match_result.line_matches || []).map((m, index) => (
                            <tr key={`${m.invoice_line.line_number}-${index}`} className="border-b">
                              <td className="px-4 py-2">{m.invoice_line?.line_number}</td>
                              <td className="px-4 py-2">{m.invoice_line?.description}</td>
                              <td className="px-4 py-2">{m.invoice_line?.quantity}</td>
                              <td className="px-4 py-2">{m.grn_line?.quantity_received || m.po_line?.quantity || "-"}</td>
                              <td className="px-4 py-2">{formatCurrency(m.invoice_line?.unit_price)}</td>
                              <td className="px-4 py-2">{formatCurrency(m.po_line?.unit_price)}</td>
                              <td className="px-4 py-2 font-bold">{m.match_status}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
                
                {/* Tolerance Check */}
                {!!task.evidence_packet.tolerance && (
                  <div className="bg-slate-50 p-4 rounded-lg">
                    <h3 className="font-bold text-sm mb-1">Tolerance Check</h3>
                    <p className="text-sm">
                      {task.evidence_packet.tolerance.within_tolerance ? "✅ Within Tolerance" : "❌ Exceeds Tolerance"}
                      <span className="text-xs text-[var(--color-muted)] ml-2">
                        (Threshold: {formatCurrency(task.evidence_packet.tolerance.threshold_amount)}, {task.evidence_packet.tolerance.threshold_pct}%)
                      </span>
                    </p>
                  </div>
                )}
              </div>
            </Card>
          )}
        </div>

        <aside className="space-y-8">
          <Card>
            <h2 className="font-display text-xl font-bold">Decision control</h2>
            {task ? (
              <>
                <p className="mt-2 text-sm text-[var(--color-muted)]">Review the evidence before acting. This decision is bound to case version {task.case_version} and hash:</p>
                <code className="mt-4 block break-all rounded-xl bg-slate-900 p-3 text-xs text-slate-200">{task.evidence_hash}</code>
                <label htmlFor="decision-comment" className="mb-2 mt-5 block text-sm font-bold">Decision comment</label>
                <textarea id="decision-comment" value={comment} onChange={(event) => setComment(event.target.value)} rows={4} className="w-full rounded-2xl bg-transparent p-4 shadow-[var(--shadow-inset)] outline-none focus:ring-2 focus:ring-[var(--color-accent)]" placeholder="Required when rejecting; recommended for approval" />
                {decisionError && <p role="alert" className="mt-3 rounded-xl bg-red-50 p-3 text-sm text-red-900">{decisionError}</p>}
                <div className="mt-5 grid gap-3 sm:grid-cols-2">
                  <Button type="button" variant="secondary" disabled={decide.isPending || !comment.trim()} onClick={() => decide.mutate({ task, decision: "REJECTED" })} className="gap-2 text-red-700 disabled:opacity-50"><XCircle className="h-4 w-4" />Reject</Button>
                  <Button type="button" variant="primary" disabled={decide.isPending} onClick={() => decide.mutate({ task, decision: "APPROVED" })} className="gap-2 disabled:opacity-50"><CheckCircle2 className="h-4 w-4" />Approve</Button>
                </div>
              </>
            ) : <p className="mt-3 text-sm text-[var(--color-muted)]">There is no pending approval task for this case.</p>}
          </Card>
          <Card>
            <h2 className="font-bold">Safety semantics</h2>
            <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-[var(--color-muted)]"><li>No private chain-of-thought is displayed.</li><li>Sanctions candidates cannot be cleared by an LLM.</li><li>A stale case version invalidates this decision.</li><li>ERP creation requires an approved evidence hash.</li></ul>
          </Card>
        </aside>
      </div>
    </div>
  );
}
