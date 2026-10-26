"""Modèle de retard : métriques, baselines, comparaison et sauvegarde."""

import numpy as np
import pandas as pd

from shoppulse.delay_model import (
    BASELINE,
    BOOSTING,
    LOGISTIC,
    STATE_RULE,
    DelayMetrics,
    DelayModelReport,
    DelayModelStore,
    DelayModelTrainer,
    StateRateBaseline,
)
from shoppulse.features import FEATURES, TARGET


class TestDelayMetrics:
    def test_top_share_keeps_ten_percent(self) -> None:
        proba = np.linspace(0, 1, 100)
        top = DelayMetrics.top_share(proba)
        assert len(top) == 10
        assert set(top) == set(range(90, 100))

    def test_constant_scores_are_broken_at_random(self) -> None:
        top = DelayMetrics.top_share(np.zeros(100))
        assert sorted(top) != list(range(10))

    def test_ranking_metrics_of_a_perfect_model(self) -> None:
        y = np.array([0] * 90 + [1] * 10)
        metrics = DelayMetrics.ranking(y, y.astype(float))
        assert metrics["pr_auc"] == 1.0
        assert metrics["roc_auc"] == 1.0
        assert metrics["recall_top10"] == 1.0

    def test_metrics_at_threshold(self) -> None:
        y = np.array([1, 1, 0, 0])
        metrics = DelayMetrics.at_threshold(y, np.array([0.9, 0.2, 0.8,
                                                         0.1]), 0.5)
        assert metrics["precision"] == 0.5
        assert metrics["recall"] == 0.5
        assert metrics["flagged_share"] == 0.5

    def test_best_f1_threshold_separates_classes(self) -> None:
        y = np.array([0, 0, 1, 1])
        threshold = DelayMetrics.best_f1_threshold(
            y, np.array([0.1, 0.2, 0.7, 0.9])
        )
        assert 0.2 < threshold <= 0.7


class TestStateRateBaseline:
    def test_predicts_the_state_late_rate(self) -> None:
        X = pd.DataFrame({"customer_state": ["SP", "SP", "BA", "BA"]})
        model = StateRateBaseline().fit(X, pd.Series([0, 0, 1, 0]))
        proba = model.predict_proba(pd.DataFrame(
            {"customer_state": ["SP", "BA", "RJ"]}
        ))[:, 1]
        assert proba.tolist() == [0.0, 0.5, 0.25]
        assert model.predict(X).tolist() == [0, 0, 1, 1]


class TestDelayModelTrainer:
    def test_compares_a_baseline_and_two_algorithms(self,
                                                    delay_results) -> None:
        models = set(delay_results.cv_scores["model"])
        assert models == {BASELINE, STATE_RULE, LOGISTIC, BOOSTING}
        assert delay_results.best_model in models
        assert 0 < delay_results.threshold < 1

    def test_split_is_temporal(self, delay_trainer) -> None:
        assert (delay_trainer.train["purchase_timestamp"].max()
                < delay_trainer.test["purchase_timestamp"].min())

    def test_predictions_cover_validation_and_test(self,
                                                   delay_results) -> None:
        column = f"proba_{delay_results.best_model}"
        assert column in delay_results.test_predictions
        assert delay_results.validation_predictions[column].between(
            0, 1
        ).all()
        assert set(delay_results.importance["feature"]) == set(FEATURES)

    def test_report_has_every_section(self, delay_results) -> None:
        markdown = DelayModelReport(delay_results).to_markdown()
        for title in ("## Données", "## Validation croisée",
                      "## Test", "## Importance"):
            assert title in markdown

    def test_model_store_round_trip(self, tmp_path, delay_frame,
                                    delay_results) -> None:
        model = DelayModelTrainer(delay_frame).fit_final(
            delay_results.best_model
        )
        path = tmp_path / "delay.joblib"
        DelayModelStore.save(model, delay_results, path, {"Sudeste": 0.4})
        saved = DelayModelStore.load(path)
        assert saved["region_thresholds"] == {"Sudeste": 0.4}
        proba = saved["model"].predict_proba(delay_frame[FEATURES])[:, 1]
        assert len(proba) == len(delay_frame)
        assert delay_frame[TARGET].isin([0, 1]).all()
