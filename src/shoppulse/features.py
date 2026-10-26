"""Variables du modèle de retard de livraison.

Règle d'or : chaque variable ne doit utiliser que ce qui est connu au
moment de l'achat. Les historiques (vendeur, trajet, plateforme) sont donc
calculés sur les seuls événements survenus avant l'achat :
- une livraison est connue à sa date de livraison ;
- le statut « en retard » est connu dès la livraison si la commande arrive
  à temps, sinon dès le lendemain de la date promise (date `known_at`) ;
- la remise au transporteur est connue à sa date.
"""

import numpy as np
import pandas as pd

from shoppulse.geography import STATE_TO_REGION, BrazilRegions
from shoppulse.warehouse import DataWarehouse

DELAY_ORDERS_SQL = """
WITH items AS (
    SELECT i.order_id,
        COUNT(*) AS n_items,
        COUNT(DISTINCT i.seller_id) AS n_sellers,
        SUM(i.price) AS order_value,
        SUM(i.freight_value) AS freight_value,
        SUM(p.weight_g) AS total_weight_g
    FROM core.order_items AS i
    JOIN core.products AS p ON p.product_id = i.product_id
    GROUP BY i.order_id
),
main_seller AS (
    SELECT order_id, seller_id
    FROM core.order_items
    WHERE order_item_id = 1
)
SELECT o.order_id,
    o.purchase_timestamp,
    o.delivered_carrier_date,
    o.estimated_delivery_date,
    o.delivered_customer_date,
    c.state AS customer_state,
    s.state AS seller_state,
    ms.seller_id,
    gc.lat AS customer_lat,
    gc.lng AS customer_lng,
    gs.lat AS seller_lat,
    gs.lng AS seller_lng,
    it.n_items,
    it.n_sellers,
    it.order_value,
    it.freight_value,
    it.total_weight_g
FROM core.orders AS o
JOIN core.customers AS c ON c.customer_id = o.customer_id
JOIN main_seller AS ms ON ms.order_id = o.order_id
JOIN core.sellers AS s ON s.seller_id = ms.seller_id
JOIN items AS it ON it.order_id = o.order_id
LEFT JOIN core.geolocation AS gc ON gc.zip_code_prefix = c.zip_code_prefix
LEFT JOIN core.geolocation AS gs ON gs.zip_code_prefix = s.zip_code_prefix
WHERE o.status = 'delivered'
    AND o.delivered_customer_date IS NOT NULL
"""

GEOLOCATION_SQL = "SELECT zip_code_prefix, lat, lng FROM core.geolocation"
SELLERS_SQL = "SELECT seller_id, zip_code_prefix, state FROM core.sellers"

TARGET = "is_late"
NUMERIC_FEATURES = [
    "distance_km",
    "same_state",
    "estimated_days",
    "route_expected_days",
    "promise_slack_days",
    "n_items",
    "total_weight_g",
    "order_value",
    "freight_value",
    "seller_past_orders",
    "seller_past_late_rate",
    "seller_dispatch_days",
    "platform_delivery_days_14d",
    "platform_orders_7d",
]
CATEGORICAL_FEATURES = ["customer_state"]
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
STATE_DTYPE = pd.CategoricalDtype(categories=sorted(STATE_TO_REGION))

EARTH_RADIUS_KM = 6371.0
SELLER_PRIOR_RATE = 0.05
PRIOR_WEIGHT = 10
ROUTE_WINDOW = pd.Timedelta(days=60)
PLATFORM_WINDOW = pd.Timedelta(days=14)
LOAD_WINDOW = pd.Timedelta(days=7)
DATA_START = "2017-01-01"
# Même précision des dates des deux côtés des jointures temporelles, quelle
# que soit leur origine (base, fichiers, requête de l'API).
TIME_RESOLUTION = "datetime64[ns]"
DATA_END = "2018-09-01"


