"""Contrôles qualité des données, mesurés avant (RAW) et après (CORE)."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from shoppulse.database import Database
from shoppulse.loader import RAW_TO_CORE_TABLE

BRAZIL_BOX_RAW = (
    "geolocation_lat::FLOAT NOT BETWEEN -33.8 AND 5.3 "
    "OR geolocation_lng::FLOAT NOT BETWEEN -74.0 AND -34.8"
)
BRAZIL_BOX_CORE = (
    "lat NOT BETWEEN -33.8 AND 5.3 OR lng NOT BETWEEN -74.0 AND -34.8"
)


@dataclass(frozen=True)
class QualityCheck:
    """Un contrôle : deux requêtes qui comptent les lignes en anomalie.

    Un contrôle bloquant fait échouer le pipeline si CORE n'est pas à 0.
    """

    name: str
    description: str
    raw_sql: str
    core_sql: str
    blocking: bool = False


@dataclass
class CheckResult:
    """Résultat d'un contrôle sur les deux couches."""

    check: QualityCheck
    raw_count: int
    core_count: int

    @property
    def failed(self) -> bool:
        return self.check.blocking and self.core_count > 0


QUALITY_CHECKS = [
    QualityCheck(
        "doublons_commandes",
        "Identifiants de commande en double",
        "SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM raw.orders",
        "SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM core.orders",
        blocking=True,
    ),
    QualityCheck(
        "doublons_avis",
        "Avis en double sur le couple (review_id, order_id)",
        "SELECT COUNT(*) - COUNT(DISTINCT (review_id, order_id)) "
        "FROM raw.order_reviews",
        "SELECT COUNT(*) - COUNT(DISTINCT (review_id, order_id)) "
        "FROM core.order_reviews",
        blocking=True,
    ),
    QualityCheck(
        "doublons_geolocalisation",
        "Plusieurs points GPS pour un même code postal (R1)",
        "SELECT COUNT(*) - COUNT(DISTINCT geolocation_zip_code_prefix) "
        "FROM raw.geolocation",
        "SELECT COUNT(*) - COUNT(DISTINCT zip_code_prefix) "
        "FROM core.geolocation",
        blocking=True,
    ),
    QualityCheck(
        "geolocalisation_hors_bresil",
        "Points GPS situés hors du Brésil (R1)",
        f"SELECT COUNT(*) FROM raw.geolocation WHERE {BRAZIL_BOX_RAW}",
        f"SELECT COUNT(*) FROM core.geolocation WHERE {BRAZIL_BOX_CORE}",
        blocking=True,
    ),
    QualityCheck(
        "categories_sans_traduction",
        "Produits dont la catégorie n'a pas de traduction (R2)",
        "SELECT COUNT(*) FROM raw.products p "
        "LEFT JOIN raw.category_translation t "
        "USING (product_category_name) "
        "WHERE p.product_category_name IS NOT NULL "
        "AND t.product_category_name IS NULL",
        "SELECT COUNT(*) FROM core.products p "
        "LEFT JOIN core.categories c USING (category_name) "
        "WHERE p.category_name IS NOT NULL AND c.category_name IS NULL",
        blocking=True,
    ),
    QualityCheck(
        "commentaires_vides",
        "Commentaires d'avis composés uniquement d'espaces (R4)",
        "SELECT COUNT(*) FROM raw.order_reviews "
        "WHERE TRIM(review_comment_message) = ''",
        "SELECT COUNT(*) FROM core.order_reviews "
        "WHERE TRIM(comment_message) = ''",
        blocking=True,
    ),
    QualityCheck(
        "produits_sans_categorie",
        "Produits sans catégorie (conservés, signalés)",
        "SELECT COUNT(*) FROM raw.products "
        "WHERE product_category_name IS NULL",
        "SELECT COUNT(*) FROM core.products WHERE category_name IS NULL",
    ),
    QualityCheck(
        "produits_sans_poids",
        "Produits sans poids ou de poids nul (conservés, signalés)",
        "SELECT COUNT(*) FROM raw.products "
        "WHERE COALESCE(product_weight_g::NUMERIC, 0) = 0",
        "SELECT COUNT(*) FROM core.products "
        "WHERE COALESCE(weight_g, 0) = 0",
    ),
    QualityCheck(
        "livrees_sans_date",
        "Commandes 'delivered' sans date de livraison client",
        "SELECT COUNT(*) FROM raw.orders WHERE order_status = 'delivered' "
        "AND order_delivered_customer_date IS NULL",
        "SELECT COUNT(*) FROM core.orders WHERE status = 'delivered' "
        "AND delivered_customer_date IS NULL",
    ),
    QualityCheck(
        "transporteur_avant_achat",
        "Remise au transporteur datée avant l'achat",
        "SELECT COUNT(*) FROM raw.orders WHERE "
        "order_delivered_carrier_date::TIMESTAMP "
        "< order_purchase_timestamp::TIMESTAMP",
        "SELECT COUNT(*) FROM core.orders "
        "WHERE delivered_carrier_date < purchase_timestamp",
    ),
    QualityCheck(
        "commandes_sans_articles",
        "Commandes sans aucun article",
        "SELECT COUNT(*) FROM raw.orders o WHERE NOT EXISTS "
        "(SELECT 1 FROM raw.order_items i WHERE i.order_id = o.order_id)",
        "SELECT COUNT(*) FROM core.orders o WHERE NOT EXISTS "
        "(SELECT 1 FROM core.order_items i WHERE i.order_id = o.order_id)",
    ),
    QualityCheck(
        "paiements_non_definis",
        "Paiements de type 'not_defined'",
        "SELECT COUNT(*) FROM raw.order_payments "
        "WHERE payment_type = 'not_defined'",
        "SELECT COUNT(*) FROM core.order_payments "
        "WHERE payment_type = 'not_defined'",
    ),
    QualityCheck(
        "codes_postaux_clients_inconnus",
        "Clients dont le code postal est absent de la géolocalisation",
        "SELECT COUNT(*) FROM raw.customers c WHERE NOT EXISTS "
        "(SELECT 1 FROM raw.geolocation g WHERE "
        "g.geolocation_zip_code_prefix = c.customer_zip_code_prefix)",
        "SELECT COUNT(*) FROM core.customers c LEFT JOIN core.geolocation g "
        "USING (zip_code_prefix) WHERE g.zip_code_prefix IS NULL",
    ),
]


