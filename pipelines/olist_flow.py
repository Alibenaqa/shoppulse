"""Pipeline ETL Olist orchestré avec Prefect.

Usage : python pipelines/olist_flow.py

Étapes : vérification des sources -> chargement RAW -> transformation CORE
-> contrôles qualité avant/après -> rapport -> analyses SQL -> segmentation
des clients (table mart.customer_segments). Chaque étape tourne dans sa
propre transaction et est idempotente : relancer le flux donne le même
résultat. Les tâches Prefect sont des fonctions (imposé par le framework) qui
délèguent tout le travail aux classes du package shoppulse.
"""

import pandas as pd
from prefect import flow, get_run_logger, task

from shoppulse.analysis import SqlAnalysisReport
from shoppulse.config import PROJECT_ROOT
from shoppulse.database import Database
from shoppulse.loader import OlistLoader
from shoppulse.quality import CheckResult, QualityChecker, QualityReport
from shoppulse.segmentation import SegmentationJob

QUALITY_REPORT_PATH = PROJECT_ROOT / "docs" / "quality_report.md"
SQL_ANALYSIS_PATH = PROJECT_ROOT / "docs" / "sql_analysis.md"
TASK_RETRIES = 2


@task(name="verifier_sources")
def check_sources() -> None:
    with Database() as database:
        loader = OlistLoader(database)
        loader.check_files()
        loader.create_schemas()
        loader.check_headers()


@task(name="charger_raw", retries=TASK_RETRIES)
def load_raw() -> dict[str, int]:
    with Database() as database:
        return OlistLoader(database).load_raw()


@task(name="transformer_core", retries=TASK_RETRIES)
def transform_core() -> dict[str, int]:
    with Database() as database:
        return OlistLoader(database).transform_core()


@task(name="controler_qualite")
def check_quality() -> list[CheckResult]:
    with Database() as database:
        return QualityChecker(database).run()


@task(name="ecrire_rapport")
def write_report(results: list[CheckResult],
                 volumes: dict[str, dict[str, int]]) -> None:
    QualityReport(results, volumes).write(QUALITY_REPORT_PATH)


@task(name="analyser_sql")
def run_sql_analysis() -> None:
    with Database() as database:
        SqlAnalysisReport(database).write(SQL_ANALYSIS_PATH)


@task(name="segmenter_clients")
def segment_customers() -> pd.DataFrame:
    return SegmentationJob().run()


@flow(name="olist_etl", log_prints=True)
def olist_etl() -> None:
    logger = get_run_logger()
    check_sources()
    volumes = {"raw": load_raw(), "core": transform_core()}
    results = check_quality()
    write_report(results, volumes)
    logger.info("Rapport qualité écrit dans %s", QUALITY_REPORT_PATH)
    failures = QualityChecker.failures(results)
    if failures:
        names = ", ".join(result.check.name for result in failures)
        raise RuntimeError(f"Contrôles qualité bloquants en échec : {names}")
    run_sql_analysis()
    logger.info("Analyses SQL écrites dans %s", SQL_ANALYSIS_PATH)
    personas = segment_customers()
    logger.info("Segmentation enregistrée :\n%s", personas.round(1))


if __name__ == "__main__":
    olist_etl()