class TimeAwareHistory:
    """Sommes et effectifs d'événements passés, connus à une date donnée.

    Pour chaque ligne de `queries` (clé de regroupement + date `at`), on
    agrège les événements de même clé survenus strictement avant `at`
    (et après `at - window` si une fenêtre est donnée). Le calcul utilise
    des cumuls et deux `merge_asof`, donc il reste rapide sur 100 000 lignes.
    """

    def __init__(self, events: pd.DataFrame, keys: list[str],
                 time: str, value: str) -> None:
        self.keys = keys
        self.events = (
            events[keys + [time, value]]
            .dropna(subset=[time, value])
            .rename(columns={time: "event_time"})
            .astype({"event_time": TIME_RESOLUTION})
            .sort_values("event_time")
        )
        grouped = self.events.groupby(keys)[value]
        self.events["cum_sum"] = grouped.cumsum()
        self.events["cum_count"] = grouped.cumcount() + 1

    def totals_at(self, queries: pd.DataFrame,
                  at: pd.Series) -> np.ndarray:
        """Cumuls (somme, effectif) juste avant chaque date `at`."""
        lookup = queries[self.keys].assign(
            at=at.to_numpy().astype(self.events["event_time"].dtype),
            row=np.arange(len(queries)),
        ).sort_values("at")
        merged = pd.merge_asof(
            lookup,
            self.events[self.keys + ["event_time", "cum_sum", "cum_count"]],
            left_on="at", right_on="event_time", by=self.keys,
            allow_exact_matches=False,
        ).sort_values("row")
        return merged[["cum_sum", "cum_count"]].fillna(0).to_numpy()

    def window(self, queries: pd.DataFrame, at: pd.Series,
               window: pd.Timedelta | None = None) -> pd.DataFrame:
        """Somme et effectif sur la fenêtre [at - window, at[."""
        totals = self.totals_at(queries, at)
        if window is not None:
            totals = totals - self.totals_at(queries, at - window)
        return pd.DataFrame(totals, columns=["sum", "count"],
                            index=queries.index)

    @staticmethod
    def smoothed_mean(window: pd.DataFrame, prior: pd.Series | float,
                      weight: float = PRIOR_WEIGHT) -> pd.Series:
        """Moyenne lissée vers un a priori quand il y a peu d'événements."""
        return (window["sum"] + weight * prior) / (window["count"] + weight)


class DelayFeatureBuilder:
    """Construit la table « une ligne par commande livrée » du modèle."""

    def __init__(self, warehouse: DataWarehouse | None = None) -> None:
        self.warehouse = warehouse or DataWarehouse()

    def build(self) -> pd.DataFrame:
        """Table complète : identifiants, variables, cible et région."""
        return self.build_from(self.load())

    def build_from(self, raw: pd.DataFrame) -> pd.DataFrame:
        """Même calcul à partir de commandes déjà chargées (colonnes de
        DELAY_ORDERS_SQL)."""
        frame = self.prepare(raw)
        frame = self.add_geography(frame)
        frame = self.add_history(frame, DelayHistory(frame))
        frame = frame[
            (frame["purchase_timestamp"] >= DATA_START)
            & (frame["purchase_timestamp"] < DATA_END)
        ].copy()
        frame["customer_state"] = frame["customer_state"].astype(STATE_DTYPE)
        frame["customer_region"] = frame["customer_state"].astype(str).map(
            BrazilRegions.of
        )
        columns = ["order_id", "purchase_timestamp", "customer_region"]
        return (
            frame[columns + FEATURES + [TARGET]]
            .sort_values(["purchase_timestamp", "order_id"])
            .reset_index(drop=True)
        )

    def load(self) -> pd.DataFrame:
        frame = self.warehouse.query(DELAY_ORDERS_SQL)
        for column in ("order_value", "freight_value", "total_weight_g"):
            frame[column] = frame[column].astype(float)
        return frame

    @staticmethod
    def prepare(frame: pd.DataFrame) -> pd.DataFrame:
        """Cible, délais réels et promis, dates de connaissance."""
        frame = frame.copy()
        purchase_day = frame["purchase_timestamp"].dt.normalize()
        promised_day = frame["estimated_delivery_date"].dt.normalize()
        delivered_day = frame["delivered_customer_date"].dt.normalize()
        frame[TARGET] = (delivered_day > promised_day).astype(int)
        frame["known_at"] = frame["delivered_customer_date"].where(
            frame[TARGET] == 0, promised_day + pd.Timedelta(days=1)
        )
        frame["estimated_days"] = (promised_day - purchase_day).dt.days
        frame["delivery_days"] = (delivered_day - purchase_day).dt.days
        frame["dispatch_days"] = (
            frame["delivered_carrier_date"].dt.normalize() - purchase_day
        ).dt.days.clip(lower=0)
        frame["route"] = frame["seller_state"] + ">" + frame["customer_state"]
        frame["platform"] = "all"
        frame["one"] = 1
        return frame

    @staticmethod
    def haversine_km(lat1: pd.Series, lng1: pd.Series,
                     lat2: pd.Series, lng2: pd.Series) -> pd.Series:
        """Distance à vol d'oiseau entre deux points GPS, en km."""
        lat1, lng1, lat2, lng2 = (
            np.radians(values) for values in (lat1, lng1, lat2, lng2)
        )
        step = (
            np.sin((lat2 - lat1) / 2) ** 2
            + np.cos(lat1) * np.cos(lat2) * np.sin((lng2 - lng1) / 2) ** 2
        )
        return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(step))

    def add_geography(self, frame: pd.DataFrame) -> pd.DataFrame:
        frame = frame.copy()
        frame["distance_km"] = self.haversine_km(
            frame["customer_lat"], frame["customer_lng"],
            frame["seller_lat"], frame["seller_lng"],
        )
        frame["same_state"] = (
            frame["customer_state"] == frame["seller_state"]
        ).astype(int)
        return frame

    @staticmethod
    def add_history(frame: pd.DataFrame,
                    history: "DelayHistory") -> pd.DataFrame:
        """Historiques connus à la date d'achat de chaque commande, et marge
        de la promesse (délai promis - délai réel attendu du trajet)."""
        frame = frame.join(history.features(frame))
        frame["promise_slack_days"] = (
            frame["estimated_days"] - frame["route_expected_days"]
        )
        return frame


