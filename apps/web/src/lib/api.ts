export type CaseStatus =
  | "DRAFT"
  | "SUBMITTED"
  | "FILE_SCANNING"
  | "DOCUMENT_PROCESSING"
  | "SPECIALIST_ANALYSIS"
  | "NEEDS_CLARIFICATION"
  | "DUPLICATE_REVIEW"
  | "RISK_REVIEW"
  | "EVIDENCE_BUILDING"
  | "VERIFICATION_FAILED"
  | "APPROVAL_PENDING"
  | "APPROVED"
  | "REJECTED"
  | "ERP_SYNC_PENDING"
  | "ERP_SYNC_FAILED"
  | "COMPLETED"
  | "INVOICE_MATCHING"
  | "EXCEPTION_CLASSIFIED"
  | "TOLERANCE_CHECK"
  | "AUTO_RESOLVED"
  | "FAILED"
  | "CANCELLED";

export interface VendorCase {
  case_id: string;
  tenant_id: string;
  case_number: string;
  case_type: string;
  status: CaseStatus;
  title: string;
  priority: "LOW" | "NORMAL" | "HIGH" | "URGENT";
  requester_user_id: string;
  current_version: number;
  created_at: string;
  updated_at: string;
}

export interface CaseList { items: VendorCase[]; total: number }

export interface CaseEvent {
  event_id: string;
  case_id: string;
  sequence: number;
  event_type: string;
  actor_type: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface EvidenceItem {
  evidence_item_id: string;
  source_type: string;
  source_id: string | null;
  source_locator: Record<string, unknown>;
  claim: string;
  reason_code: string;
  confidence: number | null;
}

export interface EvidencePacket { items: EvidenceItem[]; evidence_hash: string | null }

export interface ApprovalTask {
  approval_task_id: string;
  case_id: string;
  run_id: string;
  task_type: string;
  status: string;
  assigned_role: string;
  proposed_action: Record<string, unknown>;
  evidence_packet: Record<string, unknown>;
  evidence_hash: string;
  case_version: number;
  created_at: string;
}

export interface Notification {
  notification_id: string;
  case_id: string | null;
  notification_type: string;
  title: string;
  body: string;
  status: string;
  read_at: string | null;
  created_at: string;
}

export interface InitiatedUpload {
  document_id: string;
  upload_url: string;
  method: "PUT";
  expires_at: string;
  required_headers: Record<string, string>;
}

export interface AcceptedAction {
  case_id: string;
  run_id: string | null;
  status: CaseStatus;
  event_url: string | null;
}

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1").replace(/\/$/, "");
const API_ORIGIN = new URL(API_BASE).origin;
const DEV_TENANT = process.env.NEXT_PUBLIC_DEV_TENANT_ID ?? "00000000-0000-0000-0000-000000000001";
const DEV_USER = process.env.NEXT_PUBLIC_DEV_USER_ID ?? "00000000-0000-0000-0000-000000000101";

function requestHeaders(extra?: HeadersInit): Headers {
  const headers = new Headers(extra);
  const token = typeof window !== "undefined" ? window.sessionStorage.getItem("neurox_access_token") : null;
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  } else if (process.env.NODE_ENV !== "production") {
    headers.set("X-Dev-Tenant-Id", DEV_TENANT);
    headers.set("X-Dev-User-Id", DEV_USER);
    headers.set("X-Dev-Roles", "requester,analyst,approver,auditor,admin");
  }
  return headers;
}

function errorMessage(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "code" in detail) return String((detail as { code: unknown }).code);
  }
  return `Request failed (${status})`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = requestHeaders(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers, cache: "no-store" });
  const body = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) throw new Error(errorMessage(body, response.status));
  return body as T;
}

function idempotencyKey(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`;
}

export const api = {
  listCases: () => request<CaseList>("/cases"),
  getCase: (caseId: string) => request<VendorCase>(`/cases/${caseId}`),
  getEvents: (caseId: string) => request<CaseEvent[]>(`/cases/${caseId}/events`),
  getEvidence: (caseId: string) => request<EvidencePacket>(`/cases/${caseId}/evidence`),
  subscribeRunEvents: async (runId: string, signal: AbortSignal, onEvent: (event: Record<string, unknown>) => void) => {
    let lastEventId = "";
    while (!signal.aborted) {
      const headers = requestHeaders({ Accept: "text/event-stream" });
      if (lastEventId) headers.set("Last-Event-ID", lastEventId);
      const response = await fetch(`${API_BASE}/runs/${runId}/events`, { headers, signal, cache: "no-store" });
      if (!response.ok || !response.body) throw new Error(`Event stream failed (${response.status})`);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (!signal.aborted) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";
        for (const frame of frames) {
          const lines = frame.split("\n");
          const id = lines.find((line) => line.startsWith("id: "))?.slice(4);
          const data = lines.filter((line) => line.startsWith("data: ")).map((line) => line.slice(6)).join("\n");
          if (id) lastEventId = id;
          if (data) onEvent(JSON.parse(data) as Record<string, unknown>);
        }
      }
      if (!signal.aborted) await new Promise((resolve) => window.setTimeout(resolve, 1_000));
    }
  },
  listApprovals: () => request<ApprovalTask[]>("/approval-tasks"),
  listNotifications: () => request<Notification[]>("/notifications"),
  createCase: (title: string, priority: VendorCase["priority"] = "NORMAL") =>
    request<VendorCase>("/cases", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey("case") },
      body: JSON.stringify({ title, priority }),
    }),
  submitInvoice: (invoice_number: string, document_id?: string, priority: VendorCase["priority"] = "NORMAL", po_number?: string, vendor_id?: string) =>
    request<AcceptedAction>("/invoices", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey("invoice") },
      body: JSON.stringify({ invoice_number, document_id, priority, po_number, vendor_id }),
    }),
  initiateUpload: (caseId: string, file: File, documentType: string) =>
    request<InitiatedUpload>(`/cases/${caseId}/documents:initiate`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey("upload") },
      body: JSON.stringify({ filename: file.name, content_type: file.type, size_bytes: file.size, document_type: documentType }),
    }),
  uploadContent: async (upload: InitiatedUpload, file: File) => {
    const url = upload.upload_url.startsWith("http") ? upload.upload_url : `${API_ORIGIN}${upload.upload_url}`;
    const response = await fetch(url, { method: "PUT", headers: requestHeaders(upload.required_headers), body: file });
    const body = await response.json().catch(() => null);
    if (!response.ok) throw new Error(errorMessage(body, response.status));
    return body;
  },
  completeUpload: (documentId: string) => request(`/documents/${documentId}:complete`, {
    method: "POST", headers: { "Idempotency-Key": idempotencyKey("document") },
  }),
  submitCase: (caseId: string, expectedVersion: number) => request<AcceptedAction>(`/cases/${caseId}:submit`, {
    method: "POST", headers: { "Idempotency-Key": idempotencyKey("submit"), "If-Match": String(expectedVersion) },
  }),
  decideApproval: (task: ApprovalTask, decision: "APPROVED" | "REJECTED", comment: string) =>
    request<ApprovalTask>(`/approval-tasks/${task.approval_task_id}/decisions`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey("approval"), "If-Match": String(task.case_version) },
      body: JSON.stringify({ decision, comment: comment || null, expected_version: task.case_version, evidence_hash: task.evidence_hash, edited_payload: {} }),
    }),
  markNotificationRead: (notificationId: string) => request<Notification>(`/notifications/${notificationId}:read`, { method: "POST" }),
};
