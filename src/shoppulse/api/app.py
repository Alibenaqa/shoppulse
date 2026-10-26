"""Application FastAPI de ShopPulse.

Lancement local : uvicorn shoppulse.api.app:app --reload
Documentation interactive : http://localhost:8000/docs
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse

from shoppulse.api.predictors import ModelRegistry, ModelUnavailableError
from shoppulse.api.schemas import (
    DelayRequest,
    DelayResponse,
    HealthResponse,
    SegmentRequest,
    SegmentResponse,
    SentimentRequest,
    SentimentResponse,
)
from shoppulse.config import MODELS_DIR
from shoppulse.features import UnknownSellerError

DESCRIPTION = """
API des modèles ShopPulse, un endpoint par modèle :

- **logistique** : risque de retard d'une commande au moment de l'achat ;
- **service client** : sentiment d'un avis client (portugais) ;
- **marketing** : persona d'un client et campagne recommandée.

Les modèles sont entraînés par `pipelines/train_flow.py` et lus dans le
dossier `models/`. Usage : aide à la décision uniquement (voir
`docs/ethique.md`).
"""
UNAVAILABLE = {503: {"description": "Modèle non entraîné ou introuvable"}}


class ShopPulseApi:
    """Construit l'application et ses routes autour des modèles chargés."""

    def __init__(self, models_dir: Path = MODELS_DIR) -> None:
        self.registry = ModelRegistry(models_dir)
        self.app = FastAPI(title="ShopPulse API", version="1.0.0",
                           description=DESCRIPTION)
        self.add_routes()

    def predictor(self, name: str) -> object:
        try:
            return self.registry.require(name)
        except ModelUnavailableError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    def add_routes(self) -> None:
        """Routes FastAPI (fonctions imposées par le framework, qui
        délèguent aux prédicteurs)."""
        app = self.app

        @app.get("/", include_in_schema=False)
        def home() -> RedirectResponse:
            return RedirectResponse(url="/docs")

        @app.get("/health", response_model=HealthResponse,
                 tags=["service"], summary="État du service et des modèles")
        def health() -> HealthResponse:
            return self.registry.health()

        @app.post("/predict/delay", response_model=DelayResponse,
                  tags=["logistique"],
                  summary="Risque de retard d'une commande",
                  responses={404: {"description": "Vendeur inconnu"},
                             **UNAVAILABLE})
        def predict_delay(request: DelayRequest) -> DelayResponse:
            predictor = self.predictor("delay")
            try:
                return predictor.predict(request)
            except UnknownSellerError as error:
                raise HTTPException(
                    status_code=404,
                    detail=f"Vendeur inconnu : {request.seller_id}",
                ) from error

        @app.post("/predict/sentiment", response_model=SentimentResponse,
                  tags=["service client"],
                  summary="Sentiment d'un avis client", responses=UNAVAILABLE)
        def predict_sentiment(request: SentimentRequest) -> SentimentResponse:
            return self.predictor("sentiment").predict(request)

        @app.post("/predict/segment", response_model=SegmentResponse,
                  tags=["marketing"],
                  summary="Persona d'un client et campagne recommandée",
                  responses=UNAVAILABLE)
        def predict_segment(request: SegmentRequest) -> SegmentResponse:
            return self.predictor("segment").predict(request)


def create_app(models_dir: Path | None = None) -> FastAPI:
    return ShopPulseApi(models_dir or MODELS_DIR).app


app = create_app()