class DelayHistory:
    """Historiques connus à une date donnée : vendeur, trajet, plateforme.

    Construit une fois sur les commandes livrées, il sert à l'entraînement
    (une requête par commande, à sa date d'achat) comme à l'API (une requête
    pour la nouvelle commande) : les variables sont donc calculées
    exactement de la même façon des deux côtés.
    """

    def __init__(self, frame: pd.DataFrame) -> None:
        self.seller_late = TimeAwareHistory(frame, ["seller_id"], "known_at",
                                            TARGET)
        self.seller_dispatch = TimeAwareHistory(
            frame, ["seller_id"], "delivered_carrier_date", "dispatch_days"
        )
        self.platform_dispatch = TimeAwareHistory(
            frame, ["platform"], "delivered_carrier_date", "dispatch_days"
        )
        self.deliveries = {
            keys[0]: TimeAwareHistory(frame, keys, "delivered_customer_date",
                                      "delivery_days")
            for keys in (["platform"], ["customer_state"], ["route"])
        }
        self.orders = TimeAwareHistory(frame, ["platform"],
                                       "purchase_timestamp", "one")

    def features(self, queries: pd.DataFrame) -> pd.DataFrame:
        """Variables d'historique de chaque requête (colonnes seller_id,
        customer_state, route, platform et purchase_timestamp).

        - vendeur : volume, taux de retard (lissé vers 5 %) et délai de
          remise au transporteur (lissé vers la moyenne de la plateforme) ;
        - trajet : délai réel moyen des 60 derniers jours, lissé vers celui
          de l'état du client puis de la plateforme ;
        - plateforme : délai moyen des livraisons des 14 derniers jours et
          nombre de commandes des 7 derniers jours.
        """
        at = queries["purchase_timestamp"]
        result = pd.DataFrame(index=queries.index)
        late = self.seller_late.window(queries, at)
        result["seller_past_orders"] = late["count"]
        result["seller_past_late_rate"] = TimeAwareHistory.smoothed_mean(
            late, SELLER_PRIOR_RATE
        )
        dispatch = self.platform_dispatch.window(queries, at, ROUTE_WINDOW)
        result["seller_dispatch_days"] = TimeAwareHistory.smoothed_mean(
            self.seller_dispatch.window(queries, at),
            dispatch["sum"] / dispatch["count"],
        )
        windows = {
            name: history.window(queries, at, ROUTE_WINDOW)
            for name, history in self.deliveries.items()
        }
        platform_mean = windows["platform"]["sum"] / windows["platform"][
            "count"
        ]
        state_mean = TimeAwareHistory.smoothed_mean(
            windows["customer_state"], platform_mean
        )
        result["route_expected_days"] = TimeAwareHistory.smoothed_mean(
            windows["route"], state_mean
        )
        speed = self.deliveries["platform"].window(queries, at,
                                                   PLATFORM_WINDOW)
        result["platform_delivery_days_14d"] = (
            speed["sum"] / speed["count"]
        ).where(speed["count"] > 0)
        result["platform_orders_7d"] = self.orders.window(
            queries, at, LOAD_WINDOW
        )["count"]
        return result


