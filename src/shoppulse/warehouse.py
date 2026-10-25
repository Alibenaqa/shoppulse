"""Lecture et écriture de DataFrames pandas dans PostgreSQL."""

import pandas as pd
import psycopg
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from shoppulse.config import DatabaseSettings


class DataWarehouse:
    """Accès « analyse » à la base : requêtes SQL -> DataFrame et retour.

    Utilisé par les notebooks, la segmentation et le tableau de bord.
    """

    def __init__(self, settings: DatabaseSettings | None = None) -> None:
        self.settings = settings or DatabaseSettings()
        self.engine: Engine = create_engine(
            "postgresql+psycopg://",
            creator=lambda: psycopg.connect(self.settings.conninfo()),
        )

    def query(self, sql: str, params: dict | None = None) -> pd.DataFrame:
        """Exécute une requête SELECT et renvoie un DataFrame."""
        with self.engine.connect() as connection:
            return pd.read_sql(text(sql), connection, params=params)

    def write(self, frame: pd.DataFrame, schema: str, table: str) -> None:
        """Remplace une table par le contenu d'un DataFrame."""
        with self.engine.begin() as connection:
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
            frame.to_sql(table, connection, schema=schema,
                         if_exists="replace", index=False)
