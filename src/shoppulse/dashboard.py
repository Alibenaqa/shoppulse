"""Tableau de bord Streamlit de la direction ShopPulse.

Lancement : streamlit run src/shoppulse/dashboard.py
"""

from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from shoppulse.geography import STATE_TO_REGION
from shoppulse.kpi import ActivityData, KpiCalculator, Kpis
from shoppulse.segmentation import (
    PERSONA_DORMANT,
    PERSONA_LOST,
    PERSONA_LOYAL,
    PERSONA_NEW,
)

DEFAULT_START = date(2018, 1, 1)
DEFAULT_END = date(2018, 8, 31)
DATA_START = date(2016, 9, 1)
DATA_END = date(2018, 10, 31)
BRAND_COLOR = "#AA8350"
INK_COLOR = "#4A4A44"
CACHE_TTL_SECONDS = 600
PERSONA_COLORS = {
    PERSONA_LOYAL: "#2F5233",
    PERSONA_NEW: "#AA8350",
    PERSONA_DORMANT: "#B23A2B",
    PERSONA_LOST: "#B8B5AD",
}


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Chargement des données")
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Chargement mis en cache (fonction imposée par Streamlit)."""
    data = ActivityData()
    return data.orders(), data.categories(), data.segments()


class Dashboard:
    """Une page : filtres, 5 indicateurs clés et 4 graphiques."""

    def __init__(self) -> None:
        self.orders, self.categories, self.segments = load_data()
        self.calculator = KpiCalculator(self.orders)

    def run(self) -> None:
        st.set_page_config(page_title="ShopPulse — Activité",
                           page_icon="📦", layout="wide")
        st.title("ShopPulse — Comment se porte l'activité ?")
        start, end, regions = self.sidebar()
        current = self.calculator.period(start, end, regions)
        previous = self.calculator.previous_period(start, end, regions)
        st.caption(
            f"Période du {start:%d/%m/%Y} au {end:%d/%m/%Y}, comparée à la "
            "période de même durée qui précède."
        )
        self.kpi_row(current, previous)
        filtered = self.calculator.filter(start, end, regions)
        left, right = st.columns(2)
        with left:
            self.revenue_chart(filtered)
            self.categories_chart(filtered)
        with right:
            self.late_chart(filtered)
            self.personas_chart(regions)

    @staticmethod
    def sidebar() -> tuple[date, date, list[str]]:
        st.sidebar.header("Filtres")
        period = st.sidebar.date_input(
            "Période", (DEFAULT_START, DEFAULT_END),
            min_value=DATA_START, max_value=DATA_END,
        )
        start, end = (period if len(period) == 2
                      else (period[0], period[0]))
        regions = st.sidebar.multiselect(
            "Régions", sorted(set(STATE_TO_REGION.values())),
            help="Vide = toutes les régions",
        )
        st.sidebar.caption(
            "Données : couche CORE de PostgreSQL, alimentée par le "
            "pipeline Prefect."
        )
        return start, end, regions

    @staticmethod
    def kpi_row(current: Kpis, previous: Kpis) -> None:
        columns = st.columns(5)
        columns[0].metric(
            "Chiffre d'affaires", Dashboard.money(current.revenue),
            Dashboard.delta_pct(current.revenue, previous.revenue),
        )
        columns[1].metric(
            "Commandes", f"{current.orders:,}".replace(",", " "),
            Dashboard.delta_pct(current.orders, previous.orders),
        )
        columns[2].metric(
            "Panier moyen", f"{current.avg_basket:,.0f} R$",
            Dashboard.delta_pct(current.avg_basket, previous.avg_basket),
        )
        columns[3].metric(
            "Taux de retard", f"{current.late_rate:.1f} %",
            f"{current.late_rate - previous.late_rate:+.1f} pt",
            delta_color="inverse",
        )
        columns[4].metric(
            "Note moyenne des avis", f"{current.avg_score:.2f} / 5",
            f"{current.avg_score - previous.avg_score:+.2f}",
        )

    def revenue_chart(self, filtered: pd.DataFrame) -> None:
        monthly = self.calculator.monthly(filtered).reset_index()
        figure = px.bar(monthly, x="purchase_timestamp", y="revenue",
                        color_discrete_sequence=[BRAND_COLOR],
                        labels={"purchase_timestamp": "",
                                "revenue": "CA (R$)"})
        st.subheader("Chiffre d'affaires mensuel")
        st.plotly_chart(figure, use_container_width=True)

    def late_chart(self, filtered: pd.DataFrame) -> None:
        late = self.calculator.late_by_state(filtered).reset_index()
        figure = px.bar(late, x="state", y="late_rate",
                        color_discrete_sequence=["#B23A2B"],
                        labels={"state": "État",
                                "late_rate": "% livrées en retard"})
        st.subheader("Où livre-t-on en retard ?")
        st.plotly_chart(figure, use_container_width=True)

    def categories_chart(self, filtered: pd.DataFrame) -> None:
        top = (
            self.categories[self.categories["order_id"].isin(
                filtered["order_id"]
            )]
            .groupby("category")["price"].sum()
            .nlargest(10).sort_values().reset_index()
        )
        figure = px.bar(top, x="price", y="category", orientation="h",
                        color_discrete_sequence=[INK_COLOR],
                        labels={"price": "CA articles (R$)",
                                "category": ""})
        st.subheader("Top 10 des catégories")
        st.plotly_chart(figure, use_container_width=True)

    def personas_chart(self, regions: list[str]) -> None:
        segments = self.segments
        if regions:
            segments = segments[segments["region"].isin(regions)]
        personas = segments.groupby("persona").agg(
            clients=("persona", "size"), valeur=("monetary", "sum"),
        ).reset_index()
        figure = px.pie(personas, names="persona", values="valeur",
                        hole=0.5, color="persona",
                        color_discrete_map=PERSONA_COLORS)
        st.subheader("Valeur client par persona")
        st.plotly_chart(figure, use_container_width=True)
        st.caption("Segmentation RFM sur tout l'historique "
                   "(indépendante du filtre de période).")

    @staticmethod
    def money(value: float) -> str:
        if value >= 1_000_000:
            return f"{value / 1_000_000:.2f} M R$".replace(".", ",")
        return f"{value / 1_000:.0f} k R$"

    @staticmethod
    def delta_pct(current: float, previous: float) -> str | None:
        if not previous:
            return None
        return f"{100 * (current - previous) / previous:+.1f} %"


if __name__ == "__main__":
    Dashboard().run()
