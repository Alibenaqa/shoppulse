"""Fixtures partagées : données synthétiques, base de test, modèles."""

import os
from pathlib import Path

import joblib
import pandas as pd
import psycopg
import pytest
from psycopg import sql

from shoppulse.config import PROJECT_ROOT, DatabaseSettings
from shoppulse.delay_model import (
    DelayModelResults,
    DelayModelStore,
    DelayModelTrainer,
)
from shoppulse.fairness import DelayFairnessAudit
from shoppulse.features import (
    DelayFeatureBuilder,
    DelayHistory,
    DelayServingSnapshot,
)
from shoppulse.segmentation import CustomerSegmenter, RfmTable
from shoppulse.sentiment import TfidfSentimentModel
from tests.synthetic import SyntheticData

SAMPLES_DIR = PROJECT_ROOT / "data" / "samples"
TEST_DATABASE = os.getenv("SHOPPULSE_TEST_DB", "shoppulse_test")
REFERENCE_TIME = pd.Timestamp("2018-09-01")


@pytest.fixture(scope="session")
def delay_raw() -> pd.DataFrame:
    return SyntheticData.delay_orders()


@pytest.fixture(scope="session")
def delay_frame(delay_raw: pd.DataFrame) -> pd.DataFrame:
    return DelayFeatureBuilder().build_from(delay_raw)


@pytest.fixture(scope="session")
def delay_snapshot(delay_raw: pd.DataFrame) -> DelayServingSnapshot:
    prepared = DelayFeatureBuilder.prepare(delay_raw)
    return DelayServingSnapshot(
        DelayHistory(prepared), SyntheticData.geolocation(delay_raw),
        SyntheticData.sellers(delay_raw), REFERENCE_TIME,
    )


@pytest.fixture(scope="session")
def delay_trainer(delay_frame: pd.DataFrame) -> DelayModelTrainer:
    return DelayModelTrainer(delay_frame)


@pytest.fixture(scope="session")
def delay_results(delay_trainer: DelayModelTrainer) -> DelayModelResults:
    return delay_trainer.run()


@pytest.fixture(scope="session")
def reviews() -> pd.DataFrame:
    return SyntheticData.reviews()


@pytest.fixture(scope="session")
def segmented() -> pd.DataFrame:
    rfm = RfmTable.add_scores(SyntheticData.rfm())
    return CustomerSegmenter(n_clusters=4).fit_predict(rfm)


@pytest.fixture(scope="session")
def models_dir(tmp_path_factory: pytest.TempPathFactory,
               delay_frame: pd.DataFrame, delay_results: DelayModelResults,
               delay_snapshot: DelayServingSnapshot,
               reviews: pd.DataFrame) -> Path:
    """Petits modèles entraînés sur les données synthétiques, enregistrés
    comme le ferait le pipeline d'entraînement."""
    directory = tmp_path_factory.mktemp("models")
    model = DelayModelTrainer(delay_frame).fit_final(delay_results.best_model)
    thresholds = DelayFairnessAudit(delay_results).region_thresholds
    DelayModelStore.save(model, delay_results,
                         directory / "delay_model.joblib",
                         thresholds.thresholds)
    DelayModelStore.save_snapshot(delay_snapshot,
                                  directory / "delay_snapshot.joblib")
    labeled = reviews[reviews["is_negative"] >= 0]
    TfidfSentimentModel().fit(labeled["text"], labeled["is_negative"]).save(
        directory / "sentiment_tfidf.joblib"
    )
    joblib.dump({"model_name": "tfidf_regression_logistique",
                 "path": "sentiment_tfidf.joblib", "threshold": 0.5},
                directory / "sentiment_model.joblib")
    rfm = RfmTable.add_scores(SyntheticData.rfm())
    segmenter = CustomerSegmenter(n_clusters=4)
    segmenter.fit_predict(rfm)
    segmenter.save(directory / "segmentation.joblib")
    return directory


@pytest.fixture(scope="session")
def test_settings() -> DatabaseSettings:
    """Base PostgreSQL dédiée aux tests (créée si besoin). Les tests
    marqués « db » sont ignorés si le serveur est injoignable."""
    admin = DatabaseSettings()
    admin.dbname = "postgres"
    try:
        with psycopg.connect(admin.conninfo(), autocommit=True,
                             connect_timeout=3) as connection:
            exists = connection.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (TEST_DATABASE,),
            ).fetchone()
            if not exists:
                connection.execute(sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(TEST_DATABASE)
                ))
    except psycopg.OperationalError as error:
        pytest.skip(f"PostgreSQL indisponible : {error}")
    settings = DatabaseSettings()
    settings.dbname = TEST_DATABASE
    return settings
