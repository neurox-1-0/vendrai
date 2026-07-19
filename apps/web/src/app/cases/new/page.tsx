"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { FileCheck2, LockKeyhole, UploadCloud } from "lucide-react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function CaseIntake() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState<"LOW" | "NORMAL" | "HIGH" | "URGENT">("NORMAL");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!files.length) return setError("Add at least one PDF document.");
    setBusy(true);
    setError("");
    try {
      setProgress("Creating a tenant-scoped case…");
      const created = await api.createCase(title, priority);
      for (const [index, file] of files.entries()) {
        setProgress(`Uploading ${index + 1} of ${files.length}: ${file.name}`);
        const upload = await api.initiateUpload(created.case_id, file, "VENDOR_EVIDENCE");
        await api.uploadContent(upload, file);
        await api.completeUpload(upload.document_id);
      }
      setProgress("Queuing malware scan and document extraction…");
      await api.submitCase(created.case_id, created.current_version);
      router.push(`/cases/${created.case_id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to submit this case");
      setBusy(false);
    }
  }

  return (
    <div className="min-h-full p-6 lg:p-12">
      <header className="mb-10">
        <p className="mb-2 text-sm font-bold uppercase tracking-[0.2em] text-[var(--color-accent)]">Secure intake</p>
        <h1 className="font-display text-3xl font-bold">Start supplier onboarding</h1>
        <p className="mt-2 text-[var(--color-muted)]">Files enter quarantine first. They are scanned before extraction or agent analysis.</p>
      </header>
      <form onSubmit={submit} className="grid max-w-6xl gap-8 lg:grid-cols-[1.5fr_1fr]">
        <Card className="space-y-8">
          <div>
            <label htmlFor="title" className="mb-2 block text-sm font-bold">Supplier or request title</label>
            <Input id="title" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Example: Onboard Alpine Components GmbH" required minLength={3} />
          </div>
          <div>
            <label htmlFor="priority" className="mb-2 block text-sm font-bold">Priority</label>
            <select id="priority" value={priority} onChange={(event) => setPriority(event.target.value as typeof priority)} className="h-14 w-full rounded-2xl bg-transparent px-5 shadow-[var(--shadow-inset)] outline-none focus:ring-2 focus:ring-[var(--color-accent)]">
              <option>LOW</option><option>NORMAL</option><option>HIGH</option><option>URGENT</option>
            </select>
          </div>
          <div>
            <label htmlFor="documents" className="mb-2 block text-sm font-bold">Vendor documents</label>
            <label htmlFor="documents" className="flex cursor-pointer flex-col items-center rounded-3xl border-2 border-dashed border-[var(--color-accent)]/40 p-10 text-center focus-within:ring-2 focus-within:ring-[var(--color-accent)]">
              <UploadCloud className="mb-3 h-10 w-10 text-[var(--color-accent)]" aria-hidden="true" />
              <span className="font-bold">Choose PDF documents</span>
              <span className="mt-1 text-sm text-[var(--color-muted)]">Maximum 25 MB per file; encrypted PDFs are rejected.</span>
              <input id="documents" type="file" accept="application/pdf" multiple className="sr-only" onChange={(event) => setFiles(Array.from(event.target.files ?? []))} />
            </label>
            <ul className="mt-4 space-y-2" aria-live="polite">
              {files.map((file) => <li key={`${file.name}-${file.size}`} className="flex items-center gap-2 text-sm"><FileCheck2 className="h-4 w-4 text-emerald-700" />{file.name} · {(file.size / 1024 / 1024).toFixed(2)} MB</li>)}
            </ul>
          </div>
          {error && <p role="alert" className="rounded-xl border border-red-300 bg-red-50 p-4 text-sm text-red-900">{error}</p>}
          {progress && <p aria-live="polite" className="rounded-xl bg-blue-50 p-4 text-sm text-blue-900">{progress}</p>}
          <Button type="submit" variant="primary" disabled={busy || title.trim().length < 3 || !files.length} className="w-full disabled:cursor-not-allowed disabled:opacity-50">
            {busy ? "Submitting securely…" : "Submit for analysis"}
          </Button>
        </Card>
        <aside className="space-y-6">
          <Card className="p-6">
            <LockKeyhole className="mb-4 h-7 w-7 text-[var(--color-accent)]" />
            <h2 className="font-bold">Privacy boundary</h2>
            <p className="mt-2 text-sm leading-6 text-[var(--color-muted)]">Bank details, tax identifiers, raw OCR text and source documents stay local. External models receive only allowlisted tokenized fields.</p>
          </Card>
          <Card className="p-6">
            <h2 className="font-bold">What happens next</h2>
            <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-[var(--color-muted)]">
              <li>Quarantine and malware scan</li><li>Structured extraction and local PII masking</li><li>Parallel duplicate, sanctions and policy checks</li><li>Evidence verification and human approval</li><li>Idempotent ERP synchronization</li>
            </ol>
          </Card>
        </aside>
      </form>
    </div>
  );
}
