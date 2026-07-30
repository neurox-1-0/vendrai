import { AlertTriangle, CheckCircle2, CircleDashed, Clock3, RotateCw, ShieldAlert, XCircle } from "lucide-react";
import type { CaseStatus } from "@/lib/api";
import { Badge, type BadgeTone } from "@/components/ui/badge";

const presentation: Record<CaseStatus, { label: string; tone: BadgeTone; icon: typeof Clock3 }> = {
  DRAFT: { label: "Draft", tone: "neutral", icon: Clock3 },
  SUBMITTED: { label: "Queued", tone: "info", icon: CircleDashed },
  FILE_SCANNING: { label: "Scanning", tone: "info", icon: ShieldAlert },
  DOCUMENT_PROCESSING: { label: "Extracting", tone: "brand", icon: RotateCw },
  SPECIALIST_ANALYSIS: { label: "Analyzing", tone: "brand", icon: RotateCw },
  NEEDS_CLARIFICATION: { label: "Clarification", tone: "warning", icon: AlertTriangle },
  DUPLICATE_REVIEW: { label: "Duplicate review", tone: "warning", icon: AlertTriangle },
  RISK_REVIEW: { label: "Risk review", tone: "negative", icon: ShieldAlert },
  EVIDENCE_BUILDING: { label: "Building evidence", tone: "brand", icon: RotateCw },
  VERIFICATION_FAILED: { label: "Verification failed", tone: "negative", icon: XCircle },
  APPROVAL_PENDING: { label: "Review required", tone: "warning", icon: Clock3 },
  APPROVED: { label: "Approved", tone: "positive", icon: CheckCircle2 },
  REJECTED: { label: "Rejected", tone: "negative", icon: XCircle },
  ERP_SYNC_PENDING: { label: "Syncing", tone: "info", icon: RotateCw },
  ERP_SYNC_FAILED: { label: "ERP retry required", tone: "negative", icon: AlertTriangle },
  COMPLETED: { label: "Completed", tone: "positive", icon: CheckCircle2 },
  INVOICE_MATCHING: { label: "Matching invoice", tone: "brand", icon: RotateCw },
  EXCEPTION_CLASSIFIED: { label: "Classifying exception", tone: "brand", icon: RotateCw },
  TOLERANCE_CHECK: { label: "Tolerance check", tone: "info", icon: RotateCw },
  AUTO_RESOLVED: { label: "Auto-resolved", tone: "positive", icon: CheckCircle2 },
  BLOCKED_DUPLICATE: { label: "Duplicate blocked", tone: "negative", icon: ShieldAlert },
  HOLD: { label: "Payment hold", tone: "warning", icon: AlertTriangle },
  FAILED: { label: "Failed", tone: "negative", icon: XCircle },
  CANCELLED: { label: "Cancelled", tone: "neutral", icon: XCircle },
};

export function StatusChip({ status }: { status: CaseStatus }) {
  const value = presentation[status] ?? presentation.FAILED;
  return (
    <Badge tone={value.tone} icon={value.icon}>
      <span>{value.label}</span>
      <span className="sr-only">Case status:</span>
    </Badge>
  );
}
