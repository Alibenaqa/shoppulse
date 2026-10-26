"""Audit d'équité : le modèle se trompe-t-il davantage selon la région ?

Pour chaque région, on mesure ce que la décision « commande à risque »
(probabilité >= seuil) produit concrètement :
- taux de signalement : part des commandes signalées ;
- rappel (TPR) : part des retards réels que le modèle signale
  (égalité des chances : chaque région doit être aussi bien protégée) ;
- taux de fausses alertes (FPR) : part des commandes à l'heure signalées
  à tort ;
- précision : part de vrais retards parmi les commandes signalées ;
- ROC-AUC : qualité du classement à l'intérieur de la région.

Les régions sont comparées au Sudeste (68 % des commandes). Certaines
régions comptent peu de retards : chaque indicateur est donné avec un
intervalle de confiance à 95 % obtenu par bootstrap.
"""

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from shoppulse.delay_model import DelayModelResults
from shoppulse.features import TARGET

GROUP = "customer_region"
REFERENCE_GROUP = "Sudeste"
ALL_GROUPS = "Toutes"
BOOTSTRAP_SAMPLES = 500
CONFIDENCE = 0.95
RANDOM_STATE = 42
FOUR_FIFTHS = (0.8, 1.25)
MAX_RATE_GAP = 0.10
INTERVAL_METRICS = ["flag_rate", "tpr", "fpr", "roc_auc"]


class GroupMetrics:
    """Indicateurs de décision et de classement d'un groupe."""

    @staticmethod
    def compute(y: np.ndarray, score: np.ndarray,
                threshold: float | np.ndarray) -> dict[str, float]:
        flagged = score >= threshold
        late = y == 1
        both_classes = late.any() and (~late).any()
        return {
            "late_rate": late.mean(),
            "flag_rate": flagged.mean(),
            "tpr": flagged[late].mean() if late.any() else np.nan,
            "fpr": flagged[~late].mean() if (~late).any() else np.nan,
            "precision": late[flagged].mean() if flagged.any() else np.nan,
            "roc_auc": roc_auc_score(y, score) if both_classes else np.nan,
        }


class RegionThresholds:
    """Un seuil par région, choisi sur la validation pour que chaque région
    voie la même part de ses retards détectée (égalité des chances)."""

    def __init__(self, group: str = GROUP) -> None:
        self.group = group
        self.thresholds: dict[str, float] = {}

    def fit(self, predictions: pd.DataFrame, score_column: str,
            recall: float) -> "RegionThresholds":
        """Pour chaque région, le seuil qui signale `recall` de ses
        retards (quantile des scores des commandes en retard)."""
        late = predictions[predictions[TARGET] == 1]
        self.thresholds = {
            name: float(part[score_column].quantile(1 - recall))
            for name, part in late.groupby(self.group)
        }
        return self

    def for_rows(self, predictions: pd.DataFrame,
                 default: float) -> np.ndarray:
        """Seuil applicable à chaque commande (seuil global par défaut)."""
        return (
            predictions[self.group].map(self.thresholds).fillna(default)
            .to_numpy(dtype=float)
        )