class UnknownSellerError(KeyError):
    """Le vendeur demandé n'existe pas dans les données chargées."""


class DelayServingSnapshot:
    """Ce dont l'API a besoin pour calculer les variables d'une nouvelle
    commande : historiques, coordonnées des codes postaux, vendeurs connus
    et date de référence. Les données s'arrêtant fin août 2018, l'état
    « actuel » du réseau est celui de cette date."""

    def __init__(self, history: DelayHistory, geolocation: pd.DataFrame,
                 sellers: pd.DataFrame,
                 reference_time: pd.Timestamp) -> None:
        self.history = history
        self.geolocation = geolocation
        self.sellers = sellers
        self.reference_time = reference_time

    @staticmethod
    def build(warehouse: DataWarehouse | None = None
              ) -> "DelayServingSnapshot":
        warehouse = warehouse or DataWarehouse()
        builder = DelayFeatureBuilder(warehouse)
        frame = builder.prepare(builder.load())
        return DelayServingSnapshot(
            DelayHistory(frame),
            warehouse.query(GEOLOCATION_SQL).set_index("zip_code_prefix"),
            warehouse.query(SELLERS_SQL).set_index("seller_id"),
            pd.Timestamp(DATA_END),
        )

    def coordinates(self, zip_code_prefix: str) -> tuple[float, float]:
        if zip_code_prefix not in self.geolocation.index:
            return np.nan, np.nan
        point = self.geolocation.loc[zip_code_prefix]
        return float(point["lat"]), float(point["lng"])

    def features(self, order: dict,
                 at: pd.Timestamp | None = None) -> pd.DataFrame:
        """Variables du modèle pour une commande décrite par : code postal
        et état du client, identifiant du vendeur, délai promis (jours) et
        articles (prix, frais de port, poids). Les historiques sont ceux
        connus à la date `at` (par défaut, la date de référence)."""
        if order["seller_id"] not in self.sellers.index:
            raise UnknownSellerError(order["seller_id"])
        seller = self.sellers.loc[order["seller_id"]]
        state = order["customer_state"]
        query = pd.DataFrame([{
            "seller_id": order["seller_id"],
            "customer_state": state,
            "route": f"{seller['state']}>{state}",
            "platform": "all",
            "purchase_timestamp": at or self.reference_time,
        }])
        history = self.history.features(query).iloc[0].to_dict()
        customer_lat, customer_lng = self.coordinates(
            order["customer_zip_prefix"]
        )
        seller_lat, seller_lng = self.coordinates(seller["zip_code_prefix"])
        items = order["items"]
        weights = [item["weight_g"] for item in items
                   if item.get("weight_g") is not None]
        row = {
            "distance_km": float(DelayFeatureBuilder.haversine_km(
                customer_lat, customer_lng, seller_lat, seller_lng
            )),
            "same_state": int(seller["state"] == state),
            "estimated_days": order["estimated_days"],
            "n_items": len(items),
            "total_weight_g": float(sum(weights)) if weights else np.nan,
            "order_value": float(sum(item["price"] for item in items)),
            "freight_value": float(sum(item["freight_value"]
                                       for item in items)),
            "customer_state": state,
            **history,
        }
        row["promise_slack_days"] = (
            row["estimated_days"] - row["route_expected_days"]
        )
        features = pd.DataFrame([row])[FEATURES]
        features["customer_state"] = features["customer_state"].astype(
            STATE_DTYPE
        )
        return features
