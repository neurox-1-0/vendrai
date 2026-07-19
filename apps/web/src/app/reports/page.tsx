"use client";

import { useQuery } from "@tanstack/react-query";
import { Download, FileJson2, Sheet } from "lucide-react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

function download(name: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function ReportsPage() {
  const cases = useQuery({ queryKey: ["cases"], queryFn: api.listCases });
  const rows = cases.data?.items ?? [];
  const exportJson = () => download(`neurox-cases-${new Date().toISOString().slice(0, 10)}.json`, JSON.stringify(rows, null, 2), "application/json");
  const exportCsv = () => {
    const escape = (value: unknown) => `"${String(value).replaceAll('"', '""')}"`;
    const header = ["case_number", "title", "status", "priority", "current_version", "created_at", "updated_at"];
    const csv = [header.join(","), ...rows.map((item) => header.map((key) => escape(item[key as keyof typeof item])).join(","))].join("\n");
    download(`neurox-cases-${new Date().toISOString().slice(0, 10)}.csv`, csv, "text/csv;charset=utf-8");
  };
  return (
    <div className="min-h-full p-6 lg:p-12">
      <header className="mb-10"><p className="mb-2 text-sm font-bold uppercase tracking-[0.2em] text-[var(--color-accent)]">Controlled export</p><h1 className="font-display text-3xl font-bold">Operational reports</h1><p className="mt-2 text-[var(--color-muted)]">Exports contain only the case summary fields currently authorized in this view.</p></header>
      {cases.isError && <p role="alert" className="mb-6 rounded-xl bg-red-50 p-4 text-red-900">Unable to prepare reports: {cases.error.message}</p>}
      <div className="grid max-w-4xl gap-8 md:grid-cols-2">
        <Card>
          <Sheet className="mb-5 h-8 w-8 text-emerald-700" />
          <h2 className="font-display text-xl font-bold">Case register (CSV)</h2>
          <p className="my-4 text-sm text-[var(--color-muted)]">A spreadsheet-ready register of {rows.length} current supplier cases. Sensitive extracted fields and documents are excluded.</p>
          <Button type="button" variant="primary" className="gap-2" disabled={cases.isLoading} onClick={exportCsv}><Download className="h-4 w-4" />Download CSV</Button>
        </Card>
        <Card>
          <FileJson2 className="mb-5 h-8 w-8 text-[var(--color-accent)]" />
          <h2 className="font-display text-xl font-bold">Case register (JSON)</h2>
          <p className="my-4 text-sm text-[var(--color-muted)]">Machine-readable case summaries for controlled downstream analysis. Audit chains require the dedicated auditor API.</p>
          <Button type="button" variant="primary" className="gap-2" disabled={cases.isLoading} onClick={exportJson}><Download className="h-4 w-4" />Download JSON</Button>
        </Card>
      </div>
    </div>
  );
}
