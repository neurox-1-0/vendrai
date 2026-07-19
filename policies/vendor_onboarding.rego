package neurox.vendor_onboarding

import rego.v1

default allow := false

allow if {
  input.tenant_id != ""
  input.sanctions_status == "PASS"
  input.evidence_verified == true
  input.approval.status == "APPROVED"
  input.approval.requester_user_id != input.approval.approver_user_id
  input.approval.evidence_hash == input.current_evidence_hash
  input.approval.case_version == input.case_version
}

deny_reason contains "SANCTIONS_NOT_CLEARED" if input.sanctions_status != "PASS"
deny_reason contains "EVIDENCE_NOT_VERIFIED" if input.evidence_verified != true
deny_reason contains "APPROVAL_REQUIRED" if input.approval.status != "APPROVED"
deny_reason contains "SEGREGATION_OF_DUTIES" if input.approval.requester_user_id == input.approval.approver_user_id
deny_reason contains "STALE_APPROVAL" if input.approval.case_version != input.case_version

