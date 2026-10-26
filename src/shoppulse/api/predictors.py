"""Chargement des modèles entraînés et prédictions de l'API."""

from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

import joblib
import numpy as np
import pandas as pd

from shoppulse.api.schemas import (
    DelayRequest,
    DelayResponse,
    HealthResponse,
    SegmentRequest,
    SegmentResponse,
    SentimentRequest,
    SentimentResponse,
)
from shoppulse.features import DelayServingSnapshot
from shoppulse.geography import BrazilRegions
from shoppulse.segmentation import CampaignCatalog, CustomerSegmenter
from shoppulse.text import TextNormalizer

DELAY_MODEL_FILE = "delay_model.joblib"
DELAY_SNAPSHOT_FILE = "delay_snapshot.joblib"
SENTIMENT_FILE = "sentiment_model.joblib"
SEGMENTATION_FILE = "segmentation.joblib"


class ModelUnavailableError(RuntimeError):
    """Le modèle demandé n'a pas pu être chargé (pas encore entraîné ?)."""


class DelayPredictor:
    """Risque de retard d'une commande, avec le seuil de sa région."""

    def __init__(self, artifact: dict,
                 snapshot: DelayServingSnapshot) -> None:
        self.artifact = artifact
        self.snapshot = snapshot

    @staticmethod
    def load(models_dir: Path) -> "DelayPredictor":
        return DelayPredictor(joblib.load(models_dir / DELAY_MODEL_FILE),
                              joblib.load(models_dir / DELAY_SNAPSHOT_FILE))

    def threshold(self, region: str) -> float:
        return float(self.artifact["region_thresholds"].get(
            region, self.artifact["threshold"]
        ))

    def predict(self, request: DelayRequest) -> DelayResponse:
        features = self.snapshot.features(request.model_dump())
        probability = float(
            self.artifact["model"].predict_proba(features)[0, 1]
        )
        region = BrazilRegions.of(request.customer_state)
        threshold = self.threshold(region)
        row = features.iloc[0]
        return DelayResponse(
            late_probability=round(probability, 4),
            risk="élevé" if probability >= threshold else "normal",
            threshold=round(threshold, 4),
            region=region,
            model=self.artifact["model_name"],
            reference_date=self.snapshot.reference_time.date().isoformat(),
            features={
                name: self.serializable(row[name]) for name in features
            },
        )

    @staticmethod
    def serializable(value: object) -> float | str | None:
        if isinstance(value, str):
            return value
        value = float(value)
        return None if np.isnan(value) else round(value, 4)


class SentimentPredictor:
    """Probabilité qu'un avis soit négatif."""

    def __init__(self, metadata: dict,
                 predict_proba: Callable[[pd.Series], np.ndarray]) -> None:
        self.metadata = metadata
        self.predict_proba = predict_proba

    @staticmethod
    def load(models_dir: Path) -> "SentimentPredictor":
        """Le modèle TF-IDF se charge sans PyTorch ; le réseau GRU, s'il
        était retenu, demanderait d'installer le groupe « pipeline »."""
        metadata = joblib.load(models_dir / SENTIMENT_FILE)
        path = models_dir / metadata["path"]
        if path.suffix == ".joblib":
            pipeline = joblib.load(path)["pipeline"]
            return SentimentPredictor(
                metadata, lambda texts: pipeline.predict_proba(texts)[:, 1]
            )
        from shoppulse.sentiment import NeuralSentimentModel

        return SentimentPredictor(
            metadata, NeuralSentimentModel.load(path).predict_proba
        )

    def predict(self, request: SentimentRequest) -> SentimentResponse:
        text = pd.Series([TextNormalizer.clean(request.text)])
        probability = float(self.predict_proba(text)[0])
        threshold = float(self.metadata["threshold"])
        return SentimentResponse(
            negative_probability=round(probability, 4),
            sentiment="négatif" if probability >= threshold else "positif",
            threshold=round(threshold, 4),
            model=self.metadata["model_name"],
        )


class SegmentPredictor:
    """Persona d'un client à partir de ses indicateurs RFM."""

    def __init__(self, segmenter: CustomerSegmenter) -> None:
        self.segmenter = segmenter

    @staticmethod
    def load(models_dir: Path) -> "SegmentPredictor":
        return SegmentPredictor(
            CustomerSegmenter.load(models_dir / SEGMENTATION_FILE)
        )

    def predict(self, request: SegmentRequest) -> SegmentResponse:
        frame = pd.DataFrame([{
            "recency": request.recency_days,
            "frequency": request.frequency,
            "monetary": request.monetary,
        }])
        prediction = self.segmenter.predict(frame).iloc[0]
        campaign = CampaignCatalog.for_persona(prediction["persona"])
        return SegmentResponse(
            cluster=int(prediction["cluster"]),
            persona=prediction["persona"],
            campaign=campaign.name if campaign else None,
            action=campaign.action if campaign else None,
        )


class ModelRegistry:
    """Charge chaque modèle au démarrage ; un modèle absent n'empêche pas
    les autres de fonctionner (son endpoint répond alors 503)."""

    LOADERS: ClassVar[dict[str, Callable[[Path], object]]] = {
        "delay": DelayPredictor.load,
        "sentiment": SentimentPredictor.load,
        "segment": SegmentPredictor.load,
    }

    def __init__(self, models_dir: Path) -> None:
        self.models_dir = models_dir
        self.predictors: dict[str, object] = {}
        self.errors: dict[str, str] = {}
        for name, loader in self.LOADERS.items():
            try:
                self.predictors[name] = loader(models_dir)
            except (FileNotFoundError, KeyError, ValueError) as error:
                self.errors[name] = f"{type(error).__name__}: {error}"

    def require(self, name: str) -> object:
        if name not in self.predictors:
            raise ModelUnavailableError(
                f"Modèle « {name} » indisponible dans {self.models_dir} : "
                "lancez pipelines/olist_flow.py puis pipelines/train_flow.py"
            )
        return self.predictors[name]

    def health(self) -> HealthResponse:
        return HealthResponse(
            status="ok" if not self.errors else "dégradé",
            models={name: name in self.predictors for name in self.LOADERS},
            errors=self.errors,
        )
