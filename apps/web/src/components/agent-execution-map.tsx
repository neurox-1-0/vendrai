"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  Bot,
  BrainCircuit,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleDashed,
  Clock3,
  Gauge,
  GitBranch,
  ShieldCheck,
  TriangleAlert,
  UserRoundCheck,
  Workflow,
  X,
} from "lucide-react";

import { useAuth } from "@/app/providers";
import { api, type AgentStep } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { JsonViewer } from "@/components/ui/json-viewer";
import { useAssistanceTarget } from "@/components/assistance-registry";

const KIND_LABELS: Record<AgentStep["agent_kind"], string> = {
  PLANNER: "Planning",
  SPECIALIST: "Specialists",
  REASONING: "Reasoning",
  VERIFIER: "Verification",
  HUMAN: "Human control",
  EXECUTION: "Execution",
};

const KIND_ICONS = {
  PLANNER: GitBranch,
  SPECIALIST: Bot,
  REASONING: BrainCircuit,
  VERIFIER: ShieldCheck,
  HUMAN: UserRoundCheck,
  EXECUTION: Workflow,
};

const STATUS_STYLE: Record<string, string> = {
  SUCCESS: "border-emerald-200 bg-emerald-50 text-emerald-900",
  COMPLETED: "border-emerald-200 bg-emerald-50 text-emerald-900",
  RUNNING: "border-blue-200 bg-blue-50 text-blue-900",
  QUEUED: "border-[var(--color-border)] bg-[var(--color-surface-muted)] text-[var(--color-ink)]",
  PARTIAL: "border-amber-200 bg-amber-50 text-amber-900",
  RETRYING: "border-amber-200 bg-amber-50 text-amber-900",
  INTERRUPTED: "border-blue-200 bg-blue-50 text-blue-900",
  BLOCKED: "border-rose-200 bg-rose-50 text-rose-900",
  FAILED: "border-rose-200 bg-rose-50 text-rose-900",
};

function formatDuration(value: number | null): string {
  if (value === null) return "—";
  if (value < 1_000) return `${value} ms`;
  if (value < 60_000) return `${(value / 1_000).toFixed(value < 10_000 ? 1 : 0)} s`;
  return `${Math.floor(value / 60_000)}m ${Math.round((value % 60_000) / 1_000)}s`;
}

/**
 * Describe a step's timing without ever presenting a projection as a
 * measurement. A step still in flight has no measured latency to report, so it
 * says so rather than showing a number from the live-progress cache dressed in
 * the same styling as a committed one.
 */
function timingLabel(step: AgentStep): string {
  if (step.timing_source === "PROJECTED") {
    return step.latency_ms === null
      ? "in progress, not yet measured"
      : `${formatDuration(step.latency_ms)} elapsed so far (not yet measured)`;
  }
  return `${formatDuration(step.latency_ms)} measured`;
}

function StepStatusIcon({ status }: { status: string }) {
  const className = `mt-0.5 h-5 w-5 shrink-0 ${status === "RUNNING" ? "animate-pulse" : ""}`;
  if (status === "SUCCESS" || status === "COMPLETED") {
    return <CheckCircle2 className={className} aria-hidden="true" />;
  }
  if (status === "RUNNING" || status === "QUEUED") {
    return <CircleDashed className={className} aria-hidden="true" />;
  }
  return <TriangleAlert className={className} aria-hidden="true" />;
}

