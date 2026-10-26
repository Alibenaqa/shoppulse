"""Tests de données sur les échantillons versionnés (data/samples).

Ils vérifient le contrat des fichiers Olist : colonnes attendues par le
schéma RAW, unicité des clés, cohérence entre fichiers et domaines de
valeurs. Les mêmes fichiers servent aux tests d'intégration du pipeline.
"""

import re

import pandas as pd
import pytest

from shoppulse.config import SQL_DIR
from shoppulse.geography import STATE_TO_REGION
from shoppulse.loader import CSV_TO_RAW_TABLE
from tests.conftest import SAMPLES_DIR

ORDER_STATUSES = {"delivered", "shipped", "canceled", "unavailable",
                  "invoiced", "processing", "created", "approved"}


class OlistSamples:
    """Lecture des échantillons et du schéma RAW."""

    @staticmethod
    def read(name: str) -> pd.DataFrame:
        return pd.read_csv(SAMPLES_DIR / name, dtype=str,
                           keep_default_na=False, encoding="utf-8-sig")

    @staticmethod
    def raw_columns() -> dict[str, list[str]]:
        """Colonnes de chaque table RAW, lues dans sql/schema_raw.sql."""
        schema = (SQL_DIR / "schema_raw.sql").read_text(encoding="utf-8")
        tables = re.findall(r"CREATE TABLE IF NOT EXISTS (raw\.\w+) \((.*?)\);",
                            schema, flags=re.DOTALL)
        return {
            table: re.findall(r"^\s+(\w+)\s+TEXT", body, flags=re.MULTILINE)
            for table, body in tables
        }


@pytest.fixture(scope="module")
def samples() -> dict[str, pd.DataFrame]:
    return {name: OlistSamples.read(name) for name in CSV_TO_RAW_TABLE}


class TestFiles:
    def test_the_nine_files_weigh_less_than_one_megabyte(self) -> None:
        sizes = [(SAMPLES_DIR / name).stat().st_size
                 for name in CSV_TO_RAW_TABLE]
        assert sum(sizes) < 1_000_000

    def test_headers_match_the_raw_schema(self, samples) -> None:
        expected = OlistSamples.raw_columns()
        for name, frame in samples.items():
            assert list(frame.columns) == expected[CSV_TO_RAW_TABLE[name]]


class TestKeys:
    @pytest.mark.parametrize("name, keys", [
        ("olist_orders_dataset.csv", ["order_id"]),
        ("olist_customers_dataset.csv", ["customer_id"]),
        ("olist_products_dataset.csv", ["product_id"]),
        ("olist_sellers_dataset.csv", ["seller_id"]),
        ("olist_order_items_dataset.csv", ["order_id", "order_item_id"]),
        ("olist_order_payments_dataset.csv",
         ["order_id", "payment_sequential"]),
    ])
    def test_primary_keys_are_unique(self, samples, name, keys) -> None:
        assert not samples[name].duplicated(keys).any()

    @pytest.mark.parametrize("child, column, parent, parent_column", [
        ("olist_order_items_dataset.csv", "order_id",
         "olist_orders_dataset.csv", "order_id"),
        ("olist_order_items_dataset.csv", "product_id",
         "olist_products_dataset.csv", "product_id"),
        ("olist_order_items_dataset.csv", "seller_id",
         "olist_sellers_dataset.csv", "seller_id"),
        ("olist_orders_dataset.csv", "customer_id",
         "olist_customers_dataset.csv", "customer_id"),
        ("olist_order_payments_dataset.csv", "order_id",
         "olist_orders_dataset.csv", "order_id"),
        ("olist_order_reviews_dataset.csv", "order_id",
         "olist_orders_dataset.csv", "order_id"),
    ])
    def test_foreign_keys_exist(self, samples, child, column, parent,
                                parent_column) -> None:
        assert samples[child][column].isin(
            samples[parent][parent_column]
        ).all()


class TestValues:
    def test_review_scores_are_between_one_and_five(self, samples) -> None:
        scores = samples["olist_order_reviews_dataset.csv"][
            "review_score"
        ].astype(int)
        assert scores.between(1, 5).all()

    def test_amounts_are_not_negative(self, samples) -> None:
        items = samples["olist_order_items_dataset.csv"]
        assert (items["price"].astype(float) > 0).all()
        assert (items["freight_value"].astype(float) >= 0).all()
        payments = samples["olist_order_payments_dataset.csv"]
        assert (payments["payment_value"].astype(float) >= 0).all()

    def test_states_and_statuses_are_known(self, samples) -> None:
        customers = samples["olist_customers_dataset.csv"]
        assert customers["customer_state"].isin(STATE_TO_REGION).all()
        orders = samples["olist_orders_dataset.csv"]
        assert orders["order_status"].isin(ORDER_STATUSES).all()

    def test_promise_is_after_purchase(self, samples) -> None:
        orders = samples["olist_orders_dataset.csv"]
        purchase = pd.to_datetime(orders["order_purchase_timestamp"])
        promise = pd.to_datetime(orders["order_estimated_delivery_date"])
        assert (promise >= purchase.dt.normalize()).all()
