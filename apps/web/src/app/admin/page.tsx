"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Activity, DatabaseBackup, RefreshCw, ShieldCheck } from "lucide-react";
import {
  useIntegrationHealthApiV1AdminIntegrationsHealthGet,
  useListSanctionsDatasetsApiV1AdminSanctionsDatasetsGet,
} from "@/generated/neurox";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

export default function AdminIntegrations() {
  const queryClient = useQueryClient();
  const health = useIntegrationHealthApiV1AdminIntegrationsHealthGet({
    query: { refetchInterval: 15_000 },
  });
  const datasets = useListSanctionsDatasetsApiV1AdminSanctionsDatasetsGet();
  const refresh = useMutation({
    mutationFn: api.requestSanctionsImport,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["/api/v1/admin/sanctions-datasets"] }),
        queryClient.invalidateQueries({ queryKey: ["/api/v1/admin/integrations/health"] }),
      ]);
    },
  });

  return (
    <div className="min-h-full p-6 lg:p-12">
      <header className="mb-10">
        <p className="mb-2 text-sm font-bold uppercase tracking-[0.2em] text-[var(--color-accent)]">
          Administrator control plane
        </p>
        <h1 className="font-display text-3xl font-bold">Integration health</h1>
        <p className="mt-2 text-[var(--color-muted)]">
          Credential-free readiness, retry guidance, and sanctions provenance.
        </p>
      </header>
      {health.isError && (
        <p role="alert" className="mb-6 rounded-xl bg-red-50 p-4 text-red-900">
          Health data is unavailable or your role is not authorized.
        </p>
      )}
      <section className="grid gap-5 md:grid-cols-2 xl:grid-cols-3" aria-label="Integration status">
        {Object.entries(health.data?.checks ?? {}).map(([name, check]) => (
          <Card key={name} className="p-6">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <Activity className="h-5 w-5 text-[var(--color-accent)]" />
                <h2 className="font-bold">{name.replaceAll("_", " ")}</h2>
              </div>
              <span className={`rounded-full px-3 py-1 text-xs font-bold ${
                check.status === "HEALTHY" || check.status === "DISABLED"
                  ? "bg-emerald-100 text-emerald-900"
                  : check.status === "DEGRADED"
                    ? "bg-amber-100 text-amber-900"
                    : "bg-red-100 text-red-900"
              }`}>
                {check.status}
              </span>
            </div>
            {check.error_code && <p className="mt-3 text-sm font-bold">{check.error_code}</p>}
            {check.action && <p className="mt-2 text-sm text-[var(--color-muted)]">{check.action}</p>}
            {Object.keys(check.metadata ?? {}).length > 0 && (
              <pre className="mt-3 overflow-auto whitespace-pre-wrap text-xs text-[var(--color-muted)]">
                {JSON.stringify(check.metadata, null, 2)}
              </pre>
            )}
          </Card>
        ))}
      </section>

      <Card className="mt-8">
        <div className="mb-6 flex flex-col justify-between gap-4 md:flex-row md:items-center">
          <div className="flex items-center gap-3">
            <ShieldCheck className="h-6 w-6 text-[var(--color-accent)]" />
            <div>
              <h2 className="font-display text-xl font-bold">Official sanctions datasets</h2>
              <p className="text-sm text-[var(--color-muted)]">
                Cases fail closed unless OFAC, UN, and EU are all current.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {(["OFAC", "UN", "EU"] as const).map((source) => (
              <Button
                key={source}
                type="button"
                variant="secondary"
                className="gap-2"
                disabled={refresh.isPending}
                onClick={() => refresh.mutate(source)}
              >
                <RefreshCw className="h-4 w-4" /> Refresh {source}
              </Button>
            ))}
          </div>
        </div>
        {refresh.isError && (
          <p role="alert" className="mb-5 rounded-xl bg-red-50 p-3 text-sm text-red-900">
            Refresh request failed: {refresh.error.message}
          </p>
        )}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-300">
                <th className="p-3">Source</th>
                <th className="p-3">Version</th>
                <th className="p-3">Published</th>
                <th className="p-3">Status</th>
                <th className="p-3">SHA-256</th>
              </tr>
            </thead>
            <tbody>
              {(datasets.data ?? []).map((dataset) => (
                <tr key={dataset.dataset_id} className="border-b border-slate-200">
                  <td className="p-3 font-bold">{dataset.source}</td>
                  <td className="p-3">{dataset.version}</td>
                  <td className="p-3">{dataset.published_at ? new Date(dataset.published_at).toLocaleString() : "Not published"}</td>
                  <td className="p-3">{dataset.status}</td>
                  <td className="p-3 font-mono text-xs">{dataset.sha256.slice(0, 16)}…</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!datasets.isLoading && (datasets.data ?? []).length === 0 && (
            <div className="flex items-center gap-3 p-5 text-sm text-[var(--color-muted)]">
              <DatabaseBackup className="h-5 w-5" /> No official datasets have been published.
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
