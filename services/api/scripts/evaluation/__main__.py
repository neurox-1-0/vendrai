"""``python -m scripts.evaluation`` - run and score the 100-case suite.

Stages are separately invocable, because they have very different costs:

    python -m scripts.evaluation materialize    # deterministic, seconds
    python -m scripts.evaluation run            # live, hours, resumable
    python -m scripts.evaluation score          # pure, instant
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
from app.config import settings

from scripts.bootstrap.api_client import AdminApiClient
from scripts.evaluation.manifest import (
    ManifestError,
    load_manifest,
    load_oracle,
    verify_manifest_digest,
)
from scripts.evaluation.materializer import materialize_manifest
from scripts.evaluation.reporter import RunProvenance, write_report
from scripts.evaluation.runner import (
    Checkpoint,
    QuotaExhausted,
    RunnerConfig,
    await_outcome,
    outcome_from_detail,
    resolve_human_task,
    submit_case,
)
from scripts.evaluation.scorer import CaseOutcome, score_run

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
MANIFEST = REPOSITORY_ROOT / "evaluation" / "cases.jsonl"
DIGEST = REPOSITORY_ROOT / "evaluation" / "manifest.sha256"
ORACLE = (
    REPOSITORY_ROOT
    / "Vendrai_Procurement_Document_Corpus_v2"
    / "ground_truth"
    / "expected_case_outcomes.json"
)
DEFAULT_WORKSPACE = REPOSITORY_ROOT / ".data" / "evaluation"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m scripts.evaluation")
    parser.add_argument(
        "stage", choices=["materialize", "run", "score"], help="Which stage to run."
    )
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    parser.add_argument(
        "--limit", type=int, default=0, help="Run only the first N cases."
    )
    parser.add_argument(
        "--scenario", default="", help="Restrict to one scenario, e.g. DUPLICATE."
    )
    parser.add_argument(
        "--tenant-id",
        default="",
        help=(
            "Tenant to run against. Defaults to a fresh per-run tenant so "
            "evaluation data never contaminates demo data."
        ),
    )
    parser.add_argument("--resume", action="store_true", help="Continue a paused run.")
    return parser.parse_args(argv)


def _commit_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _selected(cases, args):
    if args.scenario:
        cases = [case for case in cases if case.scenario == args.scenario]
    if args.limit:
        cases = cases[: args.limit]
    return cases


def do_materialize(args: argparse.Namespace) -> int:
    cases = _selected(load_manifest(MANIFEST), args)
    materialized = materialize_manifest(
        cases,
        repository_root=REPOSITORY_ROOT,
        cache_root=args.workspace / "documents",
        artifact_manifest=args.workspace / "artifacts.json",
    )
    total = sum(len(item.documents) for item in materialized)
    print(f"Materialized {len(materialized)} cases, {total} documents.")
    print(f"Artifact manifest: {args.workspace / 'artifacts.json'}")
    return 0


async def do_run(args: argparse.Namespace) -> int:
    digest = verify_manifest_digest(MANIFEST, DIGEST)
    cases = _selected(load_manifest(MANIFEST), args)
    materialized = {
        item.case_id: item
        for item in materialize_manifest(
            cases,
            repository_root=REPOSITORY_ROOT,
            cache_root=args.workspace / "documents",
        )
    }

    checkpoint_path = args.workspace / "checkpoint.json"
    checkpoint = Checkpoint.load(checkpoint_path) if args.resume else None
    if checkpoint is None:
        # A dedicated tenant per run keeps evaluation data out of the demo
        # tenant, and makes cross-tenant leakage measurable rather than
        # theoretical.
        tenant_id = args.tenant_id or str(uuid.uuid4())
        checkpoint = Checkpoint(run_id=str(uuid.uuid4()), tenant_id=tenant_id)
    tenant_id = uuid.UUID(checkpoint.tenant_id)

    started_at = datetime.now(UTC).isoformat()
    consecutive_quota = 0
    config = RunnerConfig(
        api_url=settings.BOOTSTRAP_API_URL,
        tenant_id=tenant_id,
        headers={},
    )

    async with AdminApiClient(tenant_id) as api:
        await api.wait_until_available()
        client = api.client
        for case in cases:
            if case.case_id in checkpoint.completed:
                continue
            if consecutive_quota >= config.quota_patience:
                print(
                    f"Pausing: {consecutive_quota} consecutive quota refusals. "
                    f"Resume with --resume once quota returns.",
                    file=sys.stderr,
                )
                break
            record = await _execute_case(client, case, materialized, config)
            checkpoint.completed[case.case_id] = record
            checkpoint.save(checkpoint_path)
            consecutive_quota = (
                consecutive_quota + 1 if record.get("quota_exhausted") else 0
            )
            print(
                f"{case.case_id}: {record.get('status') or record.get('error')}",
                flush=True,
            )

    (args.workspace / "run-window.json").write_text(
        json.dumps(
            {
                "started_at": started_at,
                "finished_at": datetime.now(UTC).isoformat(),
                "manifest_digest": digest,
                "tenant_id": str(tenant_id),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    executed = sum(
        1 for record in checkpoint.completed.values() if record.get("status")
    )
    print(f"{executed}/{len(cases)} cases executed. Score with: score")
    return 0


async def _execute_case(client, case, materialized, config) -> dict:
    try:
        case_id = await submit_case(client, case, materialized[case.case_id], config)
        detail = await await_outcome(client, case_id, config)
        # Pass the human gate deterministically rather than skipping it, so
        # what is measured is still a system with a human control in it.
        await resolve_human_task(client, case_id, detail, approve=True)
        evidence = (await client.get(f"/cases/{case_id}/evidence")).json()
        outcome = outcome_from_detail(case, detail, evidence)
        return {
            "case_id": case_id,
            "status": outcome.status,
            "reason_codes": outcome.reason_codes,
            "policy_citations": outcome.policy_citations,
            "duplicate_candidates": outcome.duplicate_candidates,
            "human_task_auto_resolved": True,
        }
    except QuotaExhausted as error:
        # A pause, not a failure. Recording it distinctly keeps the report
        # from describing an operational limit as a product defect.
        return {"quota_exhausted": True, "error": str(error)}
    except (httpx.HTTPError, TimeoutError, KeyError) as error:
        return {"error": f"{type(error).__name__}: {error}"}


def do_score(args: argparse.Namespace) -> int:
    checkpoint = Checkpoint.load(args.workspace / "checkpoint.json")
    if checkpoint is None:
        print(
            "No checkpoint found. Run the suite first: "
            "python -m scripts.evaluation run",
            file=sys.stderr,
        )
        return 1

    cases = {case.case_id: case for case in load_manifest(MANIFEST)}
    oracle = load_oracle(ORACLE)
    outcomes = [
        CaseOutcome(
            case_id=case_id,
            scenario=cases[case_id].scenario,
            workflow=cases[case_id].workflow,
            base_scenario=cases[case_id].base_scenario,
            status=record.get("status"),
            reason_codes=list(record.get("reason_codes") or []),
            duplicate_candidates=list(record.get("duplicate_candidates") or []),
            policy_citations=list(record.get("policy_citations") or []),
            error=record.get("error"),
            quota_exhausted=bool(record.get("quota_exhausted")),
        )
        for case_id, record in checkpoint.completed.items()
        if case_id in cases
    ]

    score = score_run(
        outcomes,
        oracle,
        expected_reason_codes={
            case_id: list(case.expected_reason_codes)
            for case_id, case in cases.items()
        },
    )

    window_path = args.workspace / "run-window.json"
    window = (
        json.loads(window_path.read_text(encoding="utf-8"))
        if window_path.exists()
        else {}
    )
    markdown, _ = write_report(
        args.workspace / "report",
        score,
        outcomes,
        RunProvenance(
            commit_sha=_commit_sha(),
            model_version=settings.DEFAULT_MODEL,
            manifest_digest=window.get("manifest_digest", "unknown"),
            corpus_version="Vendrai_Procurement_Document_Corpus_v2",
            started_at=window.get("started_at", "unknown"),
            finished_at=window.get("finished_at", "unknown"),
        ),
    )
    print(f"Report: {markdown}")
    return 0


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        if args.stage == "materialize":
            return do_materialize(args)
        if args.stage == "run":
            return asyncio.run(do_run(args))
        return do_score(args)
    except ManifestError as error:
        print(f"Evaluation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
