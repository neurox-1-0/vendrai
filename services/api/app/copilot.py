import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from app.auth import Principal

HELP_PACK_VERSION = "2026.07.25.1"


@dataclass(frozen=True)
class SafeAction:
    action_id: str
    action_type: Literal[
        "NAVIGATE",
        "SPOTLIGHT",
        "OPEN_PANEL",
        "SET_FILTER",
        "START_TOUR",
    ]
    target: str
    label: str
    roles: frozenset[str]


@dataclass(frozen=True)
class HelpEntry:
    source_id: str
    title: str
    content: str
    keywords: frozenset[str]
    routes: tuple[str, ...]
    roles: frozenset[str]
    action_ids: tuple[str, ...] = ()


ALL_USER_ROLES = frozenset(
    {
        "requester",
        "analyst",
        "approver",
        "procurement_approver",
        "compliance_approver",
        "finance_approver",
        "auditor",
        "admin",
    }
)
CASE_CREATOR_ROLES = frozenset({"requester", "analyst", "admin"})
REVIEW_ROLES = frozenset(
    {
        "analyst",
        "approver",
        "procurement_approver",
        "compliance_approver",
        "finance_approver",
        "auditor",
        "admin",
    }
)

SAFE_ACTIONS = {
    action.action_id: action
    for action in (
        SafeAction(
            "go_dashboard",
            "NAVIGATE",
            "/",
            "Open the work dashboard",
            ALL_USER_ROLES,
        ),
        SafeAction(
            "start_supplier",
            "NAVIGATE",
            "/cases/new",
            "Start supplier onboarding",
            CASE_CREATOR_ROLES,
        ),
        SafeAction(
            "start_invoice",
            "NAVIGATE",
            "/invoices/new",
            "Start an invoice exception",
            CASE_CREATOR_ROLES,
        ),
        SafeAction(
            "open_approvals",
            "NAVIGATE",
            "/approvals",
            "Open pending human reviews",
            REVIEW_ROLES,
        ),
        SafeAction(
            "open_admin_health",
            "NAVIGATE",
            "/admin",
            "Open integration health",
            frozenset({"admin"}),
        ),
        SafeAction(
            "show_agent_map",
            "SPOTLIGHT",
            "case.agent-map",
            "Show the agent execution map",
            ALL_USER_ROLES,
        ),
        SafeAction(
            "show_document_review",
            "SPOTLIGHT",
            "case.document-review",
            "Show extracted document fields",
            ALL_USER_ROLES,
        ),
        SafeAction(
            "show_clarification",
            "SPOTLIGHT",
            "case.clarification",
            "Show the clarification task",
            ALL_USER_ROLES,
        ),
        SafeAction(
            "show_evidence",
            "SPOTLIGHT",
            "case.evidence",
            "Show the evidence and citations",
            ALL_USER_ROLES,
        ),
        SafeAction(
            "start_case_tour",
            "START_TOUR",
            "case.review-tour",
            "Guide me through this case",
            ALL_USER_ROLES,
        ),
        SafeAction(
            "open_notifications",
            "OPEN_PANEL",
            "notifications",
            "Open notifications",
            ALL_USER_ROLES,
        ),
    )
}