function StepCard({ step }: { step: AgentStep }) {
  const [expanded, setExpanded] = useState(false);
  const style = STATUS_STYLE[step.status] ?? STATUS_STYLE.QUEUED;
  const projected = step.timing_source === "PROJECTED";
  return (
    <article
      className={`rounded-2xl p-4 ${style} ${
        // A dashed edge distinguishes a projection at a glance, and the
        // accessible label carries the same information for anyone who cannot
        // see the border.
        projected ? "border border-dashed opacity-90" : "border"
      }`}
      aria-label={
        projected
          ? `${step.display_name}, in progress, timing not yet measured`
          : undefined
      }
    >
      <button
        type="button"
        className="flex w-full items-start justify-between gap-3 text-left"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
      >
        <span className="flex min-w-0 gap-3">
          <StepStatusIcon status={step.status} />
          <span className="min-w-0">
            <span className="flex items-center gap-2">
              <span className="block truncate font-bold">{step.display_name}</span>
              {projected && (
                <span className="rounded-full border border-dashed border-current/40 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider">
                  In progress
                </span>
              )}
            </span>
            <span className="mt-1 block text-xs opacity-75">
              {step.status.replaceAll("_", " ")} · attempt {step.attempt} · {timingLabel(step)}
            </span>
          </span>
        </span>
        {expanded ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
      </button>
      {expanded && (
        <div className="mt-4 border-t border-current/15 pt-4 text-sm">
          <p><span className="font-bold">Why selected:</span> {step.route_reason}</p>
          {step.dependencies.length > 0 && (
            <p className="mt-2">
              <span className="font-bold">Waited for:</span>{" "}
              {step.dependencies.map((item) => item.replaceAll("_", " ")).join(", ")}
            </p>
          )}
          {Object.keys(step.error).length > 0 && (
            <p className="mt-2">
              <span className="font-bold">Failure:</span>{" "}
              {String(step.error.error_code ?? "Structured error recorded")}
            </p>
          )}
          <div className="mt-3">
            <JsonViewer data={step.output_summary} title="Structured output" collapsed className="max-h-64" />
          </div>
        </div>
      )}
    </article>
  );
}

export function AgentExecutionMap({ runId }: { runId: string }) {
  const { roles } = useAuth();
  const assistance = useAssistanceTarget({
    id: "case.agent-map",
    title: "Agent execution map",
    description:
      "Inspect the selected agents, dependencies, live status, measured latency, critical path and parallel time saved.",
    tour: "case.review-tour",
    order: 10,
  });
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const graph = useQuery({
    queryKey: ["run-graph", runId],
    queryFn: () => api.getRunGraph(runId),
    refetchInterval: 2_000,
  });
  const diagnostics = useQuery({
    queryKey: ["run-diagnostics", runId],
    queryFn: () => api.getRunDiagnostics(runId),
    enabled: diagnosticsOpen && (roles.has("admin") || roles.has("auditor")),
  });
  const lanes = useMemo(() => {
    const grouped = new Map<AgentStep["agent_kind"], AgentStep[]>();
    for (const step of graph.data?.nodes ?? []) {
      grouped.set(step.agent_kind, [...(grouped.get(step.agent_kind) ?? []), step]);
    }
    return [...grouped.entries()];
  }, [graph.data?.nodes]);

  if (graph.isLoading) {
    return (
      <Card {...assistance} aria-live="polite">
        <div className="h-40 animate-pulse rounded-xl bg-[var(--color-surface-muted)]" />
      </Card>
    );
  }
  if (graph.isError || !graph.data) {
    return (
      <Card {...assistance}>
        <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">
          Execution data is temporarily unavailable: {graph.error?.message}
        </p>
      </Card>
    );
  }

  const data = graph.data;
  return (
    <>
      <Card {...assistance} className="overflow-hidden">
        <header className="flex flex-col justify-between gap-5 lg:flex-row lg:items-start">
          <div>
            <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.18em] text-[var(--color-accent)]">
              <Activity className="h-4 w-4" aria-hidden="true" />
              Live agent execution
            </p>
            <h2 className="mt-2 font-display text-2xl font-bold">{data.objective}</h2>
            <p className="mt-2 text-sm text-[var(--color-muted)]">
              Durable execution history plus short-lived live specialist progress. Expand a node to inspect its route and structured result.
            </p>
          </div>
          {(roles.has("admin") || roles.has("auditor")) && (
            <Button type="button" variant="secondary" className="gap-2" onClick={() => setDiagnosticsOpen(true)}>
              <Gauge className="h-4 w-4" aria-hidden="true" />
              Inspect run
            </Button>
          )}
        </header>

        <dl className="mt-7 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[
            ["Elapsed", data.timing.total_elapsed_ms],
            ["Agent compute", data.timing.active_compute_ms],
            ["Critical path", data.timing.critical_path_ms],
            ["Parallel time saved", data.timing.parallel_time_saved_ms],
          ].map(([label, value]) => (
            <div key={String(label)} className="rounded-xl bg-[var(--color-surface-muted)] p-4">
              <dt className="text-xs font-bold uppercase tracking-wider text-[var(--color-muted)]">{label}</dt>
              <dd className="mt-2 flex items-center gap-2 text-xl font-bold">
                <Clock3 className="h-4 w-4 text-[var(--color-accent)]" aria-hidden="true" />
                {formatDuration(value as number | null)}
              </dd>
            </div>
          ))}
        </dl>
        {data.timing.projected_step_count > 0 && (
          <p className="mt-3 text-xs text-[var(--color-muted)]">
            Measured from {data.nodes.length - data.timing.projected_step_count} completed step
            {data.nodes.length - data.timing.projected_step_count === 1 ? "" : "s"}.{" "}
            {data.timing.projected_step_count} step
            {data.timing.projected_step_count === 1 ? " is" : "s are"} still running and
            not counted here.
          </p>
        )}

        {lanes.length > 0 ? (
          <div className="mt-8 space-y-5">
            {lanes.map(([kind, steps]) => {
              const LaneIcon = KIND_ICONS[kind];
              return (
                <section key={kind} aria-labelledby={`agent-lane-${kind}`}>
                  <div className="mb-3 flex items-center gap-2">
                    <LaneIcon className="h-5 w-5 text-[var(--color-accent-dark)]" aria-hidden="true" />
                    <h3 id={`agent-lane-${kind}`} className="text-sm font-bold uppercase tracking-wider">
                      {KIND_LABELS[kind]}
                    </h3>
                    <span className="text-xs text-[var(--color-muted)]">{steps.length} step{steps.length === 1 ? "" : "s"}</span>
                  </div>
                  <div className="grid gap-3 lg:grid-cols-2">
                    {steps.map((step) => <StepCard key={step.step_id} step={step} />)}
                  </div>
                </section>
              );
            })}
          </div>
        ) : (
          <div className="mt-8 rounded-xl border border-dashed border-[var(--color-border-strong)] p-8 text-center">
            <CircleDashed className="mx-auto h-8 w-8 text-[var(--color-accent)]" aria-hidden="true" />
            <p className="mt-3 font-bold">The run is waiting for its first persisted agent step.</p>
            <p className="mt-1 text-sm text-[var(--color-muted)]">Document processing and queue events remain visible below.</p>
          </div>
        )}
      </Card>

      {diagnosticsOpen && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/55" role="presentation">
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="run-diagnostics-title"
            className="h-full w-full max-w-2xl overflow-y-auto bg-[var(--color-ink)] p-6 text-slate-100 shadow-[var(--shadow-lg)] lg:p-8"
          >
            <header className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.18em] text-blue-300">Judge-safe diagnostics</p>
                <h2 id="run-diagnostics-title" className="mt-2 text-2xl font-bold">Run inspection</h2>
                <p className="mt-2 text-sm text-slate-300">Sanitized versions, integrity controls, route, and tool outputs. No secrets, PII, or private reasoning.</p>
              </div>
              <Button type="button" variant="icon" aria-label="Close diagnostics" onClick={() => setDiagnosticsOpen(false)}>
                <X className="h-5 w-5" />
              </Button>
            </header>
            {diagnostics.isLoading && <p className="mt-8" aria-live="polite">Loading sanitized diagnostics…</p>}
            {diagnostics.isError && <p className="mt-8 text-rose-300" role="alert">{diagnostics.error.message}</p>}
            {diagnostics.data && (
              <div className="mt-8 space-y-6">
                <section>
                  <h3 className="font-bold text-blue-300">Versions</h3>
                  <pre className="mt-2 overflow-auto rounded-xl bg-white/5 p-4 text-xs">{JSON.stringify(diagnostics.data.versions, null, 2)}</pre>
                </section>
                <section>
                  <h3 className="font-bold text-blue-300">Integrity</h3>
                  <pre className="mt-2 overflow-auto rounded-xl bg-white/5 p-4 text-xs">{JSON.stringify(diagnostics.data.integrity, null, 2)}</pre>
                </section>
                <section>
                  <h3 className="font-bold text-blue-300">Decision summary</h3>
                  <pre className="mt-2 overflow-auto rounded-xl bg-white/5 p-4 text-xs">{JSON.stringify(diagnostics.data.decision_summary, null, 2)}</pre>
                </section>
              </div>
            )}
          </section>
        </div>
      )}
    </>
  );
}
