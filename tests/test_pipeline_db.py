"""Tests d'intégration : le vrai pipeline rejoué sur les échantillons.

Ils utilisent une base dédiée (shoppulse_test), jamais la base de travail,
et sont ignorés si PostgreSQL n'est pas joignable. En CI, un service
PostgreSQL est démarré pour eux.
"""

import pandas as pd
import pytest

from shoppulse.analysis import SqlAnalysisReport
from shoppulse.config import DatabaseSettings
from shoppulse.database import Database
from shoppulse.features import FEATURES, DelayFeatureBuilder
from shoppulse.kpi import ActivityData, KpiCalculator
from shoppulse.loader import CORE_TABLES, OlistLoader
from shoppulse.quality import QualityChecker
from shoppulse.segmentation import SegmentationJob
from shoppulse.sentiment import ReviewDataset
from shoppulse.warehouse import DataWarehouse
from tests.conftest import SAMPLES_DIR

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def volumes(test_settings: DatabaseSettings) -> dict[str, dict[str, int]]:
    with Database(test_settings) as database:
        return OlistLoader(database, raw_dir=SAMPLES_DIR).run()


@pytest.fixture(scope="module")
def warehouse(test_settings: DatabaseSettings,
              volumes: dict) -> DataWarehouse:
    return DataWarehouse(test_settings)


class TestLoading:
    def test_raw_tables_match_the_csv_files(self, volumes) -> None:
        orders = pd.read_csv(SAMPLES_DIR / "olist_orders_dataset.csv")
        assert volumes["raw"]["raw.orders"] == len(orders)
        assert volumes["core"]["core.orders"] == len(orders)

    def test_every_core_table_is_filled(self, volumes) -> None:
        for table in CORE_TABLES:
            assert volumes["core"][table] > 0

    def test_loading_twice_gives_the_same_result(self, test_settings,
                                                 volumes) -> None:
        with Database(test_settings) as database:
            again = OlistLoader(database, raw_dir=SAMPLES_DIR).run()
        assert again == volumes


class TestQuality:
    def test_no_blocking_check_fails_after_cleaning(self, test_settings,
                                                    volumes) -> None:
        with Database(test_settings) as database:
            results = QualityChecker(database).run()
        assert QualityChecker.failures(results) == []

    def test_the_eight_sql_analyses_run(self, test_settings,
                                        volumes) -> None:
        with Database(test_settings) as database:
            markdown = SqlAnalysisReport(database).to_markdown()
        assert markdown.count("\n## ") == 8


class TestModelsData:
    def test_delay_features_from_the_database(self, warehouse) -> None:
        frame = DelayFeatureBuilder(warehouse).build()
        assert len(frame) > 100
        assert frame["estimated_days"].notna().all()
        assert set(FEATURES) <= set(frame.columns)

    def test_segmentation_job(self, warehouse, tmp_path) -> None:
        personas = SegmentationJob(warehouse, tmp_path / "seg.joblib").run()
        assert personas["customers"].sum() > 0
        assert (tmp_path / "seg.joblib").exists()
        segments = ActivityData(warehouse).segments()
        assert len(segments) == personas["customers"].sum()

    def test_dashboard_data(self, warehouse) -> None:
        orders = ActivityData(warehouse).orders()
        kpis = KpiCalculator.compute(orders)
        assert kpis.orders > 0
        assert not ActivityData(warehouse).categories().empty

    def test_reviews_are_labeled(self, warehouse) -> None:
        reviews = ReviewDataset(warehouse).load()
        assert reviews["is_negative"].isin([-1, 0, 1]).all()
        assert reviews["review_id"].is_unique
