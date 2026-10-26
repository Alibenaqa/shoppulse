"""Audit d'équité par région."""

import numpy as np
import pandas as pd
import pytest

from shoppulse.fairness import (
    ALL_GROUPS,
    DelayFairnessAudit,
    FairnessAuditor,
    FairnessReport,
    GroupMetrics,
    RegionThresholds,
)
from shoppulse.features import TARGET


@pytest.fixture
def predictions() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    regions = np.repeat(["Sudeste", "Nordeste"], [300, 100])
    late = rng.uniform(size=400) < np.where(regions == "Sudeste", 0.1, 0.2)
    score = np.clip(0.3 * late + rng.uniform(0, 0.7, 400), 0, 1)
    return pd.DataFrame({"customer_region": regions,
                         TARGET: late.astype(int), "proba_model": score})


class TestGroupMetrics:
    def test_decision_metrics(self) -> None:
        metrics = GroupMetrics.compute(np.array([1, 1, 0, 0]),
                                       np.array([0.9, 0.2, 0.8, 0.1]), 0.5)
        assert metrics["flag_rate"] == 0.5
        assert metrics["tpr"] == 0.5
        assert metrics["fpr"] == 0.5
        assert metrics["precision"] == 0.5
        assert metrics["roc_auc"] == 0.75

    def test_single_class_gives_no_auc(self) -> None:
        metrics = GroupMetrics.compute(np.array([0, 0]),
                                       np.array([0.1, 0.9]), 0.5)
        assert np.isnan(metrics["roc_auc"])
        assert np.isnan(metrics["tpr"])


class TestFairnessAuditor:
    def test_metrics_per_region_and_overall(self, predictions) -> None:
        metrics = FairnessAuditor(predictions, "proba_model", 0.5).metrics()
        assert set(metrics.index) == {"Sudeste", "Nordeste", ALL_GROUPS}
        assert metrics.loc[ALL_GROUPS, "orders"] == 400

    def test_reference_region_has_neutral_disparities(self,
                                                      predictions) -> None:
        disparities = FairnessAuditor(predictions, "proba_model",
                                      0.5).disparities()
        assert disparities.loc["Sudeste", "flag_ratio"] == 1.0
        assert disparities.loc["Sudeste", "tpr_gap"] == 0.0

    def test_intervals_surround_the_estimate(self, predictions) -> None:
        auditor = FairnessAuditor(predictions, "proba_model", 0.5)
        metrics, intervals = auditor.metrics(), auditor.intervals()
        for region in metrics.index:
            assert (intervals.loc[region, "flag_rate_low"]
                    <= metrics.loc[region, "flag_rate"]
                    <= intervals.loc[region, "flag_rate_high"])

    def test_region_thresholds_reach_the_target_recall(self,
                                                       predictions) -> None:
        thresholds = RegionThresholds().fit(predictions, "proba_model", 0.5)
        metrics = FairnessAuditor(predictions, "proba_model", 0.5,
                                  thresholds).metrics()
        assert (metrics.drop(index=ALL_GROUPS)["tpr"] >= 0.5).all()

    def test_report_from_training_results(self, delay_results) -> None:
        audit = DelayFairnessAudit(delay_results)
        audits = audit.audits()
        assert len(audits) == 3
        assert 0 < audit.target_recall <= 1
        markdown = FairnessReport(audits).to_markdown()
        assert markdown.count("| Région |") == 3
