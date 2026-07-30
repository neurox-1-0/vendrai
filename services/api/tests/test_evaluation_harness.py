"""Materializer determinism and scorer correctness.

The determinism test is the load-bearing one: if the same seed does not
produce byte-identical documents, a score change cannot be attributed to a code
change, and the whole evaluation stops meaning anything.
"""

from pathlib import Path

import pytest

from scripts.evaluation.manifest import (
    EvaluationCase,
    Mutation,
    load_manifest,
    load_oracle,
    verify_manifest_digest,
)
from scripts.evaluation.materializer import (
    materialize_case,
    materialize_document,
    mutation_key,
)
from scripts.evaluation.reporter import RunProvenance, render_markdown
from scripts.evaluation.scorer import CaseOutcome, score_run, status_matches

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "evaluation" / "cases.jsonl"
DIGEST = ROOT / "evaluation" / "manifest.sha256"
ORACLE = (
    ROOT
    / "Vendrai_Procurement_Document_Corpus_v2"
    / "ground_truth"
    / "expected_case_outcomes.json"
)

pytestmark = pytest.mark.skipif(
    not MANIFEST.exists(), reason="evaluation manifest not present"
)


def test_the_manifest_matches_its_recorded_digest():
    """An input that drifted silently makes the published numbers unusable."""
    assert verify_manifest_digest(MANIFEST, DIGEST)


def test_the_manifest_is_the_declared_shape():
    cases = load_manifest(MANIFEST)
    assert len(cases) == 100
    assert sum(case.workflow == "SUPPLIER_ONBOARDING" for case in cases) == 50
    assert sum(case.workflow == "INVOICE_EXCEPTION" for case in cases) == 50
    assert all(case.requires_real_gemini for case in cases)


def test_every_case_maps_to_a_scenario_the_oracle_scores():
    oracle = load_oracle(ORACLE)
    for case in load_manifest(MANIFEST):
        assert case.base_scenario in oracle, (
            f"{case.case_id} derives from {case.source_case}, whose base "
            f"scenario {case.base_scenario} has no entry in the oracle, so it "
            "cannot be scored"
        )


def test_the_cache_key_changes_with_the_mutation(tmp_path):
    source = ROOT / load_manifest(MANIFEST)[0].documents[0]
    first = mutation_key(source, Mutation(contrast=0.9, rotate_degrees=0, seed=1))
    second = mutation_key(source, Mutation(contrast=1.1, rotate_degrees=0, seed=1))
    assert first != second


def test_the_cache_key_is_stable_for_the_same_inputs():
    source = ROOT / load_manifest(MANIFEST)[0].documents[0]
    mutation = Mutation(contrast=0.9, rotate_degrees=0, seed=1)
    assert mutation_key(source, mutation) == mutation_key(source, mutation)


def test_an_identity_mutation_reproduces_the_source_exactly(tmp_path):
    source = ROOT / load_manifest(MANIFEST)[0].documents[0]
    document = materialize_document(source, Mutation(), tmp_path)
    assert document.path.read_bytes() == source.read_bytes()


def test_materialization_is_deterministic(tmp_path):
    """Same seed, byte-identical output - twice, into separate caches."""
    case = load_manifest(MANIFEST)[0]
    first = materialize_case(
        case, repository_root=ROOT, cache_root=tmp_path / "a"
    )
    second = materialize_case(
        case, repository_root=ROOT, cache_root=tmp_path / "b"
    )
    assert [item.sha256 for item in first.documents] == [
        item.sha256 for item in second.documents
    ]


# --- Scoring ---------------------------------------------------------------


def _outcome(**overrides) -> CaseOutcome:
    defaults = {
        "case_id": "VO-EVAL-001",
        "scenario": "CLEAN_ONBOARDING",
        "workflow": "SUPPLIER_ONBOARDING",
        "base_scenario": "VO-001",
        "status": "APPROVAL_PENDING",
        "reason_codes": [],
        "policy_citations": ["PROC-001:3.2:4"],
    }
    return CaseOutcome(**{**defaults, **overrides})


ORACLE_FIXTURE = {
    "VO-001": {
        "expected_status": "READY_FOR_APPROVAL",
        "findings": ["required documents present"],
    },
    "VO-002": {
        "expected_status": "HUMAN_REVIEW_REQUIRED",
        "findings": ["exact tax ID match to existing vendor V000233"],
    },
}


def test_status_equivalence_bridges_the_two_vocabularies():
    assert status_matches("READY_FOR_APPROVAL", "APPROVAL_PENDING")
    assert status_matches("CLARIFICATION_REQUIRED", "NEEDS_CLARIFICATION")
    assert not status_matches("READY_FOR_APPROVAL", "NEEDS_CLARIFICATION")
    assert not status_matches("READY_FOR_APPROVAL", None)


