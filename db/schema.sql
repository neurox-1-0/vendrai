-- GMora Vendor-to-Pay Multi-Agent Exception System
-- PostgreSQL + pgvector reference schema
-- This is a foundation schema; use Alembic migrations in the application.

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS vector;


CREATE TYPE case_type AS ENUM ('VENDOR_ONBOARDING', 'INVOICE_EXCEPTION');
CREATE TYPE case_status AS ENUM (
  'DRAFT','SUBMITTED','FILE_SCANNING','DOCUMENT_PROCESSING','SPECIALIST_ANALYSIS',
  'NEEDS_CLARIFICATION','DUPLICATE_REVIEW','RISK_REVIEW','EVIDENCE_BUILDING',
  'VERIFICATION_FAILED','APPROVAL_PENDING','APPROVED','REJECTED',
  'ERP_SYNC_PENDING','ERP_SYNC_FAILED','COMPLETED','FAILED','CANCELLED'
);
CREATE TYPE run_status AS ENUM ('QUEUED','RUNNING','INTERRUPTED','SUCCEEDED','FAILED','CANCELLED');
CREATE TYPE tool_status AS ENUM ('SUCCESS','PARTIAL','PENDING','FAILED','BLOCKED');
CREATE TYPE approval_status AS ENUM ('PENDING','APPROVED','REJECTED','MORE_INFO','ESCALATED','CANCELLED','EXPIRED');
CREATE TYPE risk_level AS ENUM ('LOW','MEDIUM','HIGH','CRITICAL','UNKNOWN');

CREATE TABLE tenants (
  tenant_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  slug citext NOT NULL UNIQUE,
  status text NOT NULL DEFAULT 'ACTIVE',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
  user_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  external_subject text NOT NULL,
  email citext NOT NULL,
  full_name text NOT NULL,
  status text NOT NULL DEFAULT 'ACTIVE',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, external_subject),
  UNIQUE (tenant_id, email)
);

CREATE TABLE roles (
  role_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  name text NOT NULL,
  permissions jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name)
);

CREATE TABLE user_roles (
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  user_id uuid NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  role_id uuid NOT NULL REFERENCES roles(role_id) ON DELETE CASCADE,
  assigned_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, role_id)
);