class FairnessAuditor:
    """Indicateurs par région, intervalles de confiance et écarts."""

    def __init__(self, predictions: pd.DataFrame, score_column: str,
                 threshold: float,
                 region_thresholds: RegionThresholds | None = None,
                 group: str = GROUP,
                 reference: str = REFERENCE_GROUP) -> None:
        self.predictions = predictions.reset_index(drop=True)
        self.score_column = score_column
        self.group = group
        self.reference = reference
        self.row_thresholds = (
            region_thresholds.for_rows(self.predictions, threshold)
            if region_thresholds else
            np.full(len(self.predictions), threshold)
        )

    def groups(self) -> dict[str, np.ndarray]:
        """Indices des commandes de chaque région, plus l'ensemble."""
        groups = {
            name: part.index.to_numpy()
            for name, part in self.predictions.groupby(self.group)
        }
        groups[ALL_GROUPS] = self.predictions.index.to_numpy()
        return groups

    def arrays(self, index: np.ndarray) -> tuple[np.ndarray, ...]:
        return (self.predictions[TARGET].to_numpy()[index],
                self.predictions[self.score_column].to_numpy()[index],
                self.row_thresholds[index])

    def metrics(self) -> pd.DataFrame:
        """Indicateurs de chaque région (et de l'ensemble)."""
        rows = []
        for name, index in self.groups().items():
            y, score, threshold = self.arrays(index)
            rows.append({
                self.group: name,
                "orders": len(index),
                "late_orders": int(y.sum()),
                **GroupMetrics.compute(y, score, threshold),
            })
        return pd.DataFrame(rows).set_index(self.group)

    def intervals(self) -> pd.DataFrame:
        """Intervalles de confiance à 95 % par bootstrap (on retire les
        commandes de la région au hasard, avec remise, 500 fois)."""
        rng = np.random.default_rng(RANDOM_STATE)
        alpha = (1 - CONFIDENCE) / 2
        rows = []
        for name, index in self.groups().items():
            y, score, threshold = self.arrays(index)
            samples = []
            for _ in range(BOOTSTRAP_SAMPLES):
                draw = rng.integers(0, len(y), len(y))
                samples.append(GroupMetrics.compute(
                    y[draw], score[draw], threshold[draw]
                ))
            samples = pd.DataFrame(samples)[INTERVAL_METRICS]
            row = {self.group: name}
            for metric in INTERVAL_METRICS:
                row[f"{metric}_low"] = samples[metric].quantile(alpha)
                row[f"{metric}_high"] = samples[metric].quantile(1 - alpha)
            rows.append(row)
        return pd.DataFrame(rows).set_index(self.group)

    def disparities(self) -> pd.DataFrame:
        """Écarts avec la région de référence.

        - ratio de signalement : règle des 4/5, acceptable entre 0,8 et
          1,25 ;
        - écarts de rappel et de fausses alertes : jugés importants
          au-delà de 10 points.
        """
        metrics = self.metrics().drop(index=ALL_GROUPS)
        reference = metrics.loc[self.reference]
        table = pd.DataFrame(index=metrics.index)
        table["flag_ratio"] = metrics["flag_rate"] / reference["flag_rate"]
        table["tpr_gap"] = metrics["tpr"] - reference["tpr"]
        table["fpr_gap"] = metrics["fpr"] - reference["fpr"]
        table["precision_gap"] = (
            metrics["precision"] - reference["precision"]
        )
        low, high = FOUR_FIFTHS
        table["flag_ratio_ok"] = table["flag_ratio"].between(low, high)
        table["tpr_gap_ok"] = table["tpr_gap"].abs() <= MAX_RATE_GAP
        table["fpr_gap_ok"] = table["fpr_gap"].abs() <= MAX_RATE_GAP
        return table


class DelayFairnessAudit:
    """Les trois audits du modèle de retard retenu : validation et test
    avec le seuil unique, puis test avec des seuils par région calibrés
    sur la validation pour atteindre partout le rappel global."""

    def __init__(self, results: DelayModelResults) -> None:
        self.results = results
        self.score_column = f"proba_{results.best_model}"
        validation = results.validation_predictions
        flagged = validation[self.score_column] >= results.threshold
        self.target_recall = float(flagged[validation[TARGET] == 1].mean())
        self.region_thresholds = RegionThresholds().fit(
            validation, self.score_column, self.target_recall
        )

    @staticmethod
    def period(predictions: pd.DataFrame) -> str:
        dates = predictions["purchase_timestamp"]
        return f"{dates.min():%m/%Y} → {dates.max():%m/%Y}"

    def audits(self) -> dict[str, FairnessAuditor]:
        results = self.results
        validation = results.validation_predictions
        test = results.test_predictions
        return {
            f"Validation ({self.period(validation)}), seuil unique":
                FairnessAuditor(validation, self.score_column,
                                results.threshold),
            f"Test ({self.period(test)}), seuil unique":
                FairnessAuditor(test, self.score_column, results.threshold),
            f"Test ({self.period(test)}), seuils par région":
                FairnessAuditor(test, self.score_column, results.threshold,
                                self.region_thresholds),
        }


