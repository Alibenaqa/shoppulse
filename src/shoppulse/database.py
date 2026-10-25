"""Accès à la base PostgreSQL."""

from pathlib import Path
from typing import Self

import psycopg

from shoppulse.config import DatabaseSettings

COPY_CHUNK_SIZE = 1 << 20


class Database:
    """Connexion PostgreSQL avec quelques opérations utilitaires."""

    def __init__(self, settings: DatabaseSettings | None = None) -> None:
        self.settings = settings or DatabaseSettings()
        self.connection: psycopg.Connection | None = None

    def __enter__(self) -> Self:
        self.connection = psycopg.connect(self.settings.conninfo())
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.connection is None:
            return
        if exc_type is None:
            self.connection.commit()
        else:
            self.connection.rollback()
        self.connection.close()
        self.connection = None

    def execute_file(self, sql_path: Path) -> None:
        """Exécute un fichier SQL complet."""
        self.connection.execute(sql_path.read_text(encoding="utf-8"))

    def copy_csv(self, table: str, csv_path: Path) -> None:
        """Charge un CSV (avec en-tête) dans une table via COPY."""
        query = f"COPY {table} FROM STDIN WITH (FORMAT csv, HEADER true)"
        with (
            self.connection.cursor() as cursor,
            cursor.copy(query) as copy,
            csv_path.open("rb") as csv_file,
        ):
            while chunk := csv_file.read(COPY_CHUNK_SIZE):
                copy.write(chunk)

    def truncate(self, table: str) -> None:
        """Vide une table."""
        self.connection.execute(f"TRUNCATE {table}")

    def columns(self, table: str) -> list[str]:
        """Noms des colonnes d'une table, dans l'ordre de définition."""
        schema, name = table.split(".")
        rows = self.connection.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s "
            "ORDER BY ordinal_position",
            (schema, name),
        ).fetchall()
        return [row[0] for row in rows]

    def count_rows(self, table: str) -> int:
        """Nombre de lignes d'une table."""
        row = self.connection.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()
        return row[0]
