"""Chargement des 9 CSV Olist dans PostgreSQL (couches RAW puis CORE)."""

from pathlib import Path

from shoppulse.config import RAW_DATA_DIR, SQL_DIR
from shoppulse.database import Database

CSV_TO_RAW_TABLE = {
    "olist_customers_dataset.csv": "raw.customers",
    "olist_geolocation_dataset.csv": "raw.geolocation",
    "olist_order_items_dataset.csv": "raw.order_items",
    "olist_order_payments_dataset.csv": "raw.order_payments",
    "olist_order_reviews_dataset.csv": "raw.order_reviews",
    "olist_orders_dataset.csv": "raw.orders",
    "olist_products_dataset.csv": "raw.products",
    "olist_sellers_dataset.csv": "raw.sellers",
    "product_category_name_translation.csv": "raw.category_translation",
}
CORE_TABLES = [
    "core.customers", "core.geolocation", "core.categories",
    "core.products", "core.sellers", "core.orders", "core.order_items",
    "core.order_payments", "core.order_reviews",
]


class OlistLoader:
    """Charge les CSV Olist de façon idempotente (rejouable à l'infini)."""

    def __init__(self, database: Database,
                 raw_dir: Path = RAW_DATA_DIR) -> None:
        self.database = database
        self.raw_dir = raw_dir

    def check_files(self) -> None:
        """Vérifie que les 9 CSV attendus sont présents."""
        missing = [
            name for name in CSV_TO_RAW_TABLE
            if not (self.raw_dir / name).is_file()
        ]
        if missing:
            raise FileNotFoundError(
                f"CSV manquants dans {self.raw_dir} : {', '.join(missing)}"
            )

    def create_schemas(self) -> None:
        """Crée les schémas RAW et CORE s'ils n'existent pas."""
        self.database.execute_file(SQL_DIR / "schema_raw.sql")
        self.database.execute_file(SQL_DIR / "schema_core.sql")

    def load_raw(self) -> dict[str, int]:
        """Vide puis recharge chaque table RAW depuis son CSV."""
        counts = {}
        for csv_name, table in CSV_TO_RAW_TABLE.items():
            self.database.truncate(table)
            self.database.copy_csv(table, self.raw_dir / csv_name)
            counts[table] = self.database.count_rows(table)
        return counts

    def transform_core(self) -> dict[str, int]:
        """Alimente CORE depuis RAW (typage + règles de nettoyage)."""
        self.database.execute_file(SQL_DIR / "transform_core.sql")
        return {
            table: self.database.count_rows(table) for table in CORE_TABLES
        }

    def run(self) -> dict[str, dict[str, int]]:
        """Exécute le chargement complet et renvoie les volumes."""
        self.check_files()
        self.create_schemas()
        return {"raw": self.load_raw(), "core": self.transform_core()}
