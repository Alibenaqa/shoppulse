"""Requêtes SQL d'analyse métier et rapport de leurs résultats."""

import re
from datetime import datetime
from pathlib import Path

from shoppulse.config import SQL_DIR
from shoppulse.database import Database

QUERIES_DIR = SQL_DIR / "queries"
HEADER_PATTERN = re.compile(r"^-- (\w+) : (.*)$")
CONTINUATION_PREFIX = "--   "


class SqlQuery:
    """Une requête d'analyse lue depuis un fichier .sql documenté.

    L'en-tête du fichier contient des lignes « -- Clé : valeur » (Titre,
    Question, Destinataire, Techniques, Note, Lecture), éventuellement
    prolongées par des lignes commençant par « --   ».
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.sql = path.read_text(encoding="utf-8")
        self.metadata = self.parse_header(self.sql)

    @staticmethod
    def parse_header(sql: str) -> dict[str, str]:
        metadata: dict[str, str] = {}
        key = None
        for line in sql.splitlines():
            match = HEADER_PATTERN.match(line)
            if match:
                key = match.group(1)
                metadata[key] = match.group(2).strip()
            elif key and line.startswith(CONTINUATION_PREFIX):
                metadata[key] += " " + line.removeprefix(
                    CONTINUATION_PREFIX
                ).strip()
            elif not line.startswith("--"):
                break
        return metadata

    @property
    def title(self) -> str:
        return self.metadata.get("Titre", self.path.stem)

    def run(self, database: Database) -> tuple[list[str], list[tuple]]:
        """Exécute la requête et renvoie (colonnes, lignes)."""
        cursor = database.connection.execute(self.sql)
        columns = [column.name for column in cursor.description]
        return columns, cursor.fetchall()


class SqlAnalysisReport:
    """Exécute toutes les requêtes et écrit leurs résultats en Markdown."""

    def __init__(self, database: Database,
                 queries_dir: Path = QUERIES_DIR) -> None:
        self.database = database
        self.queries = [
            SqlQuery(path) for path in sorted(queries_dir.glob("*.sql"))
        ]

    def to_markdown(self) -> str:
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [
            "# Analyses SQL",
            "",
            (
                f"Généré automatiquement par le pipeline le {generated_at} "
                "à partir des fichiers de `sql/queries/`. Ne pas modifier à "
                "la main."
            ),
        ]
        for query in self.queries:
            lines += self.section(query)
        return "\n".join(lines) + "\n"

    def section(self, query: SqlQuery) -> list[str]:
        columns, rows = query.run(self.database)
        lines = ["", f"## {query.title}", ""]
        for key in ("Question", "Destinataire", "Techniques", "Lecture"):
            if key in query.metadata:
                lines.append(f"- **{key}** : {query.metadata[key]}")
        lines += [
            f"- **Fichier** : `sql/queries/{query.path.name}`",
            "",
            "| " + " | ".join(columns) + " |",
            "|" + "---|" * len(columns),
        ]
        for row in rows:
            cells = ["" if value is None else str(value) for value in row]
            lines.append("| " + " | ".join(cells) + " |")
        return lines

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_markdown(), encoding="utf-8")
