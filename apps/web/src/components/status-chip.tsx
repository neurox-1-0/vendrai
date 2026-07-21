import { AlertTriangle, CheckCircle2, CircleDashed, Clock3, RotateCw, ShieldAlert, XCircle } from "lucide-react";
import type { CaseStatus } from "@/lib/api";

const presentation: Record<CaseStatus, { label: string; classes: string; icon: typeof Clock3 }> = {
  DRAFT: { label: "Draft", classes: "bg-slate-100 text-slate-700", icon: Clock3 },
  SUBMITTED: { label: "Queued", classes: "bg-blue-100 text-blue-800", icon: CircleDashed },
  FILE_SCANNING: { label: "Scanning", classes: "bg-cyan-100 text-cyan-900", icon: ShieldAlert },
  DOCUMENT_PROCESSING: { label: "Extracting", classes: "bg-indigo-100 text-indigo-900", icon: RotateCw },
  SPECIALIST_ANALYSIS: { label: "Analyzing", classes: "bg-violet-100 text-violet-900", icon: RotateCw },
  NEEDS_CLARIFICATION: { label: "Clarification", classes: "bg-amber-100 text-amber-900", icon: AlertTriangle },
  DUPLICATE_REVIEW: { label: "Duplicate review", classes: "bg-orange-100 text-orange-900", icon: AlertTriangle },
  RISK_REVIEW: { label: "Risk review", classes: "bg-red-100 text-red-900", icon: ShieldAlert },
  EVIDENCE_BUILDING: { label: "Building evidence", classes: "bg-purple-100 text-purple-900", icon: RotateCw },
  VERIFICATION_FAILED: { label: "Verification failed", classes: "bg-red-100 text-red-900", icon: XCircle },
  APPROVAL_PENDING: { label: "Review required", classes: "bg-amber-100 text-amber-900", icon: Clock3 },
  APPROVED: { label: "Approved", classes: "bg-emerald-100 text-emerald-900", icon: CheckCircle2 },
  REJECTED: { label: "Rejected", classes: "bg-red-100 text-red-900", icon: XCircle },
  ERP_SYNC_PENDING: { label: "Syncing", classes: "bg-blue-100 text-blue-900", icon: RotateCw },
  ERP_SYNC_FAILED: { label: "ERP retry required", classes: "bg-red-100 text-red-900", icon: AlertTriangle },
  COMPLETED: { label: "Completed", classes: "bg-emerald-100 text-emerald-900", icon: CheckCircle2 },
  INVOICE_MATCHING: { label: "Matching invoice", classes: "bg-indigo-100 text-indigo-900", icon: RotateCw },
  EXCEPTION_CLASSIFIED: { label: "Classifying exception", classes: "bg-fuchsia-100 text-fuchsia-900", icon: RotateCw },
  TOLERANCE_CHECK: { label: "Tolerance check", classes: "bg-teal-100 text-teal-900", icon: RotateCw },
  AUTO_RESOLVED: { label: "Auto-resolved", classes: "bg-emerald-100 text-emerald-900", icon: CheckCircle2 },
  FAILED: { label: "Failed", classes: "bg-red-100 text-red-900", icon: XCircle },
  CANCELLED: { label: "Cancelled", classes: "bg-slate-200 text-slate-800", icon: XCircle },
};

export function StatusChip({ status }: { status: CaseStatus }) {
  const value = presentation[status] ?? presentation.FAILED;
  const Icon = value.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold ${value.classes}`}>
      <Icon aria-hidden="true" className="h-3.5 w-3.5" />
      <span>{value.label}</span>
      <span className="sr-only">Case status:</span>
    </span>
  );
}