class QualityChecker:
    """Exécute les contrôles et produit le rapport avant/après."""

    def __init__(self, database: Database,
                 checks: list[QualityCheck] | None = None) -> None:
        self.database = database
        self.checks = checks or QUALITY_CHECKS

    def count(self, sql: str) -> int:
        return self.database.connection.execute(sql).fetchone()[0]

    def run(self) -> list[CheckResult]:
        """Mesure chaque contrôle sur RAW puis sur CORE."""
        return [
            CheckResult(check, self.count(check.raw_sql),
                        self.count(check.core_sql))
            for check in self.checks
        ]

    @staticmethod
    def failures(results: list[CheckResult]) -> list[CheckResult]:
        """Contrôles bloquants encore en anomalie dans CORE."""
        return [result for result in results if result.failed]


class QualityReport:
    """Rapport qualité au format Markdown, régénéré à chaque exécution."""

    def __init__(self, results: list[CheckResult],
                 volumes: dict[str, dict[str, int]]) -> None:
        self.results = results
        self.volumes = volumes

    def to_markdown(self) -> str:
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [
            "# Rapport qualité des données",
            "",
            (
                f"Généré automatiquement par le pipeline le {generated_at}. "
                "Ne pas modifier à la main."
            ),
            "",
            "## Volumes par table",
            "",
            "| Table | Avant (RAW) | Après (CORE) |",
            "|---|---:|---:|",
        ]
        for raw_table, raw_count in self.volumes["raw"].items():
            core_table = RAW_TO_CORE_TABLE[raw_table]
            core_count = self.volumes["core"][core_table]
            lines.append(
                f"| {raw_table} → {core_table} "
                f"| {self.number(raw_count)} | {self.number(core_count)} |"
            )
        lines += [
            "",
            "## Contrôles",
            "",
            (
                "Nombre de lignes en anomalie. Un contrôle **bloquant** fait "
                "échouer le pipeline s'il n'est pas à 0 après nettoyage."
            ),
            "",
            "| Contrôle | Description | Avant | Après | Statut |",
            "|---|---|---:|---:|---|",
        ]
        for result in self.results:
            lines.append(
                f"| `{result.check.name}` | {result.check.description} "
                f"| {self.number(result.raw_count)} "
                f"| {self.number(result.core_count)} "
                f"| {self.status(result)} |"
            )
        return "\n".join(lines) + "\n"

    @staticmethod
    def number(value: int) -> str:
        """Nombre au format français (espace comme séparateur de milliers)."""
        return f"{value:,}".replace(",", " ")

    @staticmethod
    def status(result: CheckResult) -> str:
        if result.failed:
            return "ÉCHEC"
        if result.check.blocking:
            return "OK (bloquant)"
        return "signalé"

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_markdown(), encoding="utf-8")
