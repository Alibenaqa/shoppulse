"""Indicateurs clés de l'activité, calculés sur une table de commandes."""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from shoppulse.geography import BrazilRegions
from shoppulse.warehouse import DataWarehouse

ORDERS_SQL = """
SELECT o.order_id,
    o.purchase_timestamp,
    o.status NOT IN ('canceled', 'unavailable') AS is_valid,
    c.state,
    COALESCE(v.revenue, 0) AS revenue,
    CASE WHEN o.status = 'delivered'
        AND o.delivered_customer_date IS NOT NULL
        THEN o.delivered_customer_date::DATE > o.estimated_delivery_date::DATE
    END AS is_late,
    r.score
FROM core.orders AS o
JOIN core.customers AS c ON c.customer_id = o.customer_id
LEFT JOIN (
    SELECT order_id, SUM(price + freight_value) AS revenue
    FROM core.order_items
    GROUP BY order_id
) AS v ON v.order_id = o.order_id
LEFT JOIN (
    SELECT order_id, AVG(score) AS score
    FROM core.order_reviews
    GROUP BY order_id
) AS r ON r.order_id = o.order_id
"""
CATEGORIES_SQL = """
SELECT o.order_id,
    COALESCE(c.category_name_english, 'unknown') AS category,
    i.price
FROM core.order_items AS i
JOIN core.orders AS o ON o.order_id = i.order_id
JOIN core.products AS p ON p.product_id = i.product_id
LEFT JOIN core.categories AS c ON c.category_name = p.category_name
WHERE o.status NOT IN ('canceled', 'unavailable')
"""
SEGMENTS_SQL = "SELECT persona, state, monetary FROM mart.customer_segments"


@dataclass
class Kpis:
    """Les 5 indicateurs clés d'une période."""

    revenue: float
    orders: int
    avg_basket: float
    late_rate: float
    avg_score: float


class ActivityData:
    """Charge les données du tableau de bord depuis la base."""

    def __init__(self, warehouse: DataWarehouse | None = None) -> None:
        self.warehouse = warehouse or DataWarehouse()

    def orders(self) -> pd.DataFrame:
        frame = self.warehouse.query(ORDERS_SQL)
        frame["revenue"] = frame["revenue"].astype(float)
        frame["region"] = frame["state"].map(BrazilRegions.of)
        return frame

    def categories(self) -> pd.DataFrame:
        frame = self.warehouse.query(CATEGORIES_SQL)
        frame["price"] = frame["price"].astype(float)
        return frame

    def segments(self) -> pd.DataFrame:
        frame = self.warehouse.query(SEGMENTS_SQL)
        frame["region"] = frame["state"].map(BrazilRegions.of)
        return frame


class KpiCalculator:
    """Filtre les commandes et calcule les indicateurs d'une période."""

    def __init__(self, orders: pd.DataFrame) -> None:
        self.orders = orders

    def filter(self, start: date, end: date,
               regions: list[str] | None = None) -> pd.DataFrame:
        """Commandes passées entre start et end inclus (et régions)."""
        day = self.orders["purchase_timestamp"].dt.date
        mask = (day >= start) & (day <= end)
        if regions:
            mask &= self.orders["region"].isin(regions)
        return self.orders[mask]

    @staticmethod
    def compute(orders: pd.DataFrame) -> Kpis:
        valid = orders[orders["is_valid"]]
        revenue = float(valid["revenue"].sum())
        count = len(valid)
        return Kpis(
            revenue=revenue,
            orders=count,
            avg_basket=revenue / count if count else 0.0,
            late_rate=100 * float(
                orders["is_late"].dropna().astype(float).mean()
            ) if orders["is_late"].notna().any() else 0.0,
            avg_score=float(orders["score"].mean())
            if orders["score"].notna().any() else 0.0,
        )

    def period(self, start: date, end: date,
               regions: list[str] | None = None) -> Kpis:
        return self.compute(self.filter(start, end, regions))

    def previous_period(self, start: date, end: date,
                        regions: list[str] | None = None) -> Kpis:
        """Mêmes indicateurs sur la période de même durée juste avant."""
        length = end - start
        previous_end = start - pd.Timedelta(days=1)
        previous_start = previous_end - length
        return self.period(previous_start, previous_end, regions)

    @staticmethod
    def monthly(orders: pd.DataFrame) -> pd.DataFrame:
        """CA et nombre de commandes valides par mois."""
        valid = orders[orders["is_valid"]]
        return (
            valid.set_index("purchase_timestamp")
            .sort_index()
            .resample("MS")
            .agg({"revenue": "sum", "order_id": "count"})
            .rename(columns={"order_id": "orders"})
        )

    @staticmethod
    def late_by_state(orders: pd.DataFrame,
                      min_orders: int = 100) -> pd.DataFrame:
        """Taux de retard par état (états avec assez de livraisons)."""
        delivered = orders.dropna(subset=["is_late"])
        by_state = delivered.groupby("state").agg(
            delivered=("order_id", "count"),
            late_rate=("is_late", "mean"),
        )
        by_state["late_rate"] = 100 * by_state["late_rate"].astype(float)
        return by_state[by_state["delivered"] >= min_orders].sort_values(
            "late_rate", ascending=False
        )
