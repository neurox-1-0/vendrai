"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Receipt } from "lucide-react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Dropzone } from "@/components/ui/dropzone";
import { ProgressSteps } from "@/components/ui/progress-steps";
import { useAssistanceTarget } from "@/components/assistance-registry";

const STEPS = [
  "Preparing upload",
  "Uploading invoice documents",
  "Submitting invoice for agent analysis",
];

export default function InvoiceIntake() {
  const router = useRouter();
  const intakeAssistance = useAssistanceTarget({
    id: "invoice.secure-intake",
    title: "Invoice exception intake",
    description:
      "Enter invoice references and upload the synthetic invoice, purchase order and receipt evidence for matching.",
    tour: "invoice.intake-tour",
    order: 10,
  });
  const [invoiceNumber, setInvoiceNumber] = useState("");
  const [poNumber, setPoNumber] = useState("");
  const [priority, setPriority] = useState<"LOW" | "NORMAL" | "HIGH" | "URGENT">("NORMAL");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [stepIndex, setStepIndex] = useState<number | null>(null);
  const [stepDetail, setStepDetail] = useState("");
  const [stepFailed, setStepFailed] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!files.length) return setError("Add at least one invoice document.");
    setBusy(true);
    setError("");
    setStepFailed(false);
    try {
      setStepIndex(0);
      setStepDetail("");
      const invoiceCase = await api.createInvoiceDraft(invoiceNumber, priority, poNumber || undefined);

      setStepIndex(1);
      for (const file of files) {
        setStepDetail(file.name);
        const fnLower = file.name.toLowerCase();
        const documentType = (fnLower.includes("po") || fnLower.includes("purchase")) ? "PURCHASE_ORDER"
                           : (fnLower.includes("grn") || fnLower.includes("receipt")) ? "GOODS_RECEIPT"
                           : "INVOICE";
        const upload = await api.initiateUpload(invoiceCase.case_id, file, documentType);
        await api.uploadContent(upload, file);
        await api.completeUpload(upload.document_id);
      }

      setStepIndex(2);
      setStepDetail("");
      const created = await api.submitCase(invoiceCase.case_id, invoiceCase.current_version);
      router.push(`/cases/${created.case_id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to submit this invoice");
      setStepFailed(true);
      setBusy(false);
    }
  }

  return (
    <div className="min-h-full p-6 lg:p-12">
      <header className="mb-10">
        <p className="mb-1 text-sm font-bold text-[var(--color-accent)]">Accounts Payable</p>
        <h1 className="font-display text-3xl font-bold">Process Invoice Exception</h1>
        <p className="mt-2 text-[var(--color-muted)]">Upload an invoice to trigger 3-way matching and tolerance checks.</p>
      </header>
      <form onSubmit={submit} className="grid max-w-6xl gap-8 lg:grid-cols-[1.5fr_1fr]">
        <Card {...intakeAssistance} className="space-y-8">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="invoiceNumber" className="mb-2 block text-sm font-bold">Invoice Number</label>
              <Input id="invoiceNumber" value={invoiceNumber} onChange={(event) => setInvoiceNumber(event.target.value)} placeholder="Example: INV-2023-100" required minLength={3} />
            </div>
            <div>
              <label htmlFor="poNumber" className="mb-2 block text-sm font-bold">PO Number (Optional)</label>
              <Input id="poNumber" value={poNumber} onChange={(event) => setPoNumber(event.target.value)} placeholder="Example: PO-40012" />
            </div>
          </div>
          <div>
            <label htmlFor="priority" className="mb-2 block text-sm font-bold">Priority</label>
            <Select id="priority" value={priority} onChange={(event) => setPriority(event.target.value as typeof priority)}>
              <option>LOW</option><option>NORMAL</option><option>HIGH</option><option>URGENT</option>
            </Select>
          </div>
          <Dropzone
            id="documents"
            label="Invoice Document"
            accept="application/pdf"
            files={files}
            onFilesChange={setFiles}
            hint="Maximum 25 MB per file."
          />
          {error && <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">{error}</p>}
          <ProgressSteps
            steps={stepIndex === 1 && stepDetail ? [STEPS[0], `${STEPS[1]}: ${stepDetail}`, STEPS[2]] : STEPS}
            currentIndex={stepIndex}
            error={stepFailed}
          />
          <Button type="submit" variant="primary" disabled={busy || invoiceNumber.trim().length < 3 || !files.length} className="w-full">
            {busy ? "Processing…" : "Submit Invoice"}
          </Button>
        </Card>
        <aside className="space-y-6">
          <Card>
            <Receipt className="mb-4 h-7 w-7 text-[var(--color-accent)]" />
            <h2 className="font-bold">Automated 3-Way Matching</h2>
            <p className="mt-2 text-sm leading-6 text-[var(--color-muted)]">The AI Agent will automatically extract line items and match them against Purchase Orders and Goods Receipt Notes.</p>
          </Card>
          <Card>
            <h2 className="font-bold">Exception Handling</h2>
            <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-[var(--color-muted)]">
              <li>Invoice line item extraction</li><li>PO and GRN matching</li><li>Tolerance and Variance checks</li><li>Fraud and duplicate detection</li><li>Automated resolution or manual review</li>
            </ol>
          </Card>
        </aside>
      </form>
    </div>
  );
}
