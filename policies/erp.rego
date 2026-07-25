package neurox.erp

import rego.v1

default allow := false

allow if {
  input.tenant_id != ""
  input.case_status == "ERP_SYNC_PENDING"
  input.approval_status == "APPROVED"
  input.approver_user_id != ""
  input.approval_evidence_hash == input.current_evidence_hash
  input.requester_user_id != input.approver_user_id
  input.case_version >= input.approval_case_version
  input.deterministic_verified == true
  input.required_controls_resolved == true
  input.case_type != "VENDOR_ONBOARDING"
}

allow if {
  input.tenant_id != ""
  input.case_status == "ERP_SYNC_PENDING"
  input.approval_status == "APPROVED"
  input.approver_user_id != ""
  input.approval_evidence_hash == input.current_evidence_hash
  input.requester_user_id != input.approver_user_id
  input.case_version >= input.approval_case_version
  input.deterministic_verified == true
  input.required_controls_resolved == true
  input.case_type == "VENDOR_ONBOARDING"
  input.sanctions_cleared == true
}

deny_reasons contains "ERP_STATE_INVALID" if input.case_status != "ERP_SYNC_PENDING"
deny_reasons contains "APPROVAL_REQUIRED" if input.approval_status != "APPROVED"
deny_reasons contains "APPROVAL_DECISION_MISSING" if input.approver_user_id == ""
deny_reasons contains "EVIDENCE_CHANGED" if input.approval_evidence_hash != input.current_evidence_hash
deny_reasons contains "SEGREGATION_OF_DUTIES" if input.requester_user_id == input.approver_user_id
deny_reasons contains "STALE_APPROVAL" if input.case_version < input.approval_case_version
deny_reasons contains "EVIDENCE_NOT_VERIFIED" if input.deterministic_verified != true
deny_reasons contains "CONTROL_REVIEW_REQUIRED" if input.required_controls_resolved != true
deny_reasons contains "SANCTIONS_NOT_CLEARED" if {
  input.case_type == "VENDOR_ONBOARDING"
  input.sanctions_cleared != true
}

decision := {
  "allow": allow,
  "deny_reasons": sort([reason | deny_reasons[reason]]),
}