def test_a_correct_case_scores_full_marks():
    score = score_run(
        [_outcome()], ORACLE_FIXTURE, expected_reason_codes={"VO-EVAL-001": []}
    )
    assert score.overall.status_accuracy.value == 1.0
    assert score.overall.policy_recall_at_10.value == 1.0


def test_a_wrong_status_is_scored_wrong():
    score = score_run(
        [_outcome(status="NEEDS_CLARIFICATION")],
        ORACLE_FIXTURE,
        expected_reason_codes={"VO-EVAL-001": []},
    )
    assert score.overall.status_accuracy.value == 0.0


def test_reason_codes_are_scored_as_f1_not_exact_set_equality():
    score = score_run(
        [
            _outcome(
                case_id="VO-EVAL-002",
                base_scenario="VO-002",
                scenario="DUPLICATE",
                status="DUPLICATE_REVIEW",
                reason_codes=["POSSIBLE_DUPLICATE", "SPURIOUS_CODE"],
            )
        ],
        ORACLE_FIXTURE,
        expected_reason_codes={"VO-EVAL-002": ["POSSIBLE_DUPLICATE"]},
    )
    assert score.overall.reason_code_f1.true_positives == 1
    assert score.overall.reason_code_f1.false_positives == 1
    assert 0 < score.overall.reason_code_f1.value < 1


def test_a_quota_paused_case_is_excluded_rather_than_counted_as_a_failure():
    score = score_run(
        [_outcome(status=None, quota_exhausted=True)],
        ORACLE_FIXTURE,
        expected_reason_codes={"VO-EVAL-001": []},
    )
    assert score.overall.executed == 0
    assert score.not_executed == ["VO-EVAL-001"]
    # No case was scored, so the metric is unmeasured - not zero, which would
    # read as "we tried and failed".
    assert score.overall.status_accuracy.value is None


def test_scores_are_reported_per_scenario():
    score = score_run(
        [
            _outcome(),
            _outcome(
                case_id="VO-EVAL-002",
                scenario="DUPLICATE",
                base_scenario="VO-002",
                status="NEEDS_CLARIFICATION",
            ),
        ],
        ORACLE_FIXTURE,
        expected_reason_codes={},
    )
    assert set(score.per_scenario) == {"CLEAN_ONBOARDING", "DUPLICATE"}
    assert score.per_scenario["CLEAN_ONBOARDING"].status_accuracy.value == 1.0
    assert score.per_scenario["DUPLICATE"].status_accuracy.value == 0.0


def test_duplicate_recall_only_counts_cases_a_duplicate_was_expected_in():
    score = score_run(
        [_outcome()], ORACLE_FIXTURE, expected_reason_codes={}
    )
    assert score.overall.duplicate_recall.total == 0

    score = score_run(
        [
            _outcome(
                case_id="VO-EVAL-002",
                scenario="DUPLICATE",
                base_scenario="VO-002",
                status="DUPLICATE_REVIEW",
                duplicate_candidates=[{"score": 0.9, "erp_vendor_id": "V000233"}],
            )
        ],
        ORACLE_FIXTURE,
        expected_reason_codes={},
    )
    assert score.overall.duplicate_recall.value == 1.0
    assert score.overall.duplicate_exact_match.value == 1.0


def test_the_report_states_an_unmeasured_metric_rather_than_zero():
    score = score_run([], ORACLE_FIXTURE, expected_reason_codes={})
    markdown = render_markdown(
        score,
        [],
        RunProvenance(
            commit_sha="abc123",
            model_version="gemini-3.6-flash",
            manifest_digest="deadbeef",
            corpus_version="v2",
            started_at="2026-07-30T00:00:00Z",
            finished_at="2026-07-30T01:00:00Z",
        ),
    )
    assert "not measured" in markdown
    assert "abc123" in markdown
    assert "gemini-3.6-flash" in markdown


def test_the_report_calls_out_cross_tenant_leakage_as_a_blocker():
    score = score_run(
        [_outcome()], ORACLE_FIXTURE, expected_reason_codes={}, cross_tenant_leaks=1
    )
    markdown = render_markdown(
        score,
        [_outcome()],
        RunProvenance("sha", "model", "digest", "v2", "start", "end"),
    )
    assert "release blocker" in markdown


def test_manifest_case_shape_round_trips():
    case = EvaluationCase.from_dict(
        {
            "case_id": "X-1",
            "workflow": "SUPPLIER_ONBOARDING",
            "scenario": "DUPLICATE",
            "source_case": "VO-002_potential_duplicate_vendor",
            "documents": ["a.pdf"],
            "expected_reason_codes": ["POSSIBLE_DUPLICATE"],
            "mutation": {"contrast": 1.1, "rotate_degrees": 1, "seed": 2},
        }
    )
    assert case.base_scenario == "VO-002"
    assert case.mutation.contrast == 1.1
