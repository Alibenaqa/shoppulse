# Image de l'API ShopPulse (FastAPI). Construite depuis la racine du dépôt :
#   docker build -f infra/Dockerfile -t shoppulse-api .
# Les modèles ne sont pas dans l'image : ils sont produits par le pipeline
# d'entraînement et montés au lancement (voir infra/docker-compose.yml).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SHOPPULSE_MODELS_DIR=/app/models

WORKDIR /app

COPY infra/constraints-api.txt ./constraints-api.txt
COPY pyproject.toml ./
COPY src ./src
RUN pip install --constraint constraints-api.txt . \
    && useradd --create-home --uid 1000 shoppulse \
    && mkdir -p /app/models && chown shoppulse /app/models

USER shoppulse
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "shoppulse.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