HELP_ENTRIES = (
    HelpEntry(
        "getting-started",
        "Start a real workflow",
        (
            "Supplier onboarding starts by creating a case, uploading synthetic "
            "supporting documents, waiting for malware scan and extraction, "
            "then submitting the case. Invoice exceptions start from the invoice "
            "form and follow document extraction, PO/GRN checks and review."
        ),
        frozenset(
            {
                "start",
                "create",
                "supplier",
                "vendor",
                "invoice",
                "upload",
                "workflow",
            }
        ),
        ("/", "/cases/new", "/invoices/new"),
        CASE_CREATOR_ROLES,
        ("start_supplier", "start_invoice"),
    ),
    HelpEntry(
        "agent-autonomy",
        "How the agent is autonomous",
        (
            "A bounded Gemini planner receives a goal and non-sensitive observable "
            "facts, selects only server-registered capabilities, and explains why. "
            "The server validates mandatory tools and dependencies before execution. "
            "Independent specialists run concurrently, while deterministic controls "
            "retain authority over sanctions, approvals, tenant access and ERP writes."
        ),
        frozenset(
            {
                "agent",
                "autonomous",
                "planner",
                "tool",
                "parallel",
                "decision",
                "reasoning",
            }
        ),
        ("/cases/",),
        ALL_USER_ROLES,
        ("show_agent_map",),
    ),
    HelpEntry(
        "execution-map",
        "Read the execution map",
        (
            "The execution map is generated from persisted run steps. It shows the "
            "selected path, tool dependencies, attempts, measured latency, critical "
            "path and time saved by parallel execution. It exposes structured "
            "conclusions and reason codes, never private chain-of-thought."
        ),
        frozenset(
            {
                "execution",
                "path",
                "latency",
                "performance",
                "parallel",
                "trace",
                "step",
            }
        ),
        ("/cases/",),
        ALL_USER_ROLES,
        ("show_agent_map",),
    ),
    HelpEntry(
        "human-control",
        "Human-in-the-loop controls",
        (
            "Possible duplicates, sanctions candidates, bank-detail changes and final "
            "ERP actions require the appropriate signed human decision. Reviews are "
            "evidence-hash and case-version bound, so stale or replayed decisions are "
            "rejected. The copilot can explain or navigate but cannot decide."
        ),
        frozenset(
            {
                "approve",
                "approval",
                "review",
                "human",
                "hitl",
                "override",
                "reject",
            }
        ),
        ("/approvals", "/cases/"),
        ALL_USER_ROLES,
        ("open_approvals", "show_evidence"),
    ),
    HelpEntry(
        "clarification",
        "Resolve missing or contradictory evidence",
        (
            "When required evidence is missing or contradictory, the workflow creates "
            "a durable clarification task instead of guessing. Answer the listed "
            "questions or correct an extracted field; the case resumes from its "
            "checkpoint and re-verifies evidence."
        ),
        frozenset(
            {
                "clarification",
                "missing",
                "contradiction",
                "correct",
                "field",
                "resume",
            }
        ),
        ("/cases/",),
        ALL_USER_ROLES,
        ("show_clarification", "show_document_review"),
    ),
    HelpEntry(
        "failure-recovery",
        "Failure isolation and recovery",
        (
            "Retryable provider failures preserve completed deterministic work and "
            "show a reason code. Notification delivery retries independently and "
            "never changes case progression. Mandatory evidence, sanctions, approval "
            "or ERP confirmation failures block only the unsafe transition."
        ),
        frozenset(
            {
                "failed",
                "failure",
                "retry",
                "blocked",
                "email",
                "notification",
                "quota",
                "recover",
            }
        ),
        ("/cases/", "/admin"),
        ALL_USER_ROLES,
        ("show_agent_map", "open_notifications"),
    ),
    HelpEntry(
        "privacy-security",
        "Privacy and security boundaries",
        (
            "Documents remain in quarantine/private storage and are scanned locally. "
            "PII is detected and tokenized before external reasoning. Tenant context "
            "is enforced in API authorization and PostgreSQL RLS. Gemini never "
            "receives raw documents, bank details, tax identifiers or credentials."
        ),
        frozenset(
            {
                "privacy",
                "security",
                "pii",
                "tenant",
                "gemini",
                "document",
                "mask",
            }
        ),
        ("/cases/", "/admin"),
        ALL_USER_ROLES,
        ("show_document_review",),
    ),
    HelpEntry(
        "judge-diagnostics",
        "Judge-safe technical diagnostics",
        (
            "Auditors and administrators can open a sanitized diagnostics drawer on "
            "the execution map. It shows graph/model/prompt versions, integrity "
            "hashes, attempts and measured timings without secrets, SQL, raw OCR, "
            "sensitive identifiers or chain-of-thought."
        ),
        frozenset(
            {
                "judge",
                "diagnostic",
                "console",
                "technical",
                "version",
                "hash",
                "performance",
            }
        ),
        ("/cases/",),
        frozenset({"auditor", "admin"}),
        ("show_agent_map", "open_admin_health"),
    ),
)


class CopilotDraft(BaseModel):
    answer: str = Field(min_length=4, max_length=1800)
    citation_ids: list[str] = Field(default_factory=list, max_length=5)
    requested_action_ids: list[str] = Field(default_factory=list, max_length=4)


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 1
    }


def retrieve_help(
    question: str,
    current_path: str,
    principal: Principal,
    *,
    limit: int = 4,
) -> list[HelpEntry]:
    query_tokens = _tokens(question)
    scored: list[tuple[int, HelpEntry]] = []
    for entry in HELP_ENTRIES:
        if not principal.roles.intersection(entry.roles):
            continue
        overlap = len(query_tokens.intersection(entry.keywords))
        route_bonus = 3 if any(
            current_path.startswith(route) for route in entry.routes
        ) else 0
        title_overlap = len(query_tokens.intersection(_tokens(entry.title)))
        score = overlap * 4 + title_overlap * 2 + route_bonus
        scored.append((score, entry))
    scored.sort(key=lambda item: (-item[0], item[1].source_id))
    selected = [entry for score, entry in scored if score > 0][:limit]
    if selected:
        return selected
    return [
        entry
        for _, entry in scored
        if entry.source_id in {"getting-started", "agent-autonomy"}
    ][:limit]


def allowed_actions(
    entries: list[HelpEntry],
    principal: Principal,
) -> dict[str, SafeAction]:
    action_ids = {
        action_id
        for entry in entries
        for action_id in entry.action_ids
    }
    return {
        action_id: SAFE_ACTIONS[action_id]
        for action_id in sorted(action_ids)
        if principal.roles.intersection(SAFE_ACTIONS[action_id].roles)
    }


def attempts_business_mutation(question: str) -> bool:
    normalized = question.lower()
    patterns = (
        r"\bapprove\b",
        r"\breject\b",
        r"\bsubmit\b",
        r"\bcancel\b",
        r"\bcreate\s+(the\s+)?vendor\b",
        r"\bchange\s+(the\s+)?bank\b",
        r"\bmark\s+.*\b(pass|clear|paid)\b",
        r"\bresolve\s+(the\s+)?sanctions\b",
    )
    return any(re.search(pattern, normalized) for pattern in patterns)
