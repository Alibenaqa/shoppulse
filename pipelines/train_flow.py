"""Pipeline d'entraînement des modèles (retard et sentiment), avec Prefect.

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
from shoppulse.fairness import DelayFairnessAudit, FairnessReport
from shoppulse.features import DelayFeatureBuilder
from shoppulse.sentiment import (
    ReviewDataset,
    SentimentExperiment,
    SentimentReport,
    SentimentResults,
)

DELAY_REPORT_PATH = PROJECT_ROOT / "docs" / "delay_model_report.md"
FAIRNESS_REPORT_PATH = PROJECT_ROOT / "docs" / "fairness_report.md"
SENTIMENT_REPORT_PATH = PROJECT_ROOT / "docs" / "sentiment_report.md"


@task(name="construire_variables_retard", cache_policy=NO_CACHE)
def build_delay_features() -> pd.DataFrame:
    return DelayFeatureBuilder().build()


@task(name="comparer_modeles_retard", cache_policy=NO_CACHE)
def compare_delay_models(frame: pd.DataFrame) -> DelayModelResults:
    return DelayModelTrainer(frame).run()


@task(name="auditer_equite_retard", cache_policy=NO_CACHE)
def audit_delay_fairness(results: DelayModelResults) -> dict[str, float]:
    audit = DelayFairnessAudit(results)
    FairnessReport(audit.audits()).write(FAIRNESS_REPORT_PATH)
    return audit.region_thresholds.thresholds


@task(name="entrainer_modele_retard", cache_policy=NO_CACHE)
def train_final_delay_model(frame: pd.DataFrame, results: DelayModelResults,
                            region_thresholds: dict[str, float]) -> None:
    model = DelayModelTrainer(frame).fit_final(results.best_model)
    DelayModelStore.save(model, results, MODEL_PATH, region_thresholds)


@task(name="ecrire_rapport_retard", cache_policy=NO_CACHE)
def write_delay_report(results: DelayModelResults) -> None:
    DelayModelReport(results).write(DELAY_REPORT_PATH)


@task(name="construire_jeu_avis", cache_policy=NO_CACHE)
def build_review_dataset() -> pd.DataFrame:
    return ReviewDataset().load()


@task(name="entrainer_modeles_sentiment", cache_policy=NO_CACHE)
def train_sentiment_models(reviews: pd.DataFrame) -> SentimentResults:
    experiment = SentimentExperiment(reviews)
    results = experiment.run()
    experiment.save_best(results)
    return results


@task(name="ecrire_rapport_sentiment", cache_policy=NO_CACHE)
def write_sentiment_report(results: SentimentResults) -> None:
    SentimentReport(results).write(SENTIMENT_REPORT_PATH)


@flow(name="ml_training", log_prints=True)
def ml_training() -> None:
    logger = get_run_logger()
    frame = build_delay_features()
    results = compare_delay_models(frame)
    logger.info("Modèle de retard retenu : %s (seuil %.3f)",
                results.best_model, results.threshold)
    region_thresholds = audit_delay_fairness(results)
    train_final_delay_model(frame, results, region_thresholds)
    write_delay_report(results)
    logger.info("Modèle enregistré dans %s, rapports dans %s et %s",
                MODEL_PATH, DELAY_REPORT_PATH, FAIRNESS_REPORT_PATH)
    sentiment = train_sentiment_models(build_review_dataset())
    write_sentiment_report(sentiment)
    logger.info("Modèle de sentiment retenu : %s, rapport dans %s",
                sentiment.best_model, SENTIMENT_REPORT_PATH)


if __name__ == "__main__":
    ml_training()
