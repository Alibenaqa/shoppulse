"""Schémas d'entrée et de sortie de l'API (validation Pydantic).

Chaque champ est décrit et accompagné d'un exemple : la documentation
OpenAPI (/docs) permet ainsi de tester l'API sans rien écrire.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shoppulse.geography import STATE_TO_REGION

EXAMPLE_SELLER = "6560211a19b47992c3666cc44a7e94c0"


class OrderItem(BaseModel):
    """Un article de la commande."""

    price: float = Field(gt=0, le=100_000, description="Prix (R$)")
    freight_value: float = Field(ge=0, le=10_000,
                                 description="Frais de port (R$)")
    weight_g: float | None = Field(default=None, ge=0, le=500_000,
                                   description="Poids (g), si connu")


class DelayRequest(BaseModel):
    """Une commande au moment de l'achat."""

    model_config = ConfigDict(json_schema_extra={"examples": [{
        "customer_zip_prefix": "65010",
        "customer_state": "MA",
        "seller_id": EXAMPLE_SELLER,
        "estimated_days": 12,
        "items": [{"price": 89.9, "freight_value": 32.5, "weight_g": 1200}],
    }]})

    customer_zip_prefix: str = Field(
        pattern=r"^\d{5}$",
        description="5 premiers chiffres du code postal du client",
    )
    customer_state: str = Field(description="État du client (ex. SP, RJ)")
    seller_id: str = Field(pattern=r"^[0-9a-f]{32}$",
                           description="Identifiant du vendeur (Olist)")
    estimated_days: int = Field(ge=1, le=200,
                                description="Délai de livraison promis "
                                            "au client (jours)")
    items: list[OrderItem] = Field(min_length=1, max_length=50)

    @field_validator("customer_state")
    @classmethod
    def known_state(cls, value: str) -> str:
        state = value.strip().upper()
        if state not in STATE_TO_REGION:
            raise ValueError(f"état inconnu : {value}")
        return state


class DelayResponse(BaseModel):
    """Risque de retard de la commande."""

    late_probability: float = Field(description="Score de risque (0 à 1)")
    risk: Literal["élevé", "normal"] = Field(
        description="« élevé » : commande à surveiller en priorité"
    )
    threshold: float = Field(description="Seuil de la région du client")
    region: str
    model: str
    reference_date: str = Field(
        description="Date de l'état du réseau utilisé (fin des données)"
    )
    features: dict[str, float | str | None] = Field(
        description="Variables calculées pour cette commande"
    )


class SentimentRequest(BaseModel):
    """Un avis client (en portugais)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{
        "text": "Produto não chegou e ninguém responde. Péssimo!",
    }]})

    text: str = Field(min_length=1, max_length=5000,
                      description="Titre et/ou texte de l'avis")

    @field_validator("text")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("l'avis est vide")
        return value


class SentimentResponse(BaseModel):
    """Sentiment de l'avis."""

    negative_probability: float = Field(
        description="Probabilité que l'avis soit négatif (0 à 1)"
    )
    sentiment: Literal["négatif", "positif"]
    threshold: float
    model: str


class SegmentRequest(BaseModel):
    """Indicateurs RFM d'un client."""

    model_config = ConfigDict(json_schema_extra={"examples": [{
        "recency_days": 320, "frequency": 1, "monetary": 450.0,
    }]})

    recency_days: int = Field(ge=0, le=5000,
                              description="Jours depuis le dernier achat")
    frequency: int = Field(ge=1, le=1000, description="Nombre de commandes")
    monetary: float = Field(gt=0, le=1_000_000,
                            description="Montant total dépensé (R$)")


class SegmentResponse(BaseModel):
    """Persona du client et campagne recommandée."""

    cluster: int
    persona: str
    campaign: str | None = Field(
        description="Campagne recommandée (aucune si non rentable)"
    )
    action: str | None


class HealthResponse(BaseModel):
    """État du service et des modèles chargés."""

    status: Literal["ok", "dégradé"]
    models: dict[str, bool]
    errors: dict[str, str]
