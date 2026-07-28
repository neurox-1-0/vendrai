import { getAccessToken } from "@/lib/auth-token";

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
  | "BLOCKED_DUPLICATE"
  | "HOLD"
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
  assigned_user_id: string | null;
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

export interface AgentStep {
  step_id: string;
  run_id: string;
  node_name: string;
  display_name: string;
  agent_kind: "PLANNER" | "SPECIALIST" | "REASONING" | "VERIFIER" | "HUMAN" | "EXECUTION";
  attempt: number;
  status: string;
  route_reason: string;
  dependencies: string[];
  input_summary: Record<string, unknown>;
  output_summary: Record<string, unknown>;
  error: Record<string, unknown>;
  latency_ms: number | null;
  started_at: string;
  completed_at: string | null;
}

export interface RunGraph {
  run: {
    run_id: string;
    case_id: string;
    thread_id: string;
    graph_name: string;
    graph_version: string;
    status: string;
    current_node: string | null;
    state_version: number;
    created_at: string;
    updated_at: string;
  };
  objective: string;
  selected_path: string[];
  plan: Record<string, unknown>;
  nodes: AgentStep[];
  edges: Array<{
    source: string;
    target: string;
    relation: "DEPENDS_ON" | "ROUTES_TO";
  }>;
  timing: {
    total_elapsed_ms: number | null;
    active_compute_ms: number;
    critical_path_ms: number;
    parallel_time_saved_ms: number;
    human_waiting_ms: number | null;
  };
}

export interface RunDiagnostics {
  graph: RunGraph;
  versions: Record<string, string | null>;
  integrity: Record<string, string | number | boolean | null>;
  decision_summary: Record<string, unknown>;
}

