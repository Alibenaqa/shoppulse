"""Modèle de prédiction du retard de livraison : comparaison et sélection.

Démarche :
1. découpage temporel : on apprend sur le passé, on teste sur le futur ;
2. validation croisée temporelle (TimeSeriesSplit) sur la période
   d'apprentissage pour comparer une baseline et deux algorithmes ;
3. choix du seuil de décision sur les prédictions de validation ;
4. évaluation finale sur la période de test, jamais vue avant ;
5. importance des variables par permutation.

Les classes sont déséquilibrées (environ 7 % de retards) : on suit
l'aire sous la courbe précision-rappel (PR-AUC), le rappel, la précision
et le rappel obtenu en surveillant les 10 % de commandes les plus risquées.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import ClassVar

import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin, clone
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import (
    FunctionTransformer,
    OneHotEncoder,
    StandardScaler,
)
from threadpoolctl import threadpool_limits

from shoppulse.config import MODELS_DIR
from shoppulse.features import (
    CATEGORICAL_FEATURES,
    FEATURES,
    NUMERIC_FEATURES,
    TARGET,
    DelayServingSnapshot,
)
from shoppulse.formatting import NumberFormat

TEST_START = "2018-06-01"
CV_SPLITS = 5
TOP_SHARE = 0.10
RANDOM_STATE = 42
IMPORTANCE_REPEATS = 5
MODEL_PATH = MODELS_DIR / "delay_model.joblib"
SNAPSHOT_PATH = MODELS_DIR / "delay_snapshot.joblib"
LOG_FEATURES = [
    "distance_km", "n_items", "total_weight_g", "order_value",
    "freight_value", "seller_past_orders", "seller_dispatch_days",
]
LINEAR_FEATURES = [
    column for column in NUMERIC_FEATURES if column not in LOG_FEATURES
]

PREDICTION_COLUMNS = ["order_id", "purchase_timestamp", "customer_region",
                      TARGET]

BASELINE = "baseline_taux_moyen"
STATE_RULE = "regle_taux_par_etat"
LOGISTIC = "regression_logistique"
BOOSTING = "gradient_boosting"


class StateRateBaseline(ClassifierMixin, BaseEstimator):
    """Règle métier simple : le risque d'une commande est le taux de
    retard historique de l'état du client (ce qu'un logisticien ferait
    « à la main »)."""

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "StateRateBaseline":
        target = pd.Series(np.asarray(y), index=X.index)
        self.global_rate_ = float(target.mean())
        self.rates_ = target.groupby(
            X["customer_state"].astype(str)
        ).mean().to_dict()
        self.classes_ = np.array([0, 1])
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        late = X["customer_state"].astype(str).map(self.rates_).fillna(
            self.global_rate_
        ).to_numpy(dtype=float)
        return np.column_stack([1 - late, late])

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)


class DelayModelFactory:
    """Les modèles comparés, tous sous forme de pipelines scikit-learn."""

    @staticmethod
    def candidates() -> dict[str, BaseEstimator]:
        return {
            BASELINE: DummyClassifier(strategy="prior"),
            STATE_RULE: StateRateBaseline(),
            LOGISTIC: DelayModelFactory.logistic(),
            BOOSTING: DelayModelFactory.boosting(),
        }

    @staticmethod
    def logistic() -> Pipeline:
        """Régression logistique : variables asymétriques passées au log,
        standardisées, état du client encodé en one-hot."""
        preprocessing = ColumnTransformer([
            ("log", Pipeline([
                ("impute", SimpleImputer(strategy="median")),
                ("log", FunctionTransformer(np.log1p)),
                ("scale", StandardScaler()),
            ]), LOG_FEATURES),
            ("linear", Pipeline([
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
            ]), LINEAR_FEATURES),
            ("state", OneHotEncoder(handle_unknown="ignore"),
             CATEGORICAL_FEATURES),
        ])
        return Pipeline([
            ("preprocessing", preprocessing),
            ("model", LogisticRegression(class_weight="balanced",
                                         max_iter=2000)),
        ])

    @staticmethod
    def boosting(regularized: bool = True) -> HistGradientBoostingClassifier:
        """Gradient boosting d'arbres : gère seul les valeurs manquantes,
        les non-linéarités et la variable catégorielle (état).

        La version régularisée (arbres plus petits, feuilles plus peuplées,
        pénalité L2 plus forte) a été retenue en validation croisée contre
        la configuration standard : les données changent avec le temps, un
        modèle trop flexible apprend des règles qui ne durent pas.
        """
        params = {
            "learning_rate": 0.05,
            "max_iter": 300,
            "max_leaf_nodes": 31,
            "min_samples_leaf": 100,
            "l2_regularization": 1.0,
        }
        if regularized:
            params.update(max_iter=200, max_leaf_nodes=15,
                          min_samples_leaf=400, l2_regularization=10.0)
        return HistGradientBoostingClassifier(
            **params,
            class_weight="balanced",
            categorical_features="from_dtype",
            random_state=RANDOM_STATE,
        )


class DelayMetrics:
    """Métriques adaptées à des classes déséquilibrées."""

    @staticmethod
    def top_share(proba: np.ndarray) -> np.ndarray:
        """Indices des 10 % de commandes les plus risquées. Les ex aequo
        sont départagés au hasard (sinon un modèle constant « choisirait »
        les premières commandes de la période)."""
        shuffled = np.random.default_rng(RANDOM_STATE).permutation(
            len(proba)
        )
        ranked = shuffled[np.argsort(-proba[shuffled], kind="stable")]
        return ranked[: max(1, int(len(proba) * TOP_SHARE))]

    @staticmethod
    def ranking(y_true: np.ndarray, proba: np.ndarray) -> dict[str, float]:
        """Métriques indépendantes du seuil de décision."""
        top = DelayMetrics.top_share(proba)
        caught = y_true[top].sum()
        return {
            "pr_auc": average_precision_score(y_true, proba),
            "roc_auc": roc_auc_score(y_true, proba),
            "recall_top10": caught / max(1, y_true.sum()),
            "precision_top10": caught / len(top),
        }

    @staticmethod
    def at_threshold(y_true: np.ndarray, proba: np.ndarray,
                     threshold: float) -> dict[str, float]:
        """Métriques de classement une fois le seuil choisi."""
        predicted = (proba >= threshold).astype(int)
        return {
            "precision": precision_score(y_true, predicted, zero_division=0),
            "recall": recall_score(y_true, predicted),
            "f1": f1_score(y_true, predicted),
            "balanced_accuracy": balanced_accuracy_score(y_true, predicted),
            "flagged_share": predicted.mean(),
        }

    @staticmethod
    def best_f1_threshold(y_true: np.ndarray, proba: np.ndarray) -> float:
        precision, recall, thresholds = precision_recall_curve(y_true, proba)
        f1 = 2 * precision * recall / np.maximum(precision + recall, 1e-12)
        return float(thresholds[np.argmax(f1[:-1])])


@dataclass
class DelayModelResults:
    """Tout ce qu'il faut pour le rapport et le notebook."""

    cv_scores: pd.DataFrame
    test_scores: pd.DataFrame
    best_model: str
    threshold: float
    importance: pd.DataFrame
    test_predictions: pd.DataFrame
    validation_predictions: pd.DataFrame
    sizes: dict[str, float] = field(default_factory=dict)


