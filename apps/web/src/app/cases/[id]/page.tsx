"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, FileSearch, ShieldAlert, XCircle } from "lucide-react";
import { api, type ApprovalTask } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { JsonViewer } from "@/components/ui/json-viewer";
import { Table, Thead, Th, Tr, Td } from "@/components/ui/table";
import { StatusChip } from "@/components/status-chip";
import { CaseClarification } from "@/components/case-clarification";
import { CaseDocumentReview } from "@/components/case-document-review";
import { AgentExecutionMap } from "@/components/agent-execution-map";
import { useAssistanceTarget } from "@/components/assistance-registry";

export default function CaseDetail() {
  const caseId = String(useParams().id);
  const queryClient = useQueryClient();
  const eventsAssistance = useAssistanceTarget({
    id: "case.events",
    title: "Observable workflow events",
    description:
      "Review durable, replayable workflow events and public reason codes without exposing private chain-of-thought.",
    tour: "case.review-tour",
    order: 40,
  });
  const evidenceAssistance = useAssistanceTarget({
    id: "case.evidence",
    title: "Evidence and explanations",
    description:
      "Inspect the evidence claims, source locations, confidence and deterministic reason codes supporting the proposed outcome.",
    tour: "case.review-tour",
    order: 50,
  });
  const decisionAssistance = useAssistanceTarget({
    id: "case.decision-control",
    title: "Human decision control",
    description:
      "Approve or reject only after reviewing the case version and evidence hash; stale or replayed decisions are rejected.",
    tour: "case.review-tour",
    order: 60,
  });
  const [comment, setComment] = useState("");
  const [decisionError, setDecisionError] = useState("");
  const caseQuery = useQuery({ queryKey: ["case", caseId], queryFn: () => api.getCase(caseId) });
  const events = useQuery({ queryKey: ["events", caseId], queryFn: () => api.getEvents(caseId) });
  const evidence = useQuery({ queryKey: ["evidence", caseId], queryFn: () => api.getEvidence(caseId) });
  const approvals = useQuery({ queryKey: ["approvals"], queryFn: api.listApprovals });
  const reviews = useQuery({ queryKey: ["reviews"], queryFn: api.listReviews });
  const task = useMemo(
    () => [...(reviews.data ?? []), ...(approvals.data ?? [])].find((item) => item.case_id === caseId),
    [approvals.data, caseId, reviews.data],
  );
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
      queryClient.invalidateQueries({ queryKey: ["reviews"] });
      queryClient.invalidateQueries({ queryKey: ["clarifications"] });
      queryClient.invalidateQueries({ queryKey: ["documents", caseId] });
      queryClient.invalidateQueries({ queryKey: ["run-graph", runId] });
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
        queryClient.invalidateQueries({ queryKey: ["reviews"] }),
      ]);
    },
    onError: (error) => setDecisionError(error.message),
  });
  const ownership = useMutation({
    mutationFn: (action: "claim" | "release") =>
      action === "claim"
        ? api.claimCase(caseId, caseQuery.data!.current_version)
        : api.releaseCase(caseId, caseQuery.data!.current_version),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["case", caseId] }),
        queryClient.invalidateQueries({ queryKey: ["events", caseId] }),
        queryClient.invalidateQueries({ queryKey: ["/api/v1/work-queue"] }),
      ]);
    },
  });

  if (caseQuery.isLoading) return <p className="p-12" aria-live="polite">Loading case…</p>;
  if (caseQuery.isError || !caseQuery.data) return <p className="p-12 text-rose-800" role="alert">Unable to load case: {caseQuery.error?.message}</p>;
  const currentCase = caseQuery.data;
  const duplicateCandidates = Array.isArray(task?.evidence_packet.duplicate_candidates)
    ? task.evidence_packet.duplicate_candidates as Array<Record<string, unknown>>
    : [];
  const riskPacket = task?.evidence_packet.risk;
  const sanctionsCandidates = riskPacket && typeof riskPacket === "object" && "candidates" in riskPacket && Array.isArray(riskPacket.candidates)
    ? riskPacket.candidates as Array<Record<string, unknown>>
    : [];
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
        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            variant="secondary"
            disabled={ownership.isPending}
            onClick={() => ownership.mutate(currentCase.assigned_user_id ? "release" : "claim")}
          >
            {currentCase.assigned_user_id ? "Release ownership" : "Claim case"}
          </Button>
          <StatusChip status={currentCase.status} />
        </div>
      </header>
      {ownership.isError && (
        <p role="alert" className="mb-6 rounded-xl bg-rose-50 p-3 text-sm text-rose-900">
          Ownership change failed: {ownership.error.message}
        </p>
      )}

      <div className="grid gap-8 xl:grid-cols-[1.25fr_1fr]">
        <div className="space-y-8">
          {runId && <AgentExecutionMap runId={runId} />}
          <CaseClarification caseId={caseId} caseVersion={currentCase.current_version} />
          <CaseDocumentReview caseId={caseId} caseVersion={currentCase.current_version} />
          <Card {...eventsAssistance}>
            <div className="mb-6 flex items-center gap-3"><FileSearch className="h-6 w-6 text-[var(--color-accent)]" /><h2 className="font-display text-xl font-bold">Observable workflow events</h2></div>
            <ol className="space-y-5">
              {(events.data ?? []).map((event) => (
                <li key={event.event_id} className="grid grid-cols-[auto_1fr] gap-4">
                  <div className="mt-1 h-3 w-3 rounded-full bg-[var(--color-accent)]" aria-hidden="true" />
                  <div>
                    <div className="flex flex-wrap items-center justify-between gap-2"><span className="font-bold">{event.event_type.replaceAll("_", " ")}</span><time className="text-xs text-[var(--color-muted)]">{new Date(event.created_at).toLocaleString()}</time></div>
                    {Object.keys(event.payload).length > 0 && <div className="mt-2"><JsonViewer data={event.payload} /></div>}
                  </div>
                </li>
              ))}
              {!events.isLoading && (events.data ?? []).length === 0 && <li className="text-sm text-[var(--color-muted)]">No workflow events have been recorded.</li>}
            </ol>
          </Card>
          <Card {...evidenceAssistance}>
            <div className="mb-6 flex items-center gap-3"><ShieldAlert className="h-6 w-6 text-[var(--color-accent)]" /><h2 className="font-display text-xl font-bold">Evidence and explanations</h2></div>
            <div className="space-y-4">
              {(evidence.data?.items ?? []).map((item) => (
                <article key={item.evidence_item_id} className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)] p-5">
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <span className="flex flex-wrap items-center gap-2">
                      <Badge tone="neutral">{item.reason_code}</Badge>
                      <Badge
                        tone={item.is_authoritative ? "positive" : "warning"}
                        className="cursor-default"
                      >
                        <span
                          title={
                            item.is_authoritative
                              ? "Read from an authoritative source."
                              : "Supplied by a party to this case, so it cannot verify itself."
                          }
                        >
                          {item.provenance_label}
                        </span>
                      </Badge>
                    </span>
                    {item.confidence !== null && <span className="text-xs text-[var(--color-muted)]">Confidence {(item.confidence * 100).toFixed(0)}%</span>}
                  </div>
                  <p className="text-sm">{item.claim}</p>
                  <p className="mt-2 text-xs text-[var(--color-muted)]">Source: {item.source_type}{item.source_id ? ` · ${item.source_id}` : ""}</p>
                  {!item.is_authoritative && (
                    <p className="mt-1 text-xs text-amber-800">
                      Self-asserted evidence. Independent verification is required before it can
                      support a control decision.
                    </p>
                  )}
                </article>
              ))}
              {!evidence.isLoading && (evidence.data?.items ?? []).length === 0 && <p className="text-sm text-[var(--color-muted)]">Evidence is not ready yet. The case will remain visibly blocked if a mandatory source is unavailable.</p>}
            </div>
          </Card>

          {currentCase.case_type === "INVOICE_EXCEPTION" && task?.evidence_packet && (
            <Card>
              <div className="mb-6 flex items-center gap-3"><FileSearch className="h-6 w-6 text-[var(--color-accent)]" /><h2 className="font-display text-xl font-bold">Invoice Analysis Details</h2></div>
              <div className="space-y-6">

                {Array.isArray(task.evidence_packet.exception) && task.evidence_packet.exception.length > 0 && (
                  <div>
                    <h3 className="mb-2 text-sm font-bold text-rose-700">Detected Exceptions</h3>
                    <ul className="space-y-2">
                      {task.evidence_packet.exception.map((exception, index) => (
                        <li key={`${exception.exception_type}-${index}`} className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm">
                          <span className="font-bold">{exception.exception_type}</span> ({exception.severity})
                          <p className="mt-1 text-xs">{exception.mismatch_details?.message}</p>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {!!task.evidence_packet.match_result && (
                  <div>
                    <h3 className="mb-2 text-sm font-bold">3-Way Match Result: {task.evidence_packet.match_result.match_status}</h3>
                    <p className="text-sm text-[var(--color-muted)]">Total Variance: {formatCurrency(task.evidence_packet.match_result.overall_variance_amount)} ({task.evidence_packet.match_result.overall_variance_pct?.toFixed(2)}%)</p>

                    <div className="mt-4 overflow-x-auto rounded-xl border border-[var(--color-border)]">
                      <Table>
                        <Thead>
                          <Tr>
                            <Th>Line</Th>
                            <Th>Description</Th>
                            <Th>Inv Qty</Th>
                            <Th>PO/GRN Qty</Th>
                            <Th>Inv Price</Th>
                            <Th>PO Price</Th>
                            <Th>Status</Th>
                          </Tr>
                        </Thead>
                        <tbody>
                          {(task.evidence_packet.match_result.line_matches || []).map((m, index) => (
                            <Tr key={`${m.invoice_line.line_number}-${index}`}>
                              <Td>{m.invoice_line?.line_number}</Td>
                              <Td>{m.invoice_line?.description}</Td>
                              <Td>{m.invoice_line?.quantity}</Td>
                              <Td>{m.grn_line?.quantity_received || m.po_line?.quantity || "-"}</Td>
                              <Td>{formatCurrency(m.invoice_line?.unit_price)}</Td>
                              <Td>{formatCurrency(m.po_line?.unit_price)}</Td>
                              <Td className="font-bold">{m.match_status}</Td>
                            </Tr>
                          ))}
                        </tbody>
                      </Table>
                    </div>
                  </div>
                )}

                {!!task.evidence_packet.tolerance && (
                  <div className="rounded-xl bg-[var(--color-surface-muted)] p-4">
                    <h3 className="mb-2 text-sm font-bold">Tolerance Check</h3>
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={task.evidence_packet.tolerance.within_tolerance ? "positive" : "negative"}>
                        {task.evidence_packet.tolerance.within_tolerance ? "Within tolerance" : "Exceeds tolerance"}
                      </Badge>
                      <span className="text-xs text-[var(--color-muted)]">
                        Threshold: {formatCurrency(task.evidence_packet.tolerance.threshold_amount)}, {task.evidence_packet.tolerance.threshold_pct}%
                      </span>
                    </div>
                  </div>
                )}
              </div>
            </Card>
          )}

          {(duplicateCandidates.length > 0 || sanctionsCandidates.length > 0) && (
            <Card>
              <div className="mb-5 flex items-center gap-3">
                <ShieldAlert className="h-6 w-6 text-[var(--color-accent)]" />
                <div>
                  <h2 className="font-display text-xl font-bold">Mandatory control review</h2>
                  <p className="text-sm text-[var(--color-muted)]">
                    Candidates are deterministic leads. A human must resolve them; Gemini cannot clear a match.
                  </p>
                </div>
              </div>
              <div className="grid gap-5 lg:grid-cols-2">
                {duplicateCandidates.map((candidate, index) => (
                  <article key={String(candidate.vendor_id ?? index)} className="rounded-xl border border-amber-200 bg-amber-50 p-4">
                    <p className="text-xs font-bold uppercase tracking-wider text-amber-900">Duplicate candidate</p>
                    <p className="mt-2 font-bold">{String(candidate.name ?? candidate.vendor_id ?? "Existing vendor")}</p>
                    <p className="mt-1 text-sm">Score {Math.round(Number(candidate.score ?? 0) * 100)}%</p>
                    <div className="mt-3"><JsonViewer data={candidate.signals ?? {}} /></div>
                  </article>
                ))}
                {sanctionsCandidates.map((candidate, index) => (
                  <article key={String(candidate.entity_id ?? index)} className="rounded-xl border border-rose-200 bg-rose-50 p-4">
                    <p className="text-xs font-bold uppercase tracking-wider text-rose-900">Sanctions candidate</p>
                    <p className="mt-2 font-bold">{String(candidate.matched_name ?? candidate.entity_id ?? "Listed entity")}</p>
                    <p className="mt-1 text-sm">{String(candidate.source ?? "Official list")} · version {String(candidate.version ?? "unknown")}</p>
                    <p className="mt-1 text-sm">Similarity {Math.round(Number(candidate.score ?? 0) * 100)}%</p>
                  </article>
                ))}
              </div>
              <p className="mt-5 rounded-xl bg-[var(--color-surface-muted)] p-3 text-sm">
                What resolves this: record an evidence-bound disposition on the pending {task?.task_type.replaceAll("_", " ").toLowerCase()} task. The next control is created only after this decision is committed.
              </p>
            </Card>
          )}
        </div>

        <aside className="space-y-8">
          <Card {...decisionAssistance}>
            <h2 className="font-display text-xl font-bold">Decision control</h2>
            {task ? (
              <>
                <p className="mt-2 text-sm text-[var(--color-muted)]">Review the evidence before acting. This decision is bound to case version {task.case_version} and hash:</p>
                <Badge tone="warning" className="mt-2">{task.task_type.replaceAll("_", " ")}</Badge>
                <code className="mt-4 block break-all rounded-xl bg-[var(--color-ink)] p-3 text-xs text-slate-200">{task.evidence_hash}</code>
                <label htmlFor="decision-comment" className="mb-2 mt-5 block text-sm font-bold">Decision comment</label>
                <textarea id="decision-comment" value={comment} onChange={(event) => setComment(event.target.value)} rows={4} className="w-full rounded-xl border border-[var(--color-border)] bg-white p-4 text-sm shadow-[var(--shadow-xs)] outline-none focus:border-[var(--color-accent)] focus:ring-2 focus:ring-[var(--color-accent)]/25" placeholder="Required when rejecting; recommended for approval" />
                {decisionError && <p role="alert" className="mt-3 rounded-xl bg-rose-50 p-3 text-sm text-rose-900">{decisionError}</p>}
                <div className="mt-5 grid gap-3 sm:grid-cols-2">
                  <Button type="button" variant="destructive" disabled={decide.isPending || !comment.trim()} onClick={() => decide.mutate({ task, decision: "REJECTED" })} className="gap-2"><XCircle className="h-4 w-4" />Reject</Button>
                  <Button type="button" variant="primary" disabled={decide.isPending} onClick={() => decide.mutate({ task, decision: "APPROVED" })} className="gap-2"><CheckCircle2 className="h-4 w-4" />Approve</Button>
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
