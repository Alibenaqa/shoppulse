"""Génère les échantillons de données versionnés dans data/samples/.

Usage : python pipelines/make_samples.py

Les données complètes ne vont jamais dans Git. Ces échantillons (< 1 Mo au
total) gardent la structure des 9 CSV Olist et leur cohérence : chaque
commande tirée au hasard emporte son client, ses articles, ses paiements,
ses avis, ses produits, ses vendeurs et quelques points GPS de chaque code
postal. Ils servent aux tests de données et aux tests d'intégration de la
CI, qui rejoue le vrai pipeline de chargement sur ces fichiers.
"""

from pathlib import Path

import pandas as pd

from shoppulse.config import PROJECT_ROOT, RAW_DATA_DIR
from shoppulse.loader import CSV_TO_RAW_TABLE

SAMPLES_DIR = PROJECT_ROOT / "data" / "samples"
SAMPLE_ORDERS = 500
POINTS_PER_ZIP = 3
RANDOM_STATE = 42
MAX_TOTAL_BYTES = 1_000_000


class SampleBuilder:
    """Tire des commandes au hasard et garde toutes les lignes liées."""

    def __init__(self, raw_dir: Path = RAW_DATA_DIR,
                 output_dir: Path = SAMPLES_DIR) -> None:
        self.raw_dir = raw_dir
        self.output_dir = output_dir

    def read(self, name: str) -> pd.DataFrame:
        """CSV lu tel quel (texte), sans transformer les valeurs vides."""
        return pd.read_csv(self.raw_dir / name, dtype=str,
                           keep_default_na=False, encoding="utf-8-sig")

    def build(self) -> dict[str, pd.DataFrame]:
        orders = self.read("olist_orders_dataset.csv").sample(
            SAMPLE_ORDERS, random_state=RANDOM_STATE
        )
        keep = set(orders["order_id"])
        items = self.subset("olist_order_items_dataset.csv", "order_id", keep)
        customers = self.subset("olist_customers_dataset.csv", "customer_id",
                                set(orders["customer_id"]))
        products = self.subset("olist_products_dataset.csv", "product_id",
                               set(items["product_id"]))
        sellers = self.subset("olist_sellers_dataset.csv", "seller_id",
                              set(items["seller_id"]))
        zips = set(customers["customer_zip_code_prefix"]) | set(
            sellers["seller_zip_code_prefix"]
        )
        geolocation = (
            self.subset("olist_geolocation_dataset.csv",
                        "geolocation_zip_code_prefix", zips)
            .groupby("geolocation_zip_code_prefix").head(POINTS_PER_ZIP)
        )
        return {
            "olist_orders_dataset.csv": orders,
            "olist_order_items_dataset.csv": items,
            "olist_customers_dataset.csv": customers,
            "olist_products_dataset.csv": products,
            "olist_sellers_dataset.csv": sellers,
            "olist_geolocation_dataset.csv": geolocation,
            "olist_order_payments_dataset.csv": self.subset(
                "olist_order_payments_dataset.csv", "order_id", keep
            ),
            "olist_order_reviews_dataset.csv": self.subset(
                "olist_order_reviews_dataset.csv", "order_id", keep
            ),
            "product_category_name_translation.csv": self.read(
                "product_category_name_translation.csv"
            ),
        }

    def subset(self, name: str, column: str, values: set[str]) -> pd.DataFrame:
        frame = self.read(name)
        return frame[frame[column].isin(values)]

    def write(self, samples: dict[str, pd.DataFrame]) -> int:
        """Écrit les échantillons et renvoie leur taille totale (octets)."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        total = 0
        for name, frame in samples.items():
            path = self.output_dir / name
            frame.to_csv(path, index=False)
            total += path.stat().st_size
        if total > MAX_TOTAL_BYTES:
            raise ValueError(f"échantillons trop gros : {total} octets")
        return total

    def run(self) -> int:
        samples = self.build()
        missing = set(CSV_TO_RAW_TABLE) - set(samples)
        if missing:
            raise ValueError(f"échantillons manquants : {missing}")
        return self.write(samples)


if __name__ == "__main__":
    size = SampleBuilder().run()
    print(f"Échantillons écrits dans {SAMPLES_DIR} ({size / 1000:.0f} ko)")
