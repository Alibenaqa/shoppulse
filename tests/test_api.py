"""API FastAPI : réponses, validation des entrées et modèles absents."""

import pytest
from fastapi.testclient import TestClient

from shoppulse.api.app import create_app
from shoppulse.features import FEATURES
from shoppulse.segmentation import (
    PERSONA_DORMANT,
    PERSONA_LOST,
    PERSONA_LOYAL,
    PERSONA_NEW,
)


@pytest.fixture(scope="module")
def client(models_dir) -> TestClient:
    return TestClient(create_app(models_dir))


@pytest.fixture
def order(delay_snapshot) -> dict:
    return {
        "customer_zip_prefix": "20001",
        "customer_state": "rj",
        "seller_id": str(delay_snapshot.sellers.index[0]),
        "estimated_days": 15,
        "items": [{"price": 89.9, "freight_value": 20.0, "weight_g": 800}],
    }


class TestService:
    def test_home_redirects_to_the_documentation(self, client) -> None:
        response = client.get("/", follow_redirects=False)
        assert response.status_code in (302, 307)
        assert response.headers["location"] == "/docs"

    def test_health_lists_loaded_models(self, client) -> None:
        body = client.get("/health").json()
        assert body["status"] == "ok"
        assert body["models"] == {"delay": True, "sentiment": True,
                                  "segment": True}

    def test_openapi_documents_one_endpoint_per_model(self, client) -> None:
        paths = client.get("/openapi.json").json()["paths"]
        assert {"/predict/delay", "/predict/sentiment",
                "/predict/segment"} <= set(paths)


class TestDelayEndpoint:
    def test_valid_order(self, client, order) -> None:
        response = client.post("/predict/delay", json=order)
        assert response.status_code == 200
        body = response.json()
        assert 0 <= body["late_probability"] <= 1
        assert body["risk"] in {"élevé", "normal"}
        assert body["region"] == "Sudeste"
        assert set(body["features"]) == set(FEATURES)

    @pytest.mark.parametrize("field, value", [
        ("customer_state", "XX"),
        ("customer_zip_prefix", "123"),
        ("estimated_days", 0),
        ("items", []),
    ])
    def test_invalid_inputs_are_rejected(self, client, order, field,
                                         value) -> None:
        order[field] = value
        assert client.post("/predict/delay", json=order).status_code == 422

    def test_unknown_seller(self, client, order) -> None:
        order["seller_id"] = "f" * 32
        response = client.post("/predict/delay", json=order)
        assert response.status_code == 404


class TestSentimentEndpoint:
    def test_negative_review(self, client) -> None:
        response = client.post("/predict/sentiment",
                               json={"text": "Não recebi, produto quebrado"})
        assert response.status_code == 200
        assert response.json()["sentiment"] == "négatif"

    def test_blank_review_is_rejected(self, client) -> None:
        response = client.post("/predict/sentiment", json={"text": "   "})
        assert response.status_code == 422


class TestSegmentEndpoint:
    def test_customer_persona(self, client) -> None:
        response = client.post("/predict/segment", json={
            "recency_days": 300, "frequency": 1, "monetary": 120.0,
        })
        assert response.status_code == 200
        assert response.json()["persona"] in {
            PERSONA_LOYAL, PERSONA_NEW, PERSONA_DORMANT, PERSONA_LOST,
        }

    def test_impossible_values_are_rejected(self, client) -> None:
        response = client.post("/predict/segment", json={
            "recency_days": -1, "frequency": 0, "monetary": 0,
        })
        assert response.status_code == 422


class TestMissingModels:
    def test_service_starts_and_answers_503(self, tmp_path, order) -> None:
        client = TestClient(create_app(tmp_path))
        health = client.get("/health").json()
        assert health["status"] == "dégradé"
        assert not any(health["models"].values())
        assert client.post("/predict/delay", json=order).status_code == 503
