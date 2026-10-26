"""Pipeline d'entraînement des modèles, orchestré avec Prefect.

Usage : python pipelines/train_flow.py
(à lancer après pipelines/olist_flow.py, qui alimente la base)

Séparé du pipeline ETL : on recharge les données chaque jour, mais on ne
réentraîne un modèle que lorsqu'on le décide (nouvelles données, dérive).
"""

import pandas as pd
from prefect import flow, get_run_logger, task
from prefect.cache_policies import NO_CACHE

from shoppulse.config import PROJECT_ROOT
from shoppulse.delay_model import (
    MODEL_PATH,
    DelayModelReport,
    DelayModelResults,
    DelayModelStore,
    DelayModelTrainer,
)
from shoppulse.features import DelayFeatureBuilder

DELAY_REPORT_PATH = PROJECT_ROOT / "docs" / "delay_model_report.md"


@task(name="construire_variables_retard", cache_policy=NO_CACHE)
def build_delay_features() -> pd.DataFrame:
    return DelayFeatureBuilder().build()


@task(name="comparer_modeles_retard", cache_policy=NO_CACHE)
def compare_delay_models(frame: pd.DataFrame) -> DelayModelResults:
    return DelayModelTrainer(frame).run()


@task(name="entrainer_modele_retard", cache_policy=NO_CACHE)
def train_final_delay_model(frame: pd.DataFrame,
                            results: DelayModelResults) -> None:
    model = DelayModelTrainer(frame).fit_final(results.best_model)
    DelayModelStore.save(model, results, MODEL_PATH)


@task(name="ecrire_rapport_retard", cache_policy=NO_CACHE)
def write_delay_report(results: DelayModelResults) -> None:
    DelayModelReport(results).write(DELAY_REPORT_PATH)


@flow(name="ml_training", log_prints=True)
def ml_training() -> None:
    logger = get_run_logger()
    frame = build_delay_features()
    results = compare_delay_models(frame)
    logger.info("Modèle de retard retenu : %s (seuil %.3f)",
                results.best_model, results.threshold)
    train_final_delay_model(frame, results)
    write_delay_report(results)
    logger.info("Modèle enregistré dans %s, rapport dans %s",
                MODEL_PATH, DELAY_REPORT_PATH)


if __name__ == "__main__":
    ml_training()
