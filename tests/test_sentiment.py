"""Modèle de sentiment : préparation, baseline, réseau, expérience."""

import numpy as np
import pandas as pd
import pytest

from shoppulse.sentiment import (
    NEURAL,
    TARGET,
    TFIDF,
    ReviewDataset,
    SentimentExperiment,
    SentimentMetrics,
    SentimentReport,
    TfidfSentimentModel,
    Vocabulary,
)


@pytest.fixture(scope="module")
def parts(reviews) -> dict[str, pd.DataFrame]:
    return ReviewDataset.split(reviews)


class TestReviewDataset:
    def test_split_is_temporal_and_excludes_neutral(self, parts) -> None:
        assert (parts["train"]["creation_date"].max()
                <= parts["validation"]["creation_date"].min())
        assert (parts["validation"]["creation_date"].max()
                <= parts["test"]["creation_date"].min())
        assert (parts["neutral"]["score"] == 3).all()
        for name in ("train", "validation", "test"):
            assert parts[name][TARGET].isin([0, 1]).all()

    def test_split_proportions(self, parts) -> None:
        labeled = sum(len(parts[name]) for name in ("train", "validation",
                                                    "test"))
        assert len(parts["train"]) == int(labeled * 0.70)


class TestVocabulary:
    def test_rare_and_unknown_words(self) -> None:
        vocabulary = Vocabulary(min_freq=2).fit([["bom", "bom", "raro"]])
        assert len(vocabulary) == 3
        assert vocabulary.encode(["bom", "nunca"], max_len=5) == [
            2, Vocabulary.UNKNOWN,
        ]
        assert vocabulary.encode([], max_len=5) == [Vocabulary.UNKNOWN]
        assert len(vocabulary.encode(["bom"] * 10, max_len=4)) == 4


class TestSentimentMetrics:
    def test_metrics_of_a_perfect_model(self) -> None:
        y = np.array([0, 0, 1, 1])
        metrics = SentimentMetrics.compute(y, np.array([0.1, 0.2, 0.8, 0.9]),
                                           0.5)
        assert metrics["f1_negative"] == 1.0
        assert metrics["macro_f1"] == 1.0
        threshold = SentimentMetrics.best_f1_threshold(
            y, np.array([0.1, 0.2, 0.8, 0.9])
        )
        assert 0.2 < threshold <= 0.8


class TestTfidfSentimentModel:
    def test_learns_negative_words(self, parts, tmp_path) -> None:
        model = TfidfSentimentModel().fit(parts["train"]["text"],
                                          parts["train"][TARGET])
        proba = model.predict_proba(pd.Series(["produto quebrado não recebi",
                                               "chegou antes do prazo"]))
        assert proba[0] > 0.5 > proba[1]
        assert "não" in model.top_terms(5)["négatif"].tolist()
        path = tmp_path / "tfidf.joblib"
        model.save(path)
        reloaded = TfidfSentimentModel.load(path)
        assert np.allclose(reloaded.predict_proba(parts["test"]["text"]),
                           model.predict_proba(parts["test"]["text"]))


class TestNeuralSentimentModel:
    def test_trains_saves_and_reloads(self, parts, tmp_path) -> None:
        pytest.importorskip("torch")
        from shoppulse.sentiment import NeuralSentimentModel

        model = NeuralSentimentModel(epochs=3, patience=1).fit(
            parts["train"], parts["validation"]
        )
        assert 1 <= len(model.history) <= 3
        assert {"train_loss", "validation_pr_auc"} <= set(model.history)
        proba = model.predict_proba(parts["test"]["text"])
        assert ((proba >= 0) & (proba <= 1)).all()
        path = tmp_path / "gru.pt"
        model.save(path)
        reloaded = NeuralSentimentModel.load(path)
        assert np.allclose(reloaded.predict_proba(parts["test"]["text"]),
                           proba)


class TestSentimentExperiment:
    def test_full_comparison_and_report(self, reviews) -> None:
        pytest.importorskip("torch")
        results = SentimentExperiment(reviews).run()
        assert results.best_model in {TFIDF, NEURAL}
        assert set(results.test_scores.index) == {TFIDF, NEURAL}
        assert set(results.learning_curve["share"]) == {0.1, 0.25, 0.5, 1.0}
        assert len(results.neutral_predictions) > 0
        markdown = SentimentReport(results).to_markdown()
        assert "### Validation" in markdown
        assert "### Test" in markdown