export interface CopilotSession {
  copilot_session_id: string;
  context_case_id: string | null;
  title: string;
  help_pack_version: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface AssistanceTargetContext {
  target_id: string;
  title: string;
  description: string;
}

export interface CopilotMessage {
  copilot_message_id: string;
  copilot_session_id: string;
  role: "USER" | "ASSISTANT";
  content: string;
  citations: Array<{
    source_id: string;
    title: string;
    help_pack_version: string;
  }>;
  ui_actions: Array<{
    action_type:
      | "NAVIGATE"
      | "SPOTLIGHT"
      | "OPEN_PANEL"
      | "SET_FILTER"
      | "START_TOUR";
    target: string;
    label: string;
  }>;
  provider: string;
  model_version: string | null;
  latency_ms: number | null;
  error_code: string | null;
  created_at: string;
}

export interface CopilotFeedback {
  copilot_feedback_id: string;
  copilot_message_id: string;
  rating: "HELPFUL" | "NOT_HELPFUL";
  reason_masked: string | null;
  help_pack_version: string;
  created_at: string;
}

export interface InvoiceLineEvidence {
  line_number: number;
  description: string;
  quantity: number;
  unit_price: number;
  amount: number;
}

export interface InvoiceMatchLine {
  invoice_line: InvoiceLineEvidence;
  po_line: { quantity?: number; unit_price?: number } | null;
  grn_line: { quantity_received?: number; received?: number } | null;
  price_variance: number;
  quantity_variance: number;
  match_status: string;
}

export interface InvoiceEvidencePacket {
  recommendation?: string;
  reason_codes?: string[];
  extracted_invoice?: {
    currency?: string;
    invoice_number?: string;
    total_amount?: number;
    line_items?: InvoiceLineEvidence[];
  };
  match_result?: {
    match_status?: string;
    overall_variance_amount?: number;
    overall_variance_pct?: number;
    line_matches?: InvoiceMatchLine[];
  };
  exception?: Array<{
    exception_type: string;
    severity: string;
    mismatch_details?: { message?: string; [key: string]: unknown };
  }>;
  tolerance?: {
    within_tolerance?: boolean;
    threshold_amount?: number;
    threshold_pct?: number;
  };
  [key: string]: unknown;
}

export interface ApprovalTask {
  approval_task_id: string;
  case_id: string;
  run_id: string;
  task_type: string;
  status: string;
  assigned_role: string;
  proposed_action: Record<string, unknown>;
  evidence_packet: InvoiceEvidencePacket;
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

export type MetricKey =
  | "invoice_stp_rate"
  | "invoice_cycle_hours"
  | "vendor_onboarding_cycle_hours"
  | "vendor_activation_rate"
  | "invoice_exception_rate"
  | "pending_approval_count";

export interface MetricValue {
  key: MetricKey;
  label: string;
  value: number | null;
  unit: "percent" | "hours" | "count";
  numerator: number | null;
  denominator: number | null;
  previous_value: number | null;
  definition: string;
  statistics: Record<string, number | null>;
}

export interface AnalyticsSummary {
  period_start: string;
  period_end: string;
  timezone: string;
  metrics: MetricValue[];
  approval_aging: Record<string, number>;
  generated_at: string;
}

export interface MetricSeries {
  key: MetricKey;
  grain: "day" | "week";
  points: Array<{
    period_start: string;
    value: number | null;
    numerator: number | null;
    denominator: number | null;
  }>;
}

export interface ExceptionAnalytics {
  items: Array<{
    exception_type: string;
    severity: string;
    count: number;
    open_count: number;
  }>;
  total: number;
}

export interface RiskFinding {
  risk_finding_id: string;
  case_id: string | null;
  finding_type: string;
  severity: string;
  mode: "ACTIVE" | "SHADOW";
  data_origin: string;
  detector_key: string;
  detector_version: string;
  score: number | null;
  threshold: number | null;
  reason_codes: string[];
  explanation: { summary?: string; [key: string]: unknown };
  status: string;
  disposition: string | null;
  created_at: string;
}

export interface AlertInstance {
  alert_instance_id: string;
  alert_rule_id: string;
  case_id: string | null;
  risk_finding_id: string | null;
  title: string;
  body: string;
  severity: string;
  status: string;
  metric_snapshot: Record<string, unknown>;
  first_triggered_at: string;
  acknowledged_at: string | null;
}

export interface AnalyticsAnswer {
  answer: string;
  query: { metric: MetricKey; start: string; end: string; grain: string };
  metric: MetricValue;
  citations: Array<{ label: string; detail: string }>;
  provider: "GOVERNED_LOCAL" | "GEMINI_STRUCTURED";
}

export interface InitiatedUpload {
  document_id: string;
  upload_url: string;
  method: "PUT";
  expires_at: string;
  required_headers: Record<string, string>;
}

export interface CaseDocument {
  document_id: string;
  case_id: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  sha256: string | null;
  malware_status: string;
  processing_status: string;
  created_at: string;
}

export interface DocumentPage {
  page_id: string;
  document_id: string;
  page_number: number;
  text_content: string | null;
  layout_json: Record<string, unknown>;
  ocr_confidence: number | null;
}

export interface ExtractedField {
  extracted_field_id: string;
  document_id: string;
  field_name: string;
  field_value_masked: string | null;
  confidence: number | null;
  source_page: number | null;
  source_bbox: Record<string, unknown>;
  extractor_type: string;
  extractor_version: string | null;
  human_verified: boolean;
  updated_at: string;
}

export interface ClarificationTask {
  clarification_task_id: string;
  case_id: string;
  run_id: string;
  status: string;
  questions: Array<{
    question_id?: string;
    text?: string;
    field_name?: string;
    requested_from_role?: string;
  }>;
  response: Record<string, unknown>;
  created_at: string;
}

export interface SanctionsImport {
  sanctions_import_id: string;
  source: string;
  source_url: string;
  status: string;
  dataset_id: string | null;
  etag: string | null;
  sha256: string | null;
  entity_count: number | null;
  error_code: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
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
  const token = getAccessToken();
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

async function requestBlob(path: string): Promise<Blob> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: requestHeaders(),
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(errorMessage(body, response.status));
  }
  return response.blob();
}

function idempotencyKey(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`;
}

export const api = {
  listCases: () => request<CaseList>("/cases"),
  getAnalyticsSummary: () =>
    request<AnalyticsSummary>("/analytics/summary"),
  getMetricSeries: (metric: MetricKey, grain: "day" | "week" = "week") =>
    request<MetricSeries>(
      `/analytics/timeseries?metric=${metric}&grain=${grain}`,
    ),
  getExceptionAnalytics: () =>
    request<ExceptionAnalytics>("/analytics/exceptions"),
  askAnalytics: (question: string) =>
    request<AnalyticsAnswer>("/analytics/query", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey("analytics-query") },
      body: JSON.stringify({ question }),
    }),
  listRiskFindings: () => request<RiskFinding[]>("/risk-findings"),
  listAlerts: () => request<AlertInstance[]>("/alerts"),
  acknowledgeAlert: (alertId: string) =>
    request<AlertInstance>(`/alerts/${alertId}:acknowledge`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey("alert-ack") },
    }),
  getCase: (caseId: string) => request<VendorCase>(`/cases/${caseId}`),
  getEvents: (caseId: string) => request<CaseEvent[]>(`/cases/${caseId}/events`),
  getRunGraph: (runId: string) => request<RunGraph>(`/runs/${runId}/graph`),
  getRunDiagnostics: (runId: string) =>
    request<RunDiagnostics>(`/runs/${runId}/diagnostics`),
  createCopilotSession: (currentPath: string, caseId?: string) =>
    request<CopilotSession>("/copilot/sessions", {
      method: "POST",
      headers: {
        "Idempotency-Key": idempotencyKey("copilot-session"),
      },
      body: JSON.stringify({
        current_path: currentPath,
        case_id: caseId ?? null,
      }),
    }),
  listCopilotMessages: (sessionId: string) =>
    request<CopilotMessage[]>(
      `/copilot/sessions/${sessionId}/messages`,
    ),
  sendCopilotMessage: (
    sessionId: string,
    question: string,
    currentPath: string,
    assistanceTargets: AssistanceTargetContext[],
    caseId?: string,
  ) =>
    request<CopilotMessage>(
      `/copilot/sessions/${sessionId}/messages`,
      {
        method: "POST",
        headers: {
          "Idempotency-Key": idempotencyKey("copilot-message"),
        },
        body: JSON.stringify({
          question,
          current_path: currentPath,
          case_id: caseId ?? null,
          assistance_targets: assistanceTargets,
        }),
      },
    ),
  sendCopilotFeedback: (
    messageId: string,
    rating: CopilotFeedback["rating"],
  ) =>
    request<CopilotFeedback>(
      `/copilot/messages/${messageId}/feedback`,
      {
        method: "POST",
        headers: {
          "Idempotency-Key": idempotencyKey("copilot-feedback"),
        },
        body: JSON.stringify({ rating, reason: null }),
      },
    ),
  getEvidence: (caseId: string) => request<EvidencePacket>(`/cases/${caseId}/evidence`),
  listCaseDocuments: (caseId: string) => request<CaseDocument[]>(`/cases/${caseId}/documents`),
  listDocumentPages: (documentId: string) => request<DocumentPage[]>(`/documents/${documentId}/pages`),
  listDocumentFields: (documentId: string) => request<ExtractedField[]>(`/documents/${documentId}/fields`),
  downloadDocument: (documentId: string) => requestBlob(`/documents/${documentId}/content`),
  correctDocumentField: (
    documentId: string,
    fieldId: string,
    value: string,
    reason: string,
    expectedVersion: number,
  ) => request<ExtractedField>(`/documents/${documentId}/fields/${fieldId}`, {
    method: "PATCH",
    headers: {
      "Idempotency-Key": idempotencyKey("field-correction"),
      "If-Match": String(expectedVersion),
    },
    body: JSON.stringify({ value, reason, expected_version: expectedVersion }),
  }),
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
  listReviews: () => request<ApprovalTask[]>("/review-tasks"),
  listClarifications: () => request<ClarificationTask[]>("/clarification-tasks"),
  requestSanctionsImport: (source: "OFAC" | "UN" | "EU") =>
    request<SanctionsImport>("/admin/sanctions-imports", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey(`sanctions-${source.toLowerCase()}`) },
      body: JSON.stringify({ source }),
    }),
  listNotifications: () => request<Notification[]>("/notifications"),
  createCase: (title: string, priority: VendorCase["priority"] = "NORMAL") =>
    request<VendorCase>("/cases", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey("case") },
      body: JSON.stringify({ title, priority }),
    }),
  createInvoiceDraft: (
    invoice_number: string,
    priority: VendorCase["priority"] = "NORMAL",
    po_number?: string,
    vendor_id?: string,
    currency = "LKR",
  ) =>
    request<VendorCase>("/invoices:draft", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey("invoice-draft") },
      body: JSON.stringify({ invoice_number, priority, po_number, vendor_id, currency }),
    }),
  submitInvoice: (
    invoice_number: string,
    document_id?: string,
    priority: VendorCase["priority"] = "NORMAL",
    po_number?: string,
    vendor_id?: string,
    document_ids?: string[]
  ) =>
    request<AcceptedAction>("/invoices", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey("invoice") },
      body: JSON.stringify({ invoice_number, document_id, document_ids: document_ids || [], priority, po_number, vendor_id }),
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
  claimCase: (caseId: string, expectedVersion: number) => request<VendorCase>(`/cases/${caseId}:claim`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey("claim"), "If-Match": String(expectedVersion) },
  }),
  releaseCase: (caseId: string, expectedVersion: number) => request<VendorCase>(`/cases/${caseId}:release`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey("release"), "If-Match": String(expectedVersion) },
  }),
  decideApproval: (task: ApprovalTask, decision: "APPROVED" | "REJECTED", comment: string) =>
    request<ApprovalTask>(`/${task.task_type.endsWith("_REVIEW") ? "review-tasks" : "approval-tasks"}/${task.approval_task_id}/decisions`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey("approval"), "If-Match": String(task.case_version) },
      body: JSON.stringify({ decision, comment: comment || null, expected_version: task.case_version, evidence_hash: task.evidence_hash, edited_payload: {} }),
    }),
  respondToClarification: (
    task: ClarificationTask,
    answers: Record<string, string>,
    expectedVersion: number,
  ) => request(`/clarification-tasks/${task.clarification_task_id}/responses`, {
    method: "POST",
    headers: {
      "Idempotency-Key": idempotencyKey("clarification"),
      "If-Match": String(expectedVersion),
    },
    body: JSON.stringify({ answers, expected_version: expectedVersion }),
  }),
  markNotificationRead: (notificationId: string) => request<Notification>(`/notifications/${notificationId}:read`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey("notification-read") },
  }),
};