class DelayModelTrainer:
    """Compare les modèles, choisit le meilleur et l'entraîne.

    Les entraînements tournent sur un seul thread : le gradient boosting
    fait des sommes en parallèle dont l'ordre varie d'une exécution à
    l'autre, ce qui change légèrement les résultats. Un seul thread rend
    le pipeline exactement rejouable.
    """

    def __init__(self, frame: pd.DataFrame, test_start: str = TEST_START,
                 features: list[str] | None = None) -> None:
        self.features = features or FEATURES
        self.frame = frame.sort_values(["purchase_timestamp", "order_id"])
        is_test = self.frame["purchase_timestamp"] >= test_start
        self.train = self.frame[~is_test].reset_index(drop=True)
        self.test = self.frame[is_test].reset_index(drop=True)
        self.candidates = DelayModelFactory.candidates()
        self.oof_predictions: dict[str, np.ndarray] = {}

    @staticmethod
    def fit(model: BaseEstimator, X: pd.DataFrame,
            y: pd.Series | np.ndarray) -> BaseEstimator:
        """Entraîne une copie du modèle, sur un seul thread."""
        with threadpool_limits(limits=1, user_api="openmp"):
            return clone(model).fit(X, y)

    def sizes(self) -> dict[str, float]:
        return {
            "train_orders": len(self.train),
            "train_late_rate": self.train[TARGET].mean(),
            "test_orders": len(self.test),
            "test_late_rate": self.test[TARGET].mean(),
        }

    def cross_validate(self) -> pd.DataFrame:
        """Validation croisée temporelle : chaque pli apprend sur le passé
        et valide sur la période qui suit."""
        X, y = self.train[self.features], self.train[TARGET].to_numpy()
        splitter = TimeSeriesSplit(n_splits=CV_SPLITS)
        rows = []
        for name, model in self.candidates.items():
            oof = np.full(len(y), np.nan)
            for fold, (fit_idx, val_idx) in enumerate(splitter.split(X)):
                fitted = self.fit(model, X.iloc[fit_idx], y[fit_idx])
                proba = fitted.predict_proba(X.iloc[val_idx])[:, 1]
                oof[val_idx] = proba
                rows.append({"model": name, "fold": fold + 1,
                             **DelayMetrics.ranking(y[val_idx], proba)})
            self.oof_predictions[name] = oof
        return pd.DataFrame(rows)

    @staticmethod
    def summarize(cv_scores: pd.DataFrame) -> pd.DataFrame:
        """Moyenne et écart-type des métriques sur les plis."""
        summary = cv_scores.drop(columns="fold").groupby("model").agg(
            ["mean", "std"]
        )
        return summary.sort_values(("pr_auc", "mean"), ascending=False)

    def choose_threshold(self, name: str) -> float:
        """Seuil qui maximise le F1 sur les prédictions de validation."""
        oof = self.oof_predictions[name]
        mask = ~np.isnan(oof)
        return DelayMetrics.best_f1_threshold(
            self.train[TARGET].to_numpy()[mask], oof[mask]
        )

    def evaluate_on_test(self, threshold: float,
                         best_model: str) -> tuple[pd.DataFrame,
                                                   pd.DataFrame]:
        """Réentraîne chaque modèle sur toute la période d'apprentissage et
        le mesure sur la période de test."""
        X_train, y_train = self.train[self.features], self.train[TARGET]
        y_test = self.test[TARGET].to_numpy()
        rows = []
        predictions = self.test[PREDICTION_COLUMNS].copy()
        for name, model in self.candidates.items():
            fitted = self.fit(model, X_train, y_train)
            proba = fitted.predict_proba(self.test[self.features])[:, 1]
            predictions[f"proba_{name}"] = proba
            row = {"model": name, **DelayMetrics.ranking(y_test, proba)}
            if name == best_model:
                row.update(DelayMetrics.at_threshold(y_test, proba,
                                                     threshold))
                self.fitted_best = fitted
            rows.append(row)
        scores = pd.DataFrame(rows).set_index("model")
        return scores.sort_values("pr_auc", ascending=False), predictions

    def importance(self) -> pd.DataFrame:
        """Importance par permutation sur le test (baisse de PR-AUC quand
        on mélange une variable)."""
        result = permutation_importance(
            self.fitted_best, self.test[self.features], self.test[TARGET],
            scoring="average_precision", n_repeats=IMPORTANCE_REPEATS,
            random_state=RANDOM_STATE,
        )
        return pd.DataFrame({
            "feature": self.features,
            "importance_mean": result.importances_mean,
            "importance_std": result.importances_std,
        }).sort_values("importance_mean", ascending=False)

    def run(self) -> DelayModelResults:
        cv_scores = self.cross_validate()
        summary = self.summarize(cv_scores)
        best_model = summary.index[0]
        threshold = self.choose_threshold(best_model)
        test_scores, predictions = self.evaluate_on_test(threshold,
                                                         best_model)
        return DelayModelResults(
            cv_scores=cv_scores,
            test_scores=test_scores,
            best_model=best_model,
            threshold=threshold,
            importance=self.importance(),
            test_predictions=predictions,
            validation_predictions=self.validation_predictions(best_model),
            sizes=self.sizes(),
        )

    def validation_predictions(self, name: str) -> pd.DataFrame:
        """Prédictions de validation croisée (commandes des plis de
        validation), utiles pour l'audit d'équité."""
        oof = self.oof_predictions[name]
        mask = ~np.isnan(oof)
        predictions = self.train.loc[mask, PREDICTION_COLUMNS].copy()
        predictions[f"proba_{name}"] = oof[mask]
        return predictions.reset_index(drop=True)

    def fit_final(self, best_model: str) -> BaseEstimator:
        """Modèle de production : réentraîné sur toutes les données."""
        return self.fit(self.candidates[best_model],
                        self.frame[self.features], self.frame[TARGET])


