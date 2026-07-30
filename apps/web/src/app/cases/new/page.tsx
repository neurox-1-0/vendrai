"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { LockKeyhole } from "lucide-react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Dropzone } from "@/components/ui/dropzone";
import { ProgressSteps } from "@/components/ui/progress-steps";
import { useAssistanceTarget } from "@/components/assistance-registry";

const STEPS = [
  "Creating a tenant-scoped case",
  "Uploading vendor documents",
  "Queuing malware scan and document extraction",
];

export default function CaseIntake() {
  const router = useRouter();
  const intakeAssistance = useAssistanceTarget({
    id: "supplier.secure-intake",
    title: "Supplier secure intake",
    description:
      "Enter the supplier request, choose priority and upload synthetic PDF evidence into quarantine before analysis.",
    tour: "supplier.intake-tour",
    order: 10,
  });
  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState<"LOW" | "NORMAL" | "HIGH" | "URGENT">("NORMAL");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [stepIndex, setStepIndex] = useState<number | null>(null);
  const [stepDetail, setStepDetail] = useState("");
  const [stepFailed, setStepFailed] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!files.length) return setError("Add at least one PDF document.");
    setBusy(true);
    setError("");
    setStepFailed(false);
    try {
      setStepIndex(0);
      setStepDetail("");
      const created = await api.createCase(title, priority);
      setStepIndex(1);
      for (const [index, file] of files.entries()) {
        setStepDetail(`${index + 1} of ${files.length}: ${file.name}`);
        const upload = await api.initiateUpload(created.case_id, file, "VENDOR_EVIDENCE");
        await api.uploadContent(upload, file);
        await api.completeUpload(upload.document_id);
      }
      setStepIndex(2);
      setStepDetail("");
      await api.submitCase(created.case_id, created.current_version);
      router.push(`/cases/${created.case_id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to submit this case");
      setStepFailed(true);
      setBusy(false);
    }
  }

  return (
    <div className="min-h-full p-6 lg:p-12">
      <header className="mb-10">
        <p className="mb-1 text-sm font-bold text-[var(--color-accent)]">Secure intake</p>
        <h1 className="font-display text-3xl font-bold">Start supplier onboarding</h1>
        <p className="mt-2 text-[var(--color-muted)]">Files enter quarantine first. They are scanned before extraction or agent analysis.</p>
      </header>
      <form onSubmit={submit} className="grid max-w-6xl gap-8 lg:grid-cols-[1.5fr_1fr]">
        <Card {...intakeAssistance} className="space-y-8">
          <div>
            <label htmlFor="title" className="mb-2 block text-sm font-bold">Supplier or request title</label>
            <Input id="title" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Example: Onboard Alpine Components GmbH" required minLength={3} />
          </div>
          <div>
            <label htmlFor="priority" className="mb-2 block text-sm font-bold">Priority</label>
            <Select id="priority" value={priority} onChange={(event) => setPriority(event.target.value as typeof priority)}>
              <option>LOW</option><option>NORMAL</option><option>HIGH</option><option>URGENT</option>
            </Select>
          </div>
          <Dropzone
            id="documents"
            label="Vendor documents"
            accept="application/pdf"
            files={files}
            onFilesChange={setFiles}
            hint="Maximum 25 MB per file; encrypted PDFs are rejected."
          />
          {error && <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">{error}</p>}
          <ProgressSteps
            steps={stepIndex === 1 && stepDetail ? [STEPS[0], `${STEPS[1]}: ${stepDetail}`, STEPS[2]] : STEPS}
            currentIndex={stepIndex}
            error={stepFailed}
          />
          <Button type="submit" variant="primary" disabled={busy || title.trim().length < 3 || !files.length} className="w-full">
            {busy ? "Submitting securely…" : "Submit for analysis"}
          </Button>
        </Card>
        <aside className="space-y-6">
          <Card>
            <LockKeyhole className="mb-4 h-7 w-7 text-[var(--color-accent)]" />
            <h2 className="font-bold">Privacy boundary</h2>
            <p className="mt-2 text-sm leading-6 text-[var(--color-muted)]">Bank details, tax identifiers, raw OCR text and source documents stay local. External models receive only allowlisted tokenized fields.</p>
          </Card>
          <Card>
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
