"""Segmentation clients : scores RFM, clustering K-means et personas."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from shoppulse.config import MODELS_DIR
from shoppulse.warehouse import DataWarehouse

RFM_SQL = """
WITH reference AS (
    SELECT MAX(purchase_timestamp)::DATE + 1 AS ref_date FROM core.orders
),
order_value AS (
    SELECT order_id, SUM(payment_value) AS value
    FROM core.order_payments
    GROUP BY order_id
)
SELECT c.customer_unique_id,
    MIN(c.state) AS state,
    (SELECT ref_date FROM reference)
        - MAX(o.purchase_timestamp)::DATE AS recency,
    COUNT(DISTINCT o.order_id) AS frequency,
    SUM(v.value) AS monetary
FROM core.orders AS o
JOIN core.customers AS c ON c.customer_id = o.customer_id
JOIN order_value AS v ON v.order_id = o.order_id
WHERE o.status NOT IN ('canceled', 'unavailable')
GROUP BY c.customer_unique_id
"""
RFM_COLUMNS = ["recency", "frequency", "monetary"]
SEGMENTATION_PATH = MODELS_DIR / "segmentation.joblib"
K_CANDIDATES = range(3, 8)
SILHOUETTE_SAMPLE = 15000
RANDOM_STATE = 42

PERSONA_LOYAL = "Fidèles multi-acheteurs"
PERSONA_NEW = "Nouveaux clients récents"
PERSONA_DORMANT = "Gros acheteurs endormis"
PERSONA_LOST = "Petits acheteurs perdus"


class RfmTable:
    """Calcule la table RFM par client réel (customer_unique_id)."""

    def __init__(self, warehouse: DataWarehouse) -> None:
        self.warehouse = warehouse

    def load(self) -> pd.DataFrame:
        frame = self.warehouse.query(RFM_SQL)
        frame["monetary"] = frame["monetary"].astype(float)
        return self.add_scores(frame)

    @staticmethod
    def add_scores(frame: pd.DataFrame) -> pd.DataFrame:
        """Scores de 1 à 5 : quintiles pour R et M, paliers pour F.

        97 % des clients n'ont qu'une commande : des quintiles sur F
        n'auraient pas de sens, on utilise 1 / 2 / 3+ commandes.
        """
        scored = frame.copy()
        scored["r_score"] = pd.qcut(
            scored["recency"].rank(method="first"), 5,
            labels=[5, 4, 3, 2, 1],
        ).astype(int)
        scored["f_score"] = scored["frequency"].clip(upper=3)
        scored["m_score"] = pd.qcut(
            scored["monetary"].rank(method="first"), 5,
            labels=[1, 2, 3, 4, 5],
        ).astype(int)
        return scored


class CustomerSegmenter:
    """K-means sur les valeurs RFM (log + standardisation), puis personas.

    Le nombre de clusters est choisi par le score de silhouette. Les
    personas sont attribuées par des règles sur les centres des clusters,
    ce qui les rend indépendantes de la numérotation aléatoire de K-means.
    """

    def __init__(self, n_clusters: int | None = None) -> None:
        self.n_clusters = n_clusters
        self.scaler = StandardScaler()
        self.model: KMeans | None = None
        self.silhouettes: dict[int, float] = {}
        self.personas: dict[int, str] = {}

    def features(self, frame: pd.DataFrame) -> np.ndarray:
        return np.log1p(frame[RFM_COLUMNS].to_numpy(dtype=float))

    def choose_k(self, features: np.ndarray) -> int:
        """Nombre de clusters qui maximise la silhouette (échantillon)."""
        rng = np.random.default_rng(RANDOM_STATE)
        size = min(SILHOUETTE_SAMPLE, len(features))
        sample = rng.choice(len(features), size, replace=False)
        for k in K_CANDIDATES:
            labels = KMeans(k, n_init=10, random_state=RANDOM_STATE).fit(
                features
            ).labels_
            self.silhouettes[k] = silhouette_score(
                features[sample], labels[sample]
            )
        return max(self.silhouettes, key=self.silhouettes.get)

    def fit_predict(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Ajoute les colonnes cluster et persona à la table RFM."""
        features = self.scaler.fit_transform(self.features(frame))
        if self.n_clusters is None:
            self.n_clusters = self.choose_k(features)
        self.model = KMeans(self.n_clusters, n_init=10,
                            random_state=RANDOM_STATE)
        segmented = frame.copy()
        segmented["cluster"] = self.model.fit_predict(features)
        self.personas = self.name_personas(self.profile(segmented))
        segmented["persona"] = segmented["cluster"].map(self.personas)
        return segmented

    def predict(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Cluster et persona de nouveaux clients (colonnes recency,
        frequency, monetary), avec le modèle déjà entraîné."""
        clusters = self.model.predict(
            self.scaler.transform(self.features(frame))
        )
        return pd.DataFrame({
            "cluster": clusters,
            "persona": [self.personas[cluster] for cluster in clusters],
        }, index=frame.index)

    def save(self, path: Path = SEGMENTATION_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({
            "segmenter": self,
            "trained_at": datetime.now().isoformat(timespec="seconds"),
        }, path)

    @staticmethod
    def load(path: Path = SEGMENTATION_PATH) -> "CustomerSegmenter":
        return joblib.load(path)["segmenter"]

    @staticmethod
    def profile(segmented: pd.DataFrame,
                by: str = "cluster") -> pd.DataFrame:
        """Profil moyen et taille de chaque groupe."""
        profile = segmented.groupby(by).agg(
            customers=("customer_unique_id", "count"),
            recency=("recency", "mean"),
            frequency=("frequency", "mean"),
            monetary=("monetary", "mean"),
            total_value=("monetary", "sum"),
        )
        profile["share_pct"] = 100 * profile["customers"] / len(segmented)
        profile["value_share_pct"] = (
            100 * profile["total_value"] / profile["total_value"].sum()
        )
        return profile

    @staticmethod
    def name_personas(profile: pd.DataFrame) -> dict[int, str]:
        """Règles : la plus forte fréquence -> fidèles ; parmi le reste, la
        plus faible récence -> nouveaux ; puis le plus gros montant ->
        endormis ; les autres clusters -> perdus."""
        remaining = profile.copy()
        names = {}
        for column, pick, persona in (
            ("frequency", "idxmax", PERSONA_LOYAL),
            ("recency", "idxmin", PERSONA_NEW),
            ("monetary", "idxmax", PERSONA_DORMANT),
        ):
            if remaining.empty:
                break
            cluster = getattr(remaining[column], pick)()
            names[cluster] = persona
            remaining = remaining.drop(index=cluster)
        names.update({cluster: PERSONA_LOST for cluster in remaining.index})
        return names


@dataclass(frozen=True)
class Campaign:
    """Une campagne marketing et ses hypothèses (à valider par A/B test)."""

    name: str
    persona: str
    action: str
    contact_cost: float
    conversion_rate: float
    baseline_rate: float
    incentive_rate: float


@dataclass
class CampaignForecast:
    """Résultat chiffré d'une campagne sur son segment cible."""

    campaign: Campaign
    target_customers: int
    avg_basket: float

    @property
    def extra_orders(self) -> float:
        uplift = self.campaign.conversion_rate - self.campaign.baseline_rate
        return self.target_customers * uplift

    @property
    def extra_revenue(self) -> float:
        return self.extra_orders * self.avg_basket

    @property
    def cost(self) -> float:
        converted = self.target_customers * self.campaign.conversion_rate
        incentive = converted * self.avg_basket * self.campaign.incentive_rate
        return self.target_customers * self.campaign.contact_cost + incentive

    @property
    def net_gain(self) -> float:
        return self.extra_revenue - self.cost

    @property
    def roi(self) -> float:
        return self.net_gain / self.cost if self.cost else 0.0


DEFAULT_CAMPAIGNS = [
    Campaign(
        "Club VIP", PERSONA_LOYAL,
        "Accès anticipé aux promotions et livraison offerte",
        contact_cost=0.10, conversion_rate=0.15, baseline_rate=0.05,
        incentive_rate=0.10,
    ),
    Campaign(
        "Relance 2e commande à J+20", PERSONA_NEW,
        "E-mail + coupon de 10 % envoyé 20 jours après le 1er achat",
        contact_cost=0.05, conversion_rate=0.05, baseline_rate=0.02,
        incentive_rate=0.10,
    ),
    Campaign(
        "Reconquête des gros paniers", PERSONA_DORMANT,
        "Sélection personnalisée dans leur catégorie + frais de port "
        "offerts",
        contact_cost=0.05, conversion_rate=0.03, baseline_rate=0.01,
        incentive_rate=0.12,
    ),
]


class CampaignCatalog:
    """Campagne recommandée pour chaque persona (aucune pour les petits
    acheteurs perdus, trop peu rentables)."""

    @staticmethod
    def for_persona(persona: str,
                    campaigns: list[Campaign] | None = None
                    ) -> Campaign | None:
        return next(
            (campaign for campaign in campaigns or DEFAULT_CAMPAIGNS
             if campaign.persona == persona),
            None,
        )


class CampaignSimulator:
    """Chiffre les campagnes à partir des segments obtenus."""

    def __init__(self, segmented: pd.DataFrame,
                 campaigns: list[Campaign] | None = None) -> None:
        self.segmented = segmented
        self.campaigns = campaigns or DEFAULT_CAMPAIGNS

    def forecast(self, campaign: Campaign) -> CampaignForecast:
        target = self.segmented[self.segmented["persona"] == campaign.persona]
        avg_basket = float(
            (target["monetary"] / target["frequency"]).mean()
        )
        return CampaignForecast(campaign, len(target), avg_basket)

    def summary(self) -> pd.DataFrame:
        rows = []
        for campaign in self.campaigns:
            forecast = self.forecast(campaign)
            rows.append({
                "campagne": campaign.name,
                "persona": campaign.persona,
                "clients ciblés": forecast.target_customers,
                "panier moyen (R$)": round(forecast.avg_basket, 2),
                "commandes en plus": round(forecast.extra_orders),
                "CA additionnel (R$)": round(forecast.extra_revenue),
                "coût (R$)": round(forecast.cost),
                "gain net (R$)": round(forecast.net_gain),
                "ROI": round(forecast.roi, 2),
            })
        return pd.DataFrame(rows)


class SegmentationJob:
    """Calcule la segmentation, l'enregistre dans mart.customer_segments
    et sauvegarde le modèle pour l'API."""

    def __init__(self, warehouse: DataWarehouse | None = None,
                 model_path: Path = SEGMENTATION_PATH) -> None:
        self.warehouse = warehouse or DataWarehouse()
        self.model_path = model_path

    def run(self) -> pd.DataFrame:
        segmenter = CustomerSegmenter()
        segmented = segmenter.fit_predict(RfmTable(self.warehouse).load())
        self.warehouse.write(segmented, "mart", "customer_segments")
        segmenter.save(self.model_path)
        return CustomerSegmenter.profile(segmented, by="persona")