class FairnessReport:
    """Rapport Markdown de l'audit, régénéré à chaque entraînement."""

    def __init__(self, audits: dict[str, FairnessAuditor]) -> None:
        self.audits = audits

    def to_markdown(self) -> str:
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [
            "# Audit d'équité du modèle de retard par région",
            "",
            (
                f"Généré automatiquement par le pipeline d'entraînement le "
                f"{generated_at}. Ne pas modifier à la main. Analyse et "
                "recommandations : `notebooks/05_audit_equite.ipynb` et "
                "`docs/ethique.md`."
            ),
            "",
            (
                "Indicateurs : taux de retard réel, taux de signalement, "
                "rappel (part des retards signalés), taux de fausses alertes "
                "(part des commandes à l'heure signalées), précision, "
                "ROC-AUC. Entre crochets : intervalle de confiance à 95 % "
                f"(bootstrap, {BOOTSTRAP_SAMPLES} tirages). Référence : "
                f"{REFERENCE_GROUP}. ⚠️ = ratio de signalement hors "
                f"[{FOUR_FIFTHS[0]} ; {FOUR_FIFTHS[1]}] (règle des 4/5) ou "
                f"écart de rappel / fausses alertes > "
                f"{100 * MAX_RATE_GAP:.0f} points."
            ),
        ]
        for title, audit in self.audits.items():
            lines += ["", f"## {title}", ""]
            lines += self.section(audit)
        return "\n".join(lines) + "\n"

    def section(self, audit: FairnessAuditor) -> list[str]:
        metrics = audit.metrics()
        intervals = audit.intervals()
        disparities = audit.disparities()
        lines = [
            (
                "| Région | Commandes | Retards | Taux de retard | Signalées "
                "| Rappel | Fausses alertes | Précision | ROC-AUC "
                "| Ratio de signalement | Alerte |"
            ),
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
        for name, row in metrics.iterrows():
            ci = intervals.loc[name]
            if name in disparities.index:
                gaps = disparities.loc[name]
                ratio = f"{gaps['flag_ratio']:.2f}"
                ok = (gaps["flag_ratio_ok"] and gaps["tpr_gap_ok"]
                      and gaps["fpr_gap_ok"])
                alert = "" if ok else "⚠️"
            else:
                ratio, alert = "", ""
            lines.append(
                f"| {name} | {int(row['orders'])} | {int(row['late_orders'])} "
                f"| {self.pct(row['late_rate'])} "
                f"| {self.with_ci(row, ci, 'flag_rate')} "
                f"| {self.with_ci(row, ci, 'tpr')} "
                f"| {self.with_ci(row, ci, 'fpr')} "
                f"| {self.pct(row['precision'])} "
                f"| {self.with_ci(row, ci, 'roc_auc', percent=False)} "
                f"| {ratio} | {alert} |"
            )
        return lines

    @staticmethod
    def pct(value: float) -> str:
        return "" if pd.isna(value) else f"{100 * value:.1f} %"

    @staticmethod
    def with_ci(row: pd.Series, ci: pd.Series, metric: str,
                percent: bool = True) -> str:
        value = row[metric]
        if pd.isna(value):
            return ""
        low, high = ci[f"{metric}_low"], ci[f"{metric}_high"]
        if percent:
            return (f"{100 * value:.1f} % [{100 * low:.0f}–"
                    f"{100 * high:.0f}]")
        return f"{value:.2f} [{low:.2f}–{high:.2f}]"

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_markdown(), encoding="utf-8")
