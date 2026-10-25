"""Lance le chargement complet des CSV Olist dans PostgreSQL.

Usage : python pipelines/load_olist.py
(l'orchestration Prefect viendra envelopper ce chargement).
"""

from shoppulse.database import Database
from shoppulse.loader import OlistLoader


class LoadOlistJob:
    """Point d'entrée en ligne de commande du chargement."""

    def __init__(self) -> None:
        self.database = Database()

    def run(self) -> None:
        with self.database as database:
            volumes = OlistLoader(database).run()
        for layer, counts in volumes.items():
            print(f"[{layer}]")
            for table, count in counts.items():
                print(f"  {table:<28} {count:>9,}")


if __name__ == "__main__":
    LoadOlistJob().run()
