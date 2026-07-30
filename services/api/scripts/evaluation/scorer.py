"""Score recorded evaluation outputs against the shipped oracle.

A pure function over recorded outputs, with no network and no database. That
separation is deliberate: scoring gets re-run far more often than execution -
after a scoring bug, after a metric definition changes, after a fix - and
re-running 100 live LLM workflows to recompute an F1 would make the harness
unusable.

Every metric is reported **per scenario as well as aggregate**. An 85%
aggregate hiding a 30% PROMPT_INJECTION score is not useful information.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CaseOutcome:
    """One executed case, as recorded by the runner."""

    case_id: str
    scenario: str
    workflow: str
    base_scenario: str
    status: str | None = None
    reason_codes: list[str] = field(default_factory=list)
    extracted_fields: dict[str, str] = field(default_factory=dict)
    duplicate_candidates: list[dict[str, Any]] = field(default_factory=list)
    policy_citations: list[str] = field(default_factory=list)
    cited_clause_supports_finding: dict[str, bool] = field(default_factory=dict)
    error: str | None = None
    quota_exhausted: bool = False

    @property
    def executed(self) -> bool:
        return self.error is None and not self.quota_exhausted


@dataclass
class Metric:
    """A ratio, kept as its numerator and denominator.

    Reporting 0/0 as 0.0 would let an unexecuted scenario look like a failing
    one, which is a different and much more alarming claim.
    """

    matched: int = 0
    total: int = 0

    @property
    def value(self) -> float | None:
        return self.matched / self.total if self.total else None

    def observe(self, correct: bool) -> None:
        self.total += 1
        self.matched += int(correct)

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "matched": self.matched,
            "total": self.total,
        }


@dataclass
class F1:
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0

    @property
    def precision(self) -> float | None:
        denominator = self.true_positives + self.false_positives
        return self.true_positives / denominator if denominator else None

    @property
    def recall(self) -> float | None:
        denominator = self.true_positives + self.false_negatives
        return self.true_positives / denominator if denominator else None

    @property
    def value(self) -> float | None:
        precision, recall = self.precision, self.recall
        if precision is None or recall is None or precision + recall == 0:
            return None
        return 2 * precision * recall / (precision + recall)

    def observe(self, expected: set[str], actual: set[str]) -> None:
        self.true_positives += len(expected & actual)
        self.false_positives += len(actual - expected)
        self.false_negatives += len(expected - actual)

    def as_dict(self) -> dict[str, Any]:
        return {
            "f1": self.value,
            "precision": self.precision,
            "recall": self.recall,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
        }


@dataclass
class ScenarioScore:
    scenario: str
    cases: int = 0
    executed: int = 0
    status_accuracy: Metric = field(default_factory=Metric)
    reason_code_f1: F1 = field(default_factory=F1)
    duplicate_recall: Metric = field(default_factory=Metric)
    duplicate_exact_match: Metric = field(default_factory=Metric)
    policy_recall_at_10: Metric = field(default_factory=Metric)
    citation_precision: Metric = field(default_factory=Metric)

    def as_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "cases": self.cases,
            "executed": self.executed,
            "status_accuracy": self.status_accuracy.as_dict(),
            "reason_codes": self.reason_code_f1.as_dict(),
            "duplicate_recall": self.duplicate_recall.as_dict(),
            "duplicate_exact_match": self.duplicate_exact_match.as_dict(),
            "policy_recall_at_10": self.policy_recall_at_10.as_dict(),
            "citation_precision": self.citation_precision.as_dict(),
        }


# The product's own case statuses, mapped to the vocabulary the corpus oracle
# uses. Two different vocabularies describing the same state is a documentation
# problem, not a scoring one - but the mapping has to live somewhere explicit
# rather than being guessed at scoring time.
STATUS_EQUIVALENCE: dict[str, set[str]] = {
    "READY_FOR_APPROVAL": {"APPROVAL_PENDING"},
    "READY_FOR_AP_APPROVAL": {"APPROVAL_PENDING"},
    "HUMAN_REVIEW_REQUIRED": {"DUPLICATE_REVIEW", "RISK_REVIEW"},
    "ENHANCED_REVIEW_REQUIRED": {"RISK_REVIEW"},
    "CLARIFICATION_REQUIRED": {"NEEDS_CLARIFICATION"},
    "PROCUREMENT_REVIEW_REQUIRED": {"RISK_REVIEW", "HOLD"},
    "TAX_REVIEW_REQUIRED": {"RISK_REVIEW", "HOLD"},
    "BLOCKED_DUPLICATE": {"BLOCKED_DUPLICATE"},
    "HOLD": {"HOLD"},
}


def status_matches(expected: str, actual: str | None) -> bool:
    if actual is None:
        return False
    if expected == actual:
        return True
    return actual in STATUS_EQUIVALENCE.get(expected, set())


@dataclass
class RunScore:
    per_scenario: dict[str, ScenarioScore]
    overall: ScenarioScore
    field_macro_f1: float | None
    cross_tenant_leaks: int
    not_executed: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall.as_dict(),
            "field_macro_f1": self.field_macro_f1,
            "cross_tenant_leaks": self.cross_tenant_leaks,
            "not_executed": self.not_executed,
            "per_scenario": {
                name: score.as_dict()
                for name, score in sorted(self.per_scenario.items())
            },
        }


def score_run(
    outcomes: list[CaseOutcome],
    oracle: dict[str, dict],
    *,
    expected_reason_codes: dict[str, list[str]],
    ground_truth_fields: dict[str, dict[str, str]] | None = None,
    cross_tenant_leaks: int = 0,
) -> RunScore:
    """Score every recorded outcome. Pure - no I/O, no clock, no network."""
    per_scenario: dict[str, ScenarioScore] = defaultdict(
        lambda: ScenarioScore(scenario="")
    )
    overall = ScenarioScore(scenario="ALL")
    field_scores: dict[str, F1] = defaultdict(F1)
    not_executed: list[str] = []

    for outcome in outcomes:
        score = per_scenario[outcome.scenario]
        score.scenario = outcome.scenario
        score.cases += 1
        overall.cases += 1

        if not outcome.executed:
            not_executed.append(outcome.case_id)
            continue
        score.executed += 1
        overall.executed += 1

        expectation = oracle.get(outcome.base_scenario, {})

        expected_status = expectation.get("expected_status")
        if expected_status:
            correct = status_matches(expected_status, outcome.status)
            score.status_accuracy.observe(correct)
            overall.status_accuracy.observe(correct)

        expected_codes = set(expected_reason_codes.get(outcome.case_id, []))
        actual_codes = set(outcome.reason_codes)
        if expected_codes or actual_codes:
            score.reason_code_f1.observe(expected_codes, actual_codes)
            overall.reason_code_f1.observe(expected_codes, actual_codes)

        _score_duplicates(outcome, expectation, score, overall)
        _score_policy(outcome, score, overall)

        for field_name, truth in (ground_truth_fields or {}).get(
            outcome.case_id, {}
        ).items():
            extracted = outcome.extracted_fields.get(field_name)
            field_scores[field_name].observe(
                {truth} if truth else set(),
                {extracted} if extracted else set(),
            )

    macro_values = [
        score.value for score in field_scores.values() if score.value is not None
    ]
    return RunScore(
        per_scenario=dict(per_scenario),
        overall=overall,
        field_macro_f1=(
            sum(macro_values) / len(macro_values) if macro_values else None
        ),
        cross_tenant_leaks=cross_tenant_leaks,
        not_executed=not_executed,
    )


def _score_duplicates(
    outcome: CaseOutcome,
    expectation: dict,
    score: ScenarioScore,
    overall: ScenarioScore,
) -> None:
    findings = " ".join(expectation.get("findings", [])).lower()
    duplicate_expected = "duplicate" in findings or "match to existing vendor" in findings
    if not duplicate_expected:
        return

    detected = bool(outcome.duplicate_candidates)
    score.duplicate_recall.observe(detected)
    overall.duplicate_recall.observe(detected)
    if not detected:
        return

    # The corpus names the vendor a duplicate should resolve to, e.g. V000233.
    expected_vendor = next(
        (
            token
            for token in findings.replace(",", " ").split()
            if token.upper().startswith("V0") and token[1:].isdigit()
        ),
        None,
    )
    if expected_vendor is None:
        return
    strongest = max(
        outcome.duplicate_candidates,
        key=lambda item: float(item.get("score", 0)),
    )
    matched = expected_vendor.upper() in str(
        strongest.get("erp_vendor_id") or strongest.get("name", "")
    ).upper()
    score.duplicate_exact_match.observe(matched)
    overall.duplicate_exact_match.observe(matched)


def _score_policy(
    outcome: CaseOutcome,
    score: ScenarioScore,
    overall: ScenarioScore,
) -> None:
    # Recall@10: did retrieval surface any clause at all for a case whose
    # outcome depends on policy? Every scenario's outcome does.
    retrieved = bool(outcome.policy_citations[:10])
    score.policy_recall_at_10.observe(retrieved)
    overall.policy_recall_at_10.observe(retrieved)

    for citation, supports in outcome.cited_clause_supports_finding.items():
        del citation
        score.citation_precision.observe(supports)
        overall.citation_precision.observe(supports)
