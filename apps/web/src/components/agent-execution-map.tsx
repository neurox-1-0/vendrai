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
  SUCCESS: "border-emerald-300 bg-emerald-50 text-emerald-950",
  COMPLETED: "border-emerald-300 bg-emerald-50 text-emerald-950",
  RUNNING: "border-violet-300 bg-violet-50 text-violet-950",
  QUEUED: "border-slate-300 bg-slate-50 text-slate-800",
  PARTIAL: "border-amber-300 bg-amber-50 text-amber-950",
  RETRYING: "border-amber-300 bg-amber-50 text-amber-950",
  INTERRUPTED: "border-blue-300 bg-blue-50 text-blue-950",
  BLOCKED: "border-red-300 bg-red-50 text-red-950",
  FAILED: "border-red-300 bg-red-50 text-red-950",
};

function formatDuration(value: number | null): string {
  if (value === null) return "—";
  if (value < 1_000) return `${value} ms`;
  if (value < 60_000) return `${(value / 1_000).toFixed(value < 10_000 ? 1 : 0)} s`;
  return `${Math.floor(value / 60_000)}m ${Math.round((value % 60_000) / 1_000)}s`;
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
  return (
    <article className={`rounded-2xl border p-4 ${style}`}>
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
              {step.input_summary.projection === "LIVE" && (
                <span className="rounded-full border border-current/25 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider">
                  Live
                </span>
              )}
            </span>
            <span className="mt-1 block text-xs opacity-75">
              {step.status.replaceAll("_", " ")} · attempt {step.attempt} · {formatDuration(step.latency_ms)}
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
          <details className="mt-3">
            <summary className="cursor-pointer font-bold">Structured output</summary>
            <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-xl bg-slate-950 p-3 text-xs text-slate-100">
              {JSON.stringify(step.output_summary, null, 2)}
            </pre>
          </details>
        </div>
      )}
    </article>
  );
}

export function AgentExecutionMap({ runId }: { runId: string }) {
  const { roles } = useAuth();
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
      <Card data-tour-id="case.agent-map" aria-live="polite">
        <div className="h-40 animate-pulse rounded-2xl bg-slate-200" />
      </Card>
    );
  }
  if (graph.isError || !graph.data) {
    return (
      <Card data-tour-id="case.agent-map">
        <p role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">
          Execution data is temporarily unavailable: {graph.error?.message}
        </p>
      </Card>
    );
  }

  const data = graph.data;
  return (
    <>
      <Card data-tour-id="case.agent-map" className="overflow-hidden">
        <header className="flex flex-col justify-between gap-5 lg:flex-row lg:items-start">
          <div>
            <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.18em] text-violet-700">
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
            <div key={String(label)} className="rounded-2xl bg-white/50 p-4 shadow-[var(--shadow-inset-sm)]">
              <dt className="text-xs font-bold uppercase tracking-wider text-[var(--color-muted)]">{label}</dt>
              <dd className="mt-2 flex items-center gap-2 text-xl font-bold">
                <Clock3 className="h-4 w-4 text-violet-600" aria-hidden="true" />
                {formatDuration(value as number | null)}
              </dd>
            </div>
          ))}
        </dl>

        {lanes.length > 0 ? (
          <div className="mt-8 space-y-5">
            {lanes.map(([kind, steps]) => {
              const LaneIcon = KIND_ICONS[kind];
              return (
                <section key={kind} aria-labelledby={`agent-lane-${kind}`}>
                  <div className="mb-3 flex items-center gap-2">
                    <LaneIcon className="h-5 w-5 text-violet-700" aria-hidden="true" />
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
          <div className="mt-8 rounded-2xl border border-dashed border-slate-300 p-8 text-center">
            <CircleDashed className="mx-auto h-8 w-8 text-violet-600" aria-hidden="true" />
            <p className="mt-3 font-bold">The run is waiting for its first persisted agent step.</p>
            <p className="mt-1 text-sm text-[var(--color-muted)]">Document processing and queue events remain visible below.</p>
          </div>
        )}
      </Card>

      {diagnosticsOpen && (
        <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/55" role="presentation">
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="run-diagnostics-title"
            className="h-full w-full max-w-2xl overflow-y-auto bg-slate-950 p-6 text-slate-100 shadow-2xl lg:p-8"
          >
            <header className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.18em] text-cyan-300">Judge-safe diagnostics</p>
                <h2 id="run-diagnostics-title" className="mt-2 text-2xl font-bold">Run inspection</h2>
                <p className="mt-2 text-sm text-slate-300">Sanitized versions, integrity controls, route, and tool outputs. No secrets, PII, or private reasoning.</p>
              </div>
              <Button type="button" variant="icon" aria-label="Close diagnostics" onClick={() => setDiagnosticsOpen(false)}>
                <X className="h-5 w-5" />
              </Button>
            </header>
            {diagnostics.isLoading && <p className="mt-8" aria-live="polite">Loading sanitized diagnostics…</p>}
            {diagnostics.isError && <p className="mt-8 text-red-300" role="alert">{diagnostics.error.message}</p>}
            {diagnostics.data && (
              <div className="mt-8 space-y-6">
                <section>
                  <h3 className="font-bold text-cyan-300">Versions</h3>
                  <pre className="mt-2 overflow-auto rounded-2xl bg-white/5 p-4 text-xs">{JSON.stringify(diagnostics.data.versions, null, 2)}</pre>
                </section>
                <section>
                  <h3 className="font-bold text-cyan-300">Integrity</h3>
                  <pre className="mt-2 overflow-auto rounded-2xl bg-white/5 p-4 text-xs">{JSON.stringify(diagnostics.data.integrity, null, 2)}</pre>
                </section>
                <section>
                  <h3 className="font-bold text-cyan-300">Decision summary</h3>
                  <pre className="mt-2 overflow-auto rounded-2xl bg-white/5 p-4 text-xs">{JSON.stringify(diagnostics.data.decision_summary, null, 2)}</pre>
                </section>
              </div>
            )}
          </section>
        </div>
      )}
    </>
  );
}
