from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Iterable


@dataclass(frozen=True)
class RobustAnomalyScore:
    score: float
    threshold: float
    anomalous: bool
    median: float | None
    mad: float | None
    explanation: str


def robust_mad_score(
    value: float,
    history: Iterable[float],
    *,
    threshold: float = 3.5,
) -> RobustAnomalyScore:
    samples = [float(item) for item in history]
    if len(samples) < 5:
        return RobustAnomalyScore(
            score=0.0,
            threshold=threshold,
            anomalous=False,
            median=median(samples) if samples else None,
            mad=None,
            explanation="Insufficient history; deterministic controls remain authoritative.",
        )
    center = median(samples)
    absolute_deviations = [abs(item - center) for item in samples]
    mad = median(absolute_deviations)
    if mad == 0:
        score = 0.0 if value == center else threshold + 1
    else:
        score = abs(0.6745 * (value - center) / mad)
    return RobustAnomalyScore(
        score=round(score, 4),
        threshold=threshold,
        anomalous=score >= threshold,
        median=round(center, 4),
        mad=round(mad, 4),
        explanation=(
            f"Value differs from the historical median by a robust z-score "
            f"of {score:.2f}; threshold is {threshold:.2f}."
        ),
    )


def isolation_forest_scores(
    training_rows: list[list[float]],
    scoring_rows: list[list[float]],
    *,
    contamination: float = 0.02,
    random_state: int = 42,
) -> list[float]:
    """Return normalized shadow scores, never a workflow decision.

    Importing scikit-learn lazily keeps deterministic processing available if
    the optional model runtime is unavailable.
    """
    if len(training_rows) < 1000:
        raise ValueError("INSUFFICIENT_TENANT_HISTORY")
    try:
        from sklearn.ensemble import IsolationForest  # type: ignore[import-not-found,import-untyped]
    except ImportError as exc:
        raise RuntimeError("ANOMALY_MODEL_RUNTIME_UNAVAILABLE") from exc
    model = IsolationForest(
        contamination=contamination,
        random_state=random_state,
        n_estimators=200,
    )
    model.fit(training_rows)
    raw = [-float(item) for item in model.score_samples(scoring_rows)]
    low, high = min(raw), max(raw)
    if high == low:
        return [0.0 for _ in raw]
    return [round((item - low) / (high - low), 6) for item in raw]