CREATE TABLE tenant_settings (
  tenant_id uuid PRIMARY KEY REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  settings jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE integrations (
  integration_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  integration_type text NOT NULL,
  display_name text NOT NULL,
  config_ciphertext bytea,
  status text NOT NULL DEFAULT 'DISABLED',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE vendors (
  vendor_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  legal_name text NOT NULL,
  normalized_legal_name text NOT NULL,
  trading_name text,
  tax_id_ciphertext bytea,
  tax_id_hash bytea,
  registration_number text,
  category text,
  registered_country char(2),
  status text NOT NULL DEFAULT 'PROPOSED',
  erp_vendor_id text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, erp_vendor_id)
);

CREATE INDEX vendors_name_trgm_idx ON vendors USING gin (normalized_legal_name gin_trgm_ops);
CREATE INDEX vendors_tax_hash_idx ON vendors (tenant_id, tax_id_hash) WHERE tax_id_hash IS NOT NULL;

CREATE TABLE vendor_aliases (
  alias_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  vendor_id uuid NOT NULL REFERENCES vendors(vendor_id) ON DELETE CASCADE,
  alias text NOT NULL,
  normalized_alias text NOT NULL,
  source_document_id uuid,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX vendor_aliases_trgm_idx ON vendor_aliases USING gin (normalized_alias gin_trgm_ops);

CREATE TABLE vendor_bank_accounts (
  bank_account_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  vendor_id uuid REFERENCES vendors(vendor_id),
  bank_name text,
  bank_country char(2),
  account_ciphertext bytea NOT NULL,
  account_hash bytea NOT NULL,
  account_last4 char(4),
  swift_bic text,
  verification_status text NOT NULL DEFAULT 'UNVERIFIED',
  verified_by uuid REFERENCES users(user_id),
  verified_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX vendor_bank_hash_idx ON vendor_bank_accounts (tenant_id, account_hash);

CREATE TABLE cases (
  case_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  case_number text NOT NULL,
  case_type case_type NOT NULL,
  status case_status NOT NULL DEFAULT 'DRAFT',
  requester_user_id uuid NOT NULL REFERENCES users(user_id),
  assigned_user_id uuid REFERENCES users(user_id),
  vendor_id uuid REFERENCES vendors(vendor_id),
  title text NOT NULL,
  priority text NOT NULL DEFAULT 'NORMAL',
  current_version integer NOT NULL DEFAULT 1,
  submitted_at timestamptz,
  resolved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, case_number)
);
CREATE INDEX cases_tenant_status_idx ON cases (tenant_id, status, created_at DESC);

CREATE TABLE case_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  case_id uuid NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
  event_type text NOT NULL,
  from_status case_status,
  to_status case_status,
  actor_type text NOT NULL,
  actor_id text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX case_events_case_idx ON case_events (tenant_id, case_id, created_at);

CREATE TABLE case_comments (
  comment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  case_id uuid NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
  author_user_id uuid NOT NULL REFERENCES users(user_id),
  body text NOT NULL,
  visibility text NOT NULL DEFAULT 'INTERNAL',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE documents (
  document_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  case_id uuid REFERENCES cases(case_id) ON DELETE CASCADE,
  vendor_id uuid REFERENCES vendors(vendor_id),
  document_type text NOT NULL,
  original_filename text NOT NULL,
  sanitized_filename text NOT NULL,
  mime_type text NOT NULL,
  size_bytes bigint NOT NULL,
  sha256 char(64) NOT NULL,
  storage_key text NOT NULL,
  encryption_key_version text,
  malware_status text NOT NULL DEFAULT 'PENDING',
  processing_status text NOT NULL DEFAULT 'UPLOADED',
  parser_version text,
  ocr_version text,
  uploaded_by uuid NOT NULL REFERENCES users(user_id),
  uploaded_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, sha256, case_id)
);

CREATE TABLE document_pages (
  page_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  document_id uuid NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
  page_number integer NOT NULL,
  text_content text,
  layout_json jsonb,
  ocr_confidence numeric(5,4),
  UNIQUE (document_id, page_number)
);

CREATE TABLE document_chunks (
  chunk_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  document_id uuid NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
  page_start integer,
  page_end integer,
  heading_path jsonb NOT NULL DEFAULT '[]'::jsonb,
  chunk_index integer NOT NULL,
  content text NOT NULL,
  content_hash char(64) NOT NULL,
  embedding vector(768),
  token_count integer,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (document_id, chunk_index, content_hash)
);
CREATE INDEX document_chunks_tenant_idx ON document_chunks (tenant_id, document_id);
CREATE INDEX document_chunks_fts_idx ON document_chunks USING gin (to_tsvector('english', content));

CREATE TABLE extracted_fields (
  extracted_field_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  document_id uuid NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
  field_name text NOT NULL,
  field_value_masked text,
  field_value_ciphertext bytea,
  normalized_value text,
  confidence numeric(5,4),
  source_page integer,
  source_bbox jsonb,
  extractor_type text NOT NULL,
  extractor_version text,
  human_verified boolean NOT NULL DEFAULT false,
  verified_by uuid REFERENCES users(user_id),
  verified_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX extracted_fields_lookup_idx ON extracted_fields (tenant_id, field_name, normalized_value);

CREATE TABLE policy_documents (
  policy_document_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  title text NOT NULL,
  policy_code text NOT NULL,
  owner_department text,
  status text NOT NULL DEFAULT 'DRAFT',
  created_by uuid NOT NULL REFERENCES users(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, policy_code)
);

CREATE TABLE policy_versions (
  policy_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  policy_document_id uuid NOT NULL REFERENCES policy_documents(policy_document_id) ON DELETE CASCADE,
  version text NOT NULL,
  effective_from date NOT NULL,
  effective_to date,
  content text NOT NULL,
  content_hash char(64) NOT NULL,
  status text NOT NULL DEFAULT 'DRAFT',
  published_by uuid REFERENCES users(user_id),
  published_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (policy_document_id, version)
);

CREATE TABLE policy_chunks (
  policy_chunk_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  policy_version_id uuid NOT NULL REFERENCES policy_versions(policy_version_id) ON DELETE CASCADE,
  chunk_index integer NOT NULL,
  heading_path jsonb NOT NULL DEFAULT '[]'::jsonb,
  content text NOT NULL,
  content_hash char(64) NOT NULL,
  embedding vector(768),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (policy_version_id, chunk_index)
);
CREATE INDEX policy_chunks_fts_idx ON policy_chunks USING gin (to_tsvector('english', content));

CREATE TABLE duplicate_candidates (
  duplicate_candidate_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  case_id uuid NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
  candidate_vendor_id uuid NOT NULL REFERENCES vendors(vendor_id),
  score numeric(6,5) NOT NULL,
  signal_breakdown jsonb NOT NULL,
  status text NOT NULL DEFAULT 'PENDING_REVIEW',
  resolved_by uuid REFERENCES users(user_id),
  resolution text,
  resolved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX duplicate_candidates_case_idx ON duplicate_candidates (tenant_id, case_id, score DESC);

CREATE TABLE risk_checks (
  risk_check_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  case_id uuid NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
  vendor_id uuid REFERENCES vendors(vendor_id),
  check_type text NOT NULL,
  provider text NOT NULL,
  status tool_status NOT NULL,
  risk_level risk_level NOT NULL DEFAULT 'UNKNOWN',
  result jsonb,
  evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
  checked_at timestamptz,
  expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE agent_runs (
  run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  case_id uuid NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
  thread_id text NOT NULL,
  graph_name text NOT NULL,
  graph_version text NOT NULL,
  status run_status NOT NULL DEFAULT 'QUEUED',
  current_node text,
  state_version integer NOT NULL DEFAULT 1,
  model_name text,
  prompt_version text,
  input_hash char(64),
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, thread_id)
);
CREATE INDEX agent_runs_case_idx ON agent_runs (tenant_id, case_id, created_at DESC);

CREATE TABLE agent_steps (
  step_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  run_id uuid NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
  node_name text NOT NULL,
  attempt integer NOT NULL DEFAULT 1,
  status run_status NOT NULL,
  input_summary jsonb,
  output_summary jsonb,
  error jsonb,
  started_at timestamptz,
  completed_at timestamptz,
  latency_ms integer,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE tool_calls (
  tool_call_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  run_id uuid NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
  step_id uuid REFERENCES agent_steps(step_id) ON DELETE CASCADE,
  tool_name text NOT NULL,
  risk_class text NOT NULL,
  idempotency_key text,
  input_json jsonb NOT NULL,
  input_hash char(64),
  status tool_status NOT NULL,
  retry_count integer NOT NULL DEFAULT 0,
  cache_hit boolean NOT NULL DEFAULT false,
  latency_ms integer,
  error_type text,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);
CREATE UNIQUE INDEX tool_calls_idempotency_idx ON tool_calls (tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL;

CREATE TABLE tool_results (
  tool_result_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  tool_call_id uuid NOT NULL REFERENCES tool_calls(tool_call_id) ON DELETE CASCADE,
  result_json jsonb,
  evidence_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  output_hash char(64),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE evidence_items (
  evidence_item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  case_id uuid NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
  run_id uuid REFERENCES agent_runs(run_id),
  source_type text NOT NULL,
  source_id uuid,
  source_locator jsonb,
  claim text NOT NULL,
  confidence numeric(5,4),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE approval_tasks (
  approval_task_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  case_id uuid NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
  run_id uuid NOT NULL REFERENCES agent_runs(run_id),
  task_type text NOT NULL,
  status approval_status NOT NULL DEFAULT 'PENDING',
  assigned_role text,
  assigned_user_id uuid REFERENCES users(user_id),
  proposed_action jsonb NOT NULL,
  evidence_packet jsonb NOT NULL,
  evidence_hash char(64) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz,
  completed_at timestamptz
);
CREATE INDEX approval_tasks_queue_idx ON approval_tasks (tenant_id, status, created_at);

CREATE TABLE approval_decisions (
  approval_decision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  approval_task_id uuid NOT NULL REFERENCES approval_tasks(approval_task_id) ON DELETE CASCADE,
  decided_by uuid NOT NULL REFERENCES users(user_id),
  decision approval_status NOT NULL,
  edited_payload jsonb,
  comment text,
  evidence_hash char(64) NOT NULL,
  decided_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE human_feedback (
  feedback_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  case_id uuid NOT NULL REFERENCES cases(case_id),
  run_id uuid REFERENCES agent_runs(run_id),
  user_id uuid NOT NULL REFERENCES users(user_id),
  feedback_type text NOT NULL,
  rating integer,
  comment text,
  accepted_recommendation boolean,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit_logs (
  audit_log_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  case_id uuid REFERENCES cases(case_id),
  run_id uuid REFERENCES agent_runs(run_id),
  actor_type text NOT NULL,
  actor_id text,
  action text NOT NULL,
  resource_type text NOT NULL,
  resource_id text,
  request_id text,
  ip_address inet,
  user_agent text,
  before_hash char(64),
  after_hash char(64),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_logs_case_idx ON audit_logs (tenant_id, case_id, created_at DESC);

-- AP extension
CREATE TABLE purchase_orders (
  purchase_order_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  vendor_id uuid NOT NULL REFERENCES vendors(vendor_id),
  po_number text NOT NULL,
  currency char(3) NOT NULL,
  total_amount numeric(18,2) NOT NULL,
  status text NOT NULL,
  order_date date,
  raw_source jsonb,
  UNIQUE (tenant_id, po_number)
);

CREATE TABLE purchase_order_lines (
  po_line_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  purchase_order_id uuid NOT NULL REFERENCES purchase_orders(purchase_order_id) ON DELETE CASCADE,
  line_number integer NOT NULL,
  description text,
  quantity numeric(18,4),
  unit_price numeric(18,4),
  tax_amount numeric(18,2),
  UNIQUE (purchase_order_id, line_number)
);

CREATE TABLE goods_receipts (
  goods_receipt_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  purchase_order_id uuid NOT NULL REFERENCES purchase_orders(purchase_order_id),
  receipt_number text NOT NULL,
  received_at timestamptz,
  status text NOT NULL,
  UNIQUE (tenant_id, receipt_number)
);

CREATE TABLE invoices (
  invoice_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  vendor_id uuid NOT NULL REFERENCES vendors(vendor_id),
  purchase_order_id uuid REFERENCES purchase_orders(purchase_order_id),
  invoice_number text NOT NULL,
  currency char(3) NOT NULL,
  total_amount numeric(18,2) NOT NULL,
  tax_amount numeric(18,2),
  status text NOT NULL,
  received_at timestamptz,
  UNIQUE (tenant_id, vendor_id, invoice_number)
);

CREATE TABLE invoice_lines (
  invoice_line_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  invoice_id uuid NOT NULL REFERENCES invoices(invoice_id) ON DELETE CASCADE,
  line_number integer NOT NULL,
  po_line_id uuid REFERENCES purchase_order_lines(po_line_id),
  description text,
  quantity numeric(18,4),
  unit_price numeric(18,4),
  tax_amount numeric(18,2),
  UNIQUE (invoice_id, line_number)
);

CREATE TABLE invoice_exceptions (
  invoice_exception_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  case_id uuid NOT NULL REFERENCES cases(case_id),
  invoice_id uuid NOT NULL REFERENCES invoices(invoice_id),
  exception_type text NOT NULL,
  severity text NOT NULL,
  details jsonb NOT NULL,
  recommended_resolution jsonb,
  status text NOT NULL DEFAULT 'OPEN',
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz
);

-- Model and evaluation governance
CREATE TABLE model_registry (
  model_registry_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  model_name text NOT NULL,
  provider text NOT NULL,
  version text NOT NULL,
  purpose text NOT NULL,
  config jsonb NOT NULL DEFAULT '{}'::jsonb,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (model_name, version, purpose)
);

CREATE TABLE prompt_versions (
  prompt_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  prompt_name text NOT NULL,
  version text NOT NULL,
  content_hash char(64) NOT NULL,
  content text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (prompt_name, version)
);

CREATE TABLE evaluation_runs (
  evaluation_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  model_registry_id uuid REFERENCES model_registry(model_registry_id),
  prompt_version_id uuid REFERENCES prompt_versions(prompt_version_id),
  dataset_name text NOT NULL,
  metrics jsonb NOT NULL,
  status text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Row-Level Security
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'users','roles','user_roles','tenant_settings','integrations','vendors','vendor_aliases',
    'vendor_bank_accounts','cases','case_events','case_comments','documents','document_pages',
    'document_chunks','extracted_fields','policy_documents','policy_versions','policy_chunks',
    'duplicate_candidates','risk_checks','agent_runs','agent_steps','tool_calls','tool_results',
    'evidence_items','approval_tasks','approval_decisions','human_feedback','audit_logs',
    'purchase_orders','purchase_order_lines','goods_receipts','invoices','invoice_lines',
    'invoice_exceptions'
  ]
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation_%I ON %I USING (tenant_id = current_setting(''app.current_tenant_id'', true)::uuid) WITH CHECK (tenant_id = current_setting(''app.current_tenant_id'', true)::uuid)',
      t, t
    );
  END LOOP;
END $$;
