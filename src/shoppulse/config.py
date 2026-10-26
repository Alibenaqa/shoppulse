"""Configuration centrale du projet (chemins et connexion PostgreSQL)."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
SQL_DIR = PROJECT_ROOT / "sql"

load_dotenv(PROJECT_ROOT / ".env")

# Dossier des modèles entraînés (surchargé dans l'image Docker).
MODELS_DIR = Path(os.getenv("SHOPPULSE_MODELS_DIR",
                            PROJECT_ROOT / "models"))


class DatabaseSettings:
    """Paramètres de connexion lus depuis les variables d'environnement."""

    def __init__(self) -> None:
        self.host = os.getenv("POSTGRES_HOST", "localhost")
        self.port = int(os.getenv("POSTGRES_PORT", "5432"))
        self.dbname = os.getenv("POSTGRES_DB", "shoppulse")
        self.user = os.getenv("POSTGRES_USER", "shoppulse")
        self.password = os.getenv("POSTGRES_PASSWORD", "")

    def conninfo(self) -> str:
        """Chaîne de connexion au format libpq."""
        return (
            f"host={self.host} port={self.port} dbname={self.dbname} "
            f"user={self.user} password={self.password}"
        )
