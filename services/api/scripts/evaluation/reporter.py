"""Render an evidence-linked evaluation report.

Every score traces back to the cases that produced it, and the report records
the commit SHA, model version, and dataset versions so a number can be
reproduced rather than merely quoted.

**Publish the numbers that come out.** If field F1 is 0.62, the report says
0.62. A credible mediocre number is worth more than an unverifiable good one,
and claims outrunning evidence is the criticism this whole phase exists to
answer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.evaluation.scorer import CaseOutcome, RunScore


@dataclass(frozen=True)
class RunProvenance:
    commit_sha: str
    model_version: str
    manifest_digest: str
    corpus_version: str
    started_at: str
    finished_at: str

    def as_dict(self) -> dict[str, str]:
        return {
            "commit_sha": self.commit_sha,
            "model_version": self.model_version,
            "manifest_digest": self.manifest_digest,
            "corpus_version": self.corpus_version,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


def _percent(value: float | None) -> str:
    return "not measured" if value is None else f"{value * 100:.1f}%"


def _ratio(metric: dict[str, Any]) -> str:
    if metric["total"] == 0:
        return "not measured"
    return f"{_percent(metric['value'])} ({metric['matched']}/{metric['total']})"


def render_markdown(
    score: RunScore,
    outcomes: list[CaseOutcome],
    provenance: RunProvenance,
) -> str:
    lines: list[str] = [
        "# NeuroX evaluation report",
        "",
        f"**Generated:** {datetime.now(UTC).isoformat()}",
        f"**Commit:** `{provenance.commit_sha}`",
        f"**Model:** {provenance.model_version}",
        f"**Manifest digest:** `{provenance.manifest_digest}`",
        f"**Corpus:** {provenance.corpus_version}",
        f"**Run window:** {provenance.started_at} to {provenance.finished_at}",
        "",
        "These are the measured numbers. Where a metric reads *not measured*, "
        "no case in the run exercised it - that is reported rather than "
        "rounded to zero, because zero would be a much stronger claim.",
        "",
        "## Aggregate",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Cases in manifest | {score.overall.cases} |",
        f"| Cases executed | {score.overall.executed} |",
        f"| Status accuracy | {_ratio(score.overall.status_accuracy.as_dict())} |",
        f"| Reason-code F1 | {_percent(score.overall.reason_code_f1.value)} |",
        f"| Field macro-F1 | {_percent(score.field_macro_f1)} |",
        f"| Duplicate recall | {_ratio(score.overall.duplicate_recall.as_dict())} |",
        f"| Duplicate exact match | {_ratio(score.overall.duplicate_exact_match.as_dict())} |",
        f"| Policy Recall@10 | {_ratio(score.overall.policy_recall_at_10.as_dict())} |",
        f"| Citation precision | {_ratio(score.overall.citation_precision.as_dict())} |",
        f"| Cross-tenant leakage | {score.cross_tenant_leaks} |",
        "",
    ]

    if score.cross_tenant_leaks:
        lines.extend(
            [
                "> **Cross-tenant leakage is not zero.** This is a release "
                "blocker, not a metric to trend. Every other number below is "
                "secondary to it.",
                "",
            ]
        )

    if score.not_executed:
        lines.extend(
            [
                f"## Not executed ({len(score.not_executed)})",
                "",
                "These cases did not produce a result, usually because the run "
                "paused on provider quota. They are excluded from every metric "
                "rather than counted as failures.",
                "",
                "```",
                "\n".join(score.not_executed),
                "```",
                "",
            ]
        )

    lines.extend(
        [
            "## Per scenario",
            "",
            "An aggregate can hide a scenario that fails completely, so every "
            "metric is also reported per scenario.",
            "",
            "| Scenario | Cases | Executed | Status | Reason-code F1 | Recall@10 |",
            "|---|---|---|---|---|---|",
        ]
    )
    for name, scenario in sorted(score.per_scenario.items()):
        lines.append(
            f"| {name} | {scenario.cases} | {scenario.executed} | "
            f"{_ratio(scenario.status_accuracy.as_dict())} | "
            f"{_percent(scenario.reason_code_f1.value)} | "
            f"{_ratio(scenario.policy_recall_at_10.as_dict())} |"
        )

    lines.extend(["", "## Case detail", "", "| Case | Scenario | Status | Reason codes |", "|---|---|---|---|"])
    for outcome in outcomes:
        reasons = ", ".join(outcome.reason_codes) or "-"
        status = outcome.status or (
            "quota paused" if outcome.quota_exhausted else outcome.error or "not run"
        )
        lines.append(
            f"| `{outcome.case_id}` | {outcome.scenario} | {status} | {reasons} |"
        )

    lines.append("")
    return "\n".join(lines)


def write_report(
    directory: Path,
    score: RunScore,
    outcomes: list[CaseOutcome],
    provenance: RunProvenance,
) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    markdown_path = directory / "evaluation-report.md"
    json_path = directory / "evaluation-report.json"

    markdown_path.write_text(
        render_markdown(score, outcomes, provenance), encoding="utf-8"
    )
    json_path.write_text(
        json.dumps(
            {
                "provenance": provenance.as_dict(),
                "scores": score.as_dict(),
                "cases": [
                    {
                        "case_id": outcome.case_id,
                        "scenario": outcome.scenario,
                        "workflow": outcome.workflow,
                        "status": outcome.status,
                        "reason_codes": outcome.reason_codes,
                        "policy_citations": outcome.policy_citations,
                        "error": outcome.error,
                        "quota_exhausted": outcome.quota_exhausted,
                    }
                    for outcome in outcomes
                ],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return markdown_path, json_path
