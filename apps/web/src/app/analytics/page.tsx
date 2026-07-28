"use client";

import { FormEvent, useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  Bot,
  CheckCircle2,
  Clock3,
  Gauge,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, type MetricKey, type MetricValue } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const metricIcons: Record<MetricKey, typeof Gauge> = {
  invoice_stp_rate: Gauge,
  invoice_cycle_hours: Clock3,
  vendor_onboarding_cycle_hours: Activity,
  vendor_activation_rate: CheckCircle2,
  invoice_exception_rate: AlertTriangle,
  pending_approval_count: ShieldAlert,
};

function metricDisplay(metric: MetricValue): string {
  if (metric.value === null) return "—";
  if (metric.unit === "percent") return `${metric.value.toFixed(1)}%`;
  if (metric.unit === "hours") return `${metric.value.toFixed(1)}h`;
  return metric.value.toFixed(0);
}

function changeDisplay(metric: MetricValue): string {
  if (metric.value === null || metric.previous_value === null) {
    return "No comparable prior period";
  }
  const delta = metric.value - metric.previous_value;
  return `${delta >= 0 ? "+" : ""}${delta.toFixed(1)} vs prior period`;
}

export default function AnalyticsPage() {
  const queryClient = useQueryClient();
  const [question, setQuestion] = useState("");
  const summary = useQuery({
    queryKey: ["analytics", "summary"],
    queryFn: api.getAnalyticsSummary,
  });
  const trend = useQuery({
    queryKey: ["analytics", "series", "invoice_stp_rate"],
    queryFn: () => api.getMetricSeries("invoice_stp_rate"),
  });
  const exceptions = useQuery({
    queryKey: ["analytics", "exceptions"],
    queryFn: api.getExceptionAnalytics,
  });
  const findings = useQuery({
    queryKey: ["risk-findings"],
    queryFn: api.listRiskFindings,
  });
  const alerts = useQuery({
    queryKey: ["alerts"],
    queryFn: api.listAlerts,
  });
  const acknowledge = useMutation({
    mutationFn: api.acknowledgeAlert,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts"] }),
  });
  const ask = useMutation({ mutationFn: api.askAnalytics });

  const trendData = useMemo(
    () =>
      (trend.data?.points ?? []).map((point) => ({
        period: new Date(point.period_start).toLocaleDateString(undefined, {
          month: "short",
          day: "numeric",
        }),
        value: point.value,
      })),
    [trend.data],
  );
  const exceptionData = useMemo(
    () =>
      (exceptions.data?.items ?? []).map((item) => ({
        name: item.exception_type.replaceAll("_", " "),
        total: item.count,
        open: item.open_count,
      })),
    [exceptions.data],
  );
  const error = summary.error ?? trend.error ?? exceptions.error;

  const submitQuestion = (event: FormEvent) => {
    event.preventDefault();
    const normalized = question.trim();
    if (normalized) ask.mutate(normalized);
  };

  return (
    <div className="min-h-full p-6 lg:p-12">
      <header className="mb-10 flex flex-col justify-between gap-5 xl:flex-row xl:items-end">
        <div>
          <p className="mb-2 text-sm font-bold uppercase tracking-[0.2em] text-[var(--color-accent)]">
            Event-derived reporting
          </p>
          <h1 className="font-display text-3xl font-bold">
            Fraud and operational analytics
          </h1>
          <p className="mt-2 max-w-3xl text-[var(--color-muted)]">
            Tenant-scoped metrics come from immutable workflow events. Active
            controls can hold work; shadow anomaly models can only recommend
            review.
          </p>
        </div>
        <div className="rounded-xl px-4 py-2 text-sm shadow-[var(--shadow-inset-sm)]">
          {summary.data
            ? `${new Date(summary.data.period_start).toLocaleDateString()} – ${new Date(summary.data.period_end).toLocaleDateString()}`
            : "Loading reporting period…"}
        </div>
      </header>

      {error && (
        <p role="alert" className="mb-6 rounded-xl bg-red-50 p-4 text-red-900">
          Unable to load analytics: {error.message}
        </p>
      )}

      <section className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
        {(summary.data?.metrics ?? []).map((metric) => {
          const Icon = metricIcons[metric.key];
          return (
            <Card key={metric.key} className="p-6">
              <div className="mb-4 flex items-center justify-between">
                <Icon className="h-6 w-6 text-[var(--color-accent)]" />
                <span className="text-xs font-bold uppercase text-[var(--color-muted)]">
                  {metric.numerator ?? "—"}
                  {metric.denominator !== null
                    ? ` / ${metric.denominator}`
                    : ""}
                </span>
              </div>
              <p className="text-sm font-bold text-[var(--color-muted)]">
                {metric.label}
              </p>
              <p className="my-1 text-4xl font-extrabold">
                {metricDisplay(metric)}
              </p>
              <p className="text-xs text-[var(--color-muted)]">
                {changeDisplay(metric)}
              </p>
              {metric.statistics.median !== undefined && (
                <p className="mt-3 text-xs">
                  Median {metric.statistics.median ?? "—"}h · P90{" "}
                  {metric.statistics.p90 ?? "—"}h
                </p>
              )}
              <details className="mt-4 text-xs text-[var(--color-muted)]">
                <summary className="cursor-pointer font-bold">
                  Metric definition
                </summary>
                <p className="mt-2 leading-5">{metric.definition}</p>
              </details>
            </Card>
          );
        })}
      </section>

      <section className="mt-8 grid gap-8 xl:grid-cols-2">
        <Card>
          <h2 className="font-display text-xl font-bold">Invoice STP trend</h2>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            Completed without a human touch after submission.
          </p>
          <div className="mt-6 h-72" aria-label="Invoice STP trend chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trendData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" />
                <XAxis dataKey="period" tick={{ fontSize: 12 }} />
                <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 12 }} />
                <Tooltip />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="#6C63FF"
                  strokeWidth={3}
                  connectNulls
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card>
          <h2 className="font-display text-xl font-bold">
            Exception distribution
          </h2>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            Persisted deterministic exception records, not model guesses.
          </p>
          <div className="mt-6 h-72" aria-label="Exception distribution chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={exceptionData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" />
                <XAxis type="number" allowDecimals={false} />
                <YAxis
                  dataKey="name"
                  type="category"
                  width={120}
                  tick={{ fontSize: 10 }}
                />
                <Tooltip />
                <Bar dataKey="total" fill="#6C63FF" radius={[0, 6, 6, 0]} />
                <Bar dataKey="open" fill="#f59e0b" radius={[0, 6, 6, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </section>

      <section className="mt-8 grid gap-8 xl:grid-cols-[1.2fr_1fr]">
        <Card>
          <div className="mb-5 flex items-center gap-3">
            <ShieldAlert className="h-6 w-6 text-[var(--color-accent)]" />
            <div>
              <h2 className="font-display text-xl font-bold">Risk findings</h2>
              <p className="text-sm text-[var(--color-muted)]">
                Active controls and explicitly labelled shadow scores.
              </p>
            </div>
          </div>
          <div className="space-y-3">
            {(findings.data ?? []).slice(0, 8).map((finding) => (
              <div
                key={finding.risk_finding_id}
                className="rounded-xl p-4 shadow-[var(--shadow-inset-sm)]"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-bold">
                    {finding.finding_type.replaceAll("_", " ")}
                  </span>
                  <span
                    className={`rounded-full px-2 py-1 text-[10px] font-bold ${
                      finding.mode === "SHADOW"
                        ? "bg-violet-100 text-violet-900"
                        : "bg-red-100 text-red-900"
                    }`}
                  >
                    {finding.mode}
                  </span>
                  <span className="rounded-full bg-slate-200 px-2 py-1 text-[10px] font-bold">
                    {finding.severity}
                  </span>
                </div>
                <p className="mt-2 text-sm text-[var(--color-muted)]">
                  {finding.explanation.summary ?? finding.detector_key}
                </p>
                <div className="mt-3 flex justify-between text-xs">
                  <span>
                    Score {finding.score ?? "—"} · threshold{" "}
                    {finding.threshold ?? "—"}
                  </span>
                  {finding.case_id && (
                    <Link
                      className="font-bold text-[var(--color-accent)]"
                      href={`/cases/${finding.case_id}`}
                    >
                      Open case
                    </Link>
                  )}
                </div>
              </div>
            ))}
            {!findings.isLoading && (findings.data ?? []).length === 0 && (
              <p className="text-sm text-[var(--color-muted)]">
                No risk findings in this tenant.
              </p>
            )}
          </div>
        </Card>

        <Card>
          <div className="mb-5 flex items-center gap-3">
            <AlertTriangle className="h-6 w-6 text-amber-600" />
            <div>
              <h2 className="font-display text-xl font-bold">
                Operational alerts
              </h2>
              <p className="text-sm text-[var(--color-muted)]">
                Deduplicated SLA and control notifications.
              </p>
            </div>
          </div>
          <div className="space-y-3">
            {(alerts.data ?? []).slice(0, 8).map((alert) => (
              <div
                key={alert.alert_instance_id}
                className="rounded-xl p-4 shadow-[var(--shadow-inset-sm)]"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-bold">{alert.title}</p>
                    <p className="mt-1 text-xs text-[var(--color-muted)]">
                      {alert.body}
                    </p>
                  </div>
                  <span className="text-[10px] font-bold">{alert.severity}</span>
                </div>
                {alert.status === "OPEN" ? (
                  <Button
                    className="mt-3"
                    onClick={() =>
                      acknowledge.mutate(alert.alert_instance_id)
                    }
                    disabled={acknowledge.isPending}
                  >
                    Acknowledge
                  </Button>
                ) : (
                  <p className="mt-3 text-xs font-bold text-emerald-700">
                    {alert.status}
                  </p>
                )}
              </div>
            ))}
            {!alerts.isLoading && (alerts.data ?? []).length === 0 && (
              <p className="text-sm text-[var(--color-muted)]">
                No alert instances. Rules are evaluated by the scheduled alert
                worker.
              </p>
            )}
          </div>
        </Card>
      </section>

      <Card className="mt-8">
        <div className="flex items-center gap-3">
          <Bot className="h-6 w-6 text-[var(--color-accent)]" />
          <div>
            <h2 className="font-display text-xl font-bold">
              Ask governed analytics
            </h2>
            <p className="text-sm text-[var(--color-muted)]">
              Questions compile to an allowlisted metric query. Free-form SQL
              is never generated or executed.
            </p>
          </div>
        </div>
        <form
          className="mt-5 flex flex-col gap-3 sm:flex-row"
          onSubmit={submitQuestion}
        >
          <Input
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="What is our invoice STP rate this month?"
            aria-label="Analytics question"
          />
          <Button variant="primary" type="submit" disabled={ask.isPending}>
            <Sparkles className="mr-2 h-4 w-4" />
            {ask.isPending ? "Calculating…" : "Ask"}
          </Button>
        </form>
        {ask.isError && (
          <p role="alert" className="mt-4 text-sm text-red-800">
            This question is outside the governed metric catalogue.
          </p>
        )}
        {ask.data && (
          <div className="mt-5 rounded-xl p-5 shadow-[var(--shadow-inset-sm)]">
            <p className="text-lg font-bold">{ask.data.answer}</p>
            <p className="mt-2 text-xs text-[var(--color-muted)]">
              {ask.data.metric.definition}
            </p>
            <p className="mt-2 text-xs font-bold uppercase tracking-wide text-violet-700">
              {ask.data.provider.replaceAll("_", " ")}
            </p>
          </div>
        )}
      </Card>
    </div>
  );
}