class DelayModelReport:
    """Rapport Markdown du modèle de retard, régénéré à chaque entraînement.
    """

    METRIC_LABELS: ClassVar[dict[str, str]] = {
        "pr_auc": "PR-AUC",
        "roc_auc": "ROC-AUC",
        "recall_top10": "Rappel top 10 %",
        "precision_top10": "Précision top 10 %",
        "precision": "Précision",
        "recall": "Rappel",
        "f1": "F1",
        "balanced_accuracy": "Exactitude équilibrée",
        "flagged_share": "Part signalée",
    }

    def __init__(self, results: DelayModelResults) -> None:
        self.results = results

    def to_markdown(self) -> str:
        sizes = self.results.sizes
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [
            "# Modèle de retard de livraison",
            "",
            (
                f"Généré automatiquement par le pipeline d'entraînement le "
                f"{generated_at}. Ne pas modifier à la main."
            ),
            "",
            "## Données",
            "",
            (
                "- Apprentissage (janv. 2017 → mai 2018) : "
                f"{NumberFormat.thousands(sizes['train_orders'])} commandes, "
                f"{NumberFormat.percent(sizes['train_late_rate'])} de retards"
            ),
            (
                "- Test (juin → août 2018) : "
                f"{NumberFormat.thousands(sizes['test_orders'])} commandes, "
                f"{NumberFormat.percent(sizes['test_late_rate'])} de retards"
            ),
            "",
            f"## Validation croisée temporelle ({CV_SPLITS} plis)",
            "",
            (
                "Moyenne ± écart-type sur les plis. Modèle retenu : le "
                "meilleur PR-AUC moyen."
            ),
            "",
        ]
        lines += self.cv_table()
        lines += [
            "",
            "## Test (période jamais vue)",
            "",
            (
                f"Modèle retenu : **{self.results.best_model}**, seuil de "
                f"décision {self.results.threshold:.3f} (F1 maximal en "
                "validation)."
            ),
            "",
        ]
        lines += self.table(self.results.test_scores)
        lines += [
            "",
            "## Importance des variables (permutation sur le test)",
            "",
            (
                "Baisse de PR-AUC quand on mélange la variable. Une valeur "
                "négative signifie que la relation apprise ne tient plus "
                "sur la période de test."
            ),
            "",
            "| Variable | Importance | Écart-type |",
            "|---|---:|---:|",
        ]
        for row in self.results.importance.itertuples():
            lines.append(
                f"| `{row.feature}` | {row.importance_mean:.4f} "
                f"| {row.importance_std:.4f} |"
            )
        return "\n".join(lines) + "\n"

    def cv_table(self) -> list[str]:
        summary = DelayModelTrainer.summarize(self.results.cv_scores)
        metrics = list(dict.fromkeys(summary.columns.get_level_values(0)))
        lines = [
            "| Modèle | " + " | ".join(
                self.METRIC_LABELS[metric] for metric in metrics
            ) + " |",
            "|---|" + "---:|" * len(metrics),
        ]
        for model, row in summary.iterrows():
            cells = [
                f"{row[(metric, 'mean')]:.3f} ± {row[(metric, 'std')]:.3f}"
                for metric in metrics
            ]
            lines.append(f"| {model} | " + " | ".join(cells) + " |")
        return lines

    def table(self, scores: pd.DataFrame) -> list[str]:
        metrics = list(scores.columns)
        lines = [
            "| Modèle | " + " | ".join(
                self.METRIC_LABELS[metric] for metric in metrics
            ) + " |",
            "|---|" + "---:|" * len(metrics),
        ]
        for model, row in scores.iterrows():
            cells = [
                "" if pd.isna(row[metric]) else f"{row[metric]:.3f}"
                for metric in metrics
            ]
            lines.append(f"| {model} | " + " | ".join(cells) + " |")
        return lines

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_markdown(), encoding="utf-8")


class DelayModelStore:
    """Sauvegarde et chargement du modèle avec ses métadonnées."""

    @staticmethod
    def save(model: BaseEstimator, results: DelayModelResults,
             path: Path = MODEL_PATH,
             region_thresholds: dict[str, float] | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({
            "model": model,
            "model_name": results.best_model,
            "threshold": results.threshold,
            "region_thresholds": region_thresholds or {},
            "features": FEATURES,
            "test_scores": results.test_scores.loc[
                results.best_model
            ].to_dict(),
            "trained_at": datetime.now().isoformat(timespec="seconds"),
        }, path)

    @staticmethod
    def load(path: Path = MODEL_PATH) -> dict:
        return joblib.load(path)

    @staticmethod
    def save_snapshot(snapshot: DelayServingSnapshot,
                      path: Path = SNAPSHOT_PATH) -> None:
        """Historiques et référentiels dont l'API a besoin."""
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(snapshot, path)

    @staticmethod
    def load_snapshot(path: Path = SNAPSHOT_PATH) -> DelayServingSnapshot:
        return joblib.load(path)
