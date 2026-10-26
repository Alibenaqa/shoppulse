"""Modèle de sentiment des avis clients (en portugais).

Stratégie de langue : entraînement direct sur le portugais. On dispose de
plus de 37 000 avis étiquetés par leur note ; c'est assez pour apprendre
le vocabulaire des clients (« não recebi », « atrasou », « recomendo »),
sans coût de traduction, sans envoyer de données clients à un service
externe et avec un modèle léger à servir dans l'API.

Cible : un avis est négatif (1) pour une note de 1 ou 2, positif (0) pour
une note de 4 ou 5. Les notes de 3, ambiguës, sont exclues de
l'apprentissage et analysées à part.

Deux modèles comparés sur un découpage temporel (70 % des avis les plus
anciens pour apprendre, 15 % pour régler, 15 % les plus récents pour
tester) :
- baseline : TF-IDF (mots et paires de mots) + régression logistique ;
- réseau de neurones : GRU bidirectionnel (PyTorch) entraîné de zéro.
"""

import copy
import re
import unicodedata
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.feature_extraction.text import TfidfVectorizer
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
from sklearn.pipeline import Pipeline
from torch import nn
from torch.nn.utils.rnn import pack_padded_sequence, pad_sequence

from shoppulse.config import PROJECT_ROOT
from shoppulse.formatting import NumberFormat
from shoppulse.warehouse import DataWarehouse

REVIEWS_SQL = """
SELECT DISTINCT ON (review_id)
    review_id,
    score,
    comment_title,
    comment_message,
    creation_date
FROM core.order_reviews
WHERE comment_message IS NOT NULL
ORDER BY review_id, creation_date
"""
TARGET = "is_negative"
NEGATIVE_MAX_SCORE = 2
POSITIVE_MIN_SCORE = 4
TRAIN_SHARE = 0.70
VALIDATION_SHARE = 0.15
RANDOM_STATE = 42
TOKEN_PATTERN = r"[a-zà-ÿ0-9]+|[!?]"
TFIDF_C_GRID = [0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0]
LEARNING_CURVE_SHARES = [0.1, 0.25, 0.5, 1.0]
MIN_NEURAL_GAIN = 0.01
TOP_TERMS = 15
TFIDF = "tfidf_regression_logistique"
NEURAL = "reseau_gru"
MODELS_DIR = PROJECT_ROOT / "models"
TFIDF_PATH = MODELS_DIR / "sentiment_tfidf.joblib"
NEURAL_PATH = MODELS_DIR / "sentiment_gru.pt"


class TextNormalizer:
    """Nettoyage et découpage en mots des avis."""

    @staticmethod
    def clean(text: str) -> str:
        """Minuscules, accents normalisés (NFC), espaces uniformisés."""
        text = unicodedata.normalize("NFC", text).lower()
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def tokenize(text: str) -> list[str]:
        """Mots (avec accents) et ponctuations expressives (! ?)."""
        return re.findall(TOKEN_PATTERN, TextNormalizer.clean(text))


class ReviewDataset:
    """Avis avec texte, étiquetés par leur note, découpés dans le temps."""

    def __init__(self, warehouse: DataWarehouse | None = None) -> None:
        self.warehouse = warehouse or DataWarehouse()

    def load(self) -> pd.DataFrame:
        frame = self.warehouse.query(REVIEWS_SQL)
        title = frame["comment_title"].fillna("")
        frame["text"] = (title + " " + frame["comment_message"]).map(
            TextNormalizer.clean
        )
        frame[TARGET] = np.where(
            frame["score"] <= NEGATIVE_MAX_SCORE, 1,
            np.where(frame["score"] >= POSITIVE_MIN_SCORE, 0, -1),
        )
        return (
            frame[["review_id", "creation_date", "score", "text", TARGET]]
            .sort_values(["creation_date", "review_id"])
            .reset_index(drop=True)
        )

    @staticmethod
    def split(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
        """Découpage temporel des avis étiquetés + avis neutres à part."""
        labeled = frame[frame[TARGET] >= 0].reset_index(drop=True)
        train_end = int(len(labeled) * TRAIN_SHARE)
        validation_end = int(len(labeled) * (TRAIN_SHARE + VALIDATION_SHARE))
        return {
            "train": labeled.iloc[:train_end].reset_index(drop=True),
            "validation": labeled.iloc[train_end:validation_end]
            .reset_index(drop=True),
            "test": labeled.iloc[validation_end:].reset_index(drop=True),
            "neutral": frame[frame[TARGET] < 0].reset_index(drop=True),
        }


class SentimentMetrics:
    """Métriques pour une classe minoritaire (les avis négatifs)."""

    @staticmethod
    def compute(y: np.ndarray, proba: np.ndarray,
                threshold: float) -> dict[str, float]:
        predicted = (proba >= threshold).astype(int)
        return {
            "pr_auc": average_precision_score(y, proba),
            "roc_auc": roc_auc_score(y, proba),
            "precision_negative": precision_score(y, predicted,
                                                  zero_division=0),
            "recall_negative": recall_score(y, predicted),
            "f1_negative": f1_score(y, predicted),
            "macro_f1": f1_score(y, predicted, average="macro"),
            "balanced_accuracy": balanced_accuracy_score(y, predicted),
        }

    @staticmethod
    def best_f1_threshold(y: np.ndarray, proba: np.ndarray) -> float:
        precision, recall, thresholds = precision_recall_curve(y, proba)
        f1 = 2 * precision * recall / np.maximum(precision + recall, 1e-12)
        return float(thresholds[np.argmax(f1[:-1])])


class TfidfSentimentModel:
    """Baseline : TF-IDF sur les mots et paires de mots + régression
    logistique (classes équilibrées). La force de régularisation C est
    choisie sur la validation."""

    def __init__(self, c: float = 1.0) -> None:
        self.c = c
        self.pipeline = self.build(c)

    @staticmethod
    def build(c: float) -> Pipeline:
        return Pipeline([
            ("tfidf", TfidfVectorizer(
                tokenizer=TextNormalizer.tokenize, token_pattern=None,
                lowercase=False, ngram_range=(1, 2), min_df=2,
                sublinear_tf=True,
            )),
            ("model", LogisticRegression(C=c, class_weight="balanced",
                                         max_iter=3000)),
        ])

    def fit(self, texts: pd.Series, y: np.ndarray) -> "TfidfSentimentModel":
        self.pipeline.fit(texts, y)
        return self

    def tune(self, train: pd.DataFrame,
             validation: pd.DataFrame) -> pd.DataFrame:
        """Essaie plusieurs C et garde le meilleur PR-AUC de validation."""
        rows = []
        for c in TFIDF_C_GRID:
            model = TfidfSentimentModel(c).fit(train["text"], train[TARGET])
            proba = model.predict_proba(validation["text"])
            rows.append({"C": c, "pr_auc": average_precision_score(
                validation[TARGET], proba
            )})
        scores = pd.DataFrame(rows)
        self.c = float(scores.loc[scores["pr_auc"].idxmax(), "C"])
        self.pipeline = self.build(self.c)
        self.fit(train["text"], train[TARGET])
        return scores

    def predict_proba(self, texts: pd.Series) -> np.ndarray:
        return self.pipeline.predict_proba(texts)[:, 1]

    def top_terms(self, count: int = TOP_TERMS) -> pd.DataFrame:
        """Mots qui poussent le plus vers « négatif » et vers « positif »."""
        vocabulary = self.pipeline.named_steps["tfidf"]
        weights = self.pipeline.named_steps["model"].coef_[0]
        terms = pd.Series(weights, index=vocabulary.get_feature_names_out())
        return pd.DataFrame({
            "négatif": terms.nlargest(count).index,
            "poids négatif": terms.nlargest(count).to_numpy(),
            "positif": terms.nsmallest(count).index,
            "poids positif": terms.nsmallest(count).to_numpy(),
        })

    def save(self, path: Path = TFIDF_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"c": self.c, "pipeline": self.pipeline}, path)

    @staticmethod
    def load(path: Path = TFIDF_PATH) -> "TfidfSentimentModel":
        saved = joblib.load(path)
        model = TfidfSentimentModel(saved["c"])
        model.pipeline = saved["pipeline"]
        return model


class Vocabulary:
    """Dictionnaire mot -> indice, construit sur les avis d'apprentissage.
    Indice 0 : remplissage ; indice 1 : mot inconnu."""

    PAD = 0
    UNKNOWN = 1

    def __init__(self, min_freq: int = 2, max_size: int = 20000) -> None:
        self.min_freq = min_freq
        self.max_size = max_size
        self.index: dict[str, int] = {}

    def fit(self, tokenized: list[list[str]]) -> "Vocabulary":
        counts = Counter(token for tokens in tokenized for token in tokens)
        frequent = [
            token for token, count in counts.most_common(self.max_size)
            if count >= self.min_freq
        ]
        self.index = {token: rank + 2 for rank, token in enumerate(frequent)}
        return self

    def __len__(self) -> int:
        return len(self.index) + 2

    def encode(self, tokens: list[str], max_len: int) -> list[int]:
        ids = [self.index.get(token, self.UNKNOWN) for token in tokens]
        return ids[:max_len] or [self.UNKNOWN]


class GruClassifier(nn.Module):
    """Plongements de mots -> GRU bidirectionnel -> probabilité négative.

    Le GRU lit l'avis dans les deux sens, ce qui permet de tenir compte de
    l'ordre des mots (« não gostei » n'est pas « gostei »).
    """

    def __init__(self, vocabulary_size: int, embedding_dim: int,
                 hidden_dim: int, dropout: float) -> None:
        super().__init__()
        self.embedding = nn.Embedding(vocabulary_size, embedding_dim,
                                      padding_idx=Vocabulary.PAD)
        self.gru = nn.GRU(embedding_dim, hidden_dim, batch_first=True,
                          bidirectional=True)
        self.dropout = nn.Dropout(dropout)
        self.output = nn.Linear(2 * hidden_dim, 1)

    def forward(self, ids: torch.Tensor,
                lengths: torch.Tensor) -> torch.Tensor:
        embedded = self.dropout(self.embedding(ids))
        packed = pack_padded_sequence(embedded, lengths, batch_first=True,
                                      enforce_sorted=False)
        _, hidden = self.gru(packed)
        features = torch.cat([hidden[0], hidden[1]], dim=1)
        return self.output(self.dropout(features)).squeeze(1)


class SequenceBatcher:
    """Découpe des séquences d'indices en lots complétés par du
    remplissage."""

    def __init__(self, sequences: list[list[int]], batch_size: int) -> None:
        self.sequences = sequences
        self.batch_size = batch_size

    def batches(self, order: np.ndarray) -> Iterator[tuple[np.ndarray,
                                                           torch.Tensor,
                                                           torch.Tensor]]:
        for start in range(0, len(order), self.batch_size):
            index = order[start:start + self.batch_size]
            tensors = [torch.tensor(self.sequences[i]) for i in index]
            ids = pad_sequence(tensors, batch_first=True,
                               padding_value=Vocabulary.PAD)
            lengths = torch.tensor([len(tensor) for tensor in tensors])
            yield index, ids, lengths


class NeuralSentimentModel:
    """Réseau GRU entraîné avec arrêt anticipé sur la validation.

    L'historique par époque (perte et PR-AUC en apprentissage et en
    validation) donne les courbes d'apprentissage.
    """

    def __init__(self, embedding_dim: int = 64, hidden_dim: int = 64,
                 dropout: float = 0.3, max_len: int = 80,
                 batch_size: int = 128, epochs: int = 15,
                 learning_rate: float = 2e-3, patience: int = 3,
                 seed: int = RANDOM_STATE) -> None:
        self.config = {
            "embedding_dim": embedding_dim, "hidden_dim": hidden_dim,
            "dropout": dropout, "max_len": max_len,
            "batch_size": batch_size, "epochs": epochs,
            "learning_rate": learning_rate, "patience": patience,
            "seed": seed,
        }
        self.vocabulary = Vocabulary()
        self.network: GruClassifier | None = None
        self.history = pd.DataFrame()

    def encode(self, texts: pd.Series) -> list[list[int]]:
        return [
            self.vocabulary.encode(TextNormalizer.tokenize(text),
                                   self.config["max_len"])
            for text in texts
        ]

    def build_network(self) -> GruClassifier:
        return GruClassifier(len(self.vocabulary),
                             self.config["embedding_dim"],
                             self.config["hidden_dim"],
                             self.config["dropout"])

    def logits(self, sequences: list[list[int]]) -> torch.Tensor:
        """Sorties du réseau en mode évaluation, dans l'ordre d'entrée."""
        self.network.eval()
        output = torch.empty(len(sequences))
        batcher = SequenceBatcher(sequences, 4 * self.config["batch_size"])
        with torch.no_grad():
            for index, ids, lengths in batcher.batches(
                np.arange(len(sequences))
            ):
                output[torch.from_numpy(index)] = self.network(ids, lengths)
        return output

    def fit(self, train: pd.DataFrame,
            validation: pd.DataFrame) -> "NeuralSentimentModel":
        seed = self.config["seed"]
        torch.manual_seed(seed)
        rng = np.random.default_rng(seed)
        self.vocabulary = Vocabulary().fit(
            [TextNormalizer.tokenize(text) for text in train["text"]]
        )
        train_sequences = self.encode(train["text"])
        validation_sequences = self.encode(validation["text"])
        y_train = train[TARGET].to_numpy(dtype=np.float32)
        y_validation = validation[TARGET].to_numpy(dtype=np.float32)
        monitor = rng.choice(len(train), min(5000, len(train)),
                             replace=False)
        self.network = self.build_network()
        optimizer = torch.optim.Adam(self.network.parameters(),
                                     lr=self.config["learning_rate"])
        loss_function = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(
            (1 - y_train.mean()) / y_train.mean()
        ))
        batcher = SequenceBatcher(train_sequences, self.config["batch_size"])
        best_score, best_state = -np.inf, None
        patience_left = self.config["patience"]
        history = []
        for epoch in range(1, self.config["epochs"] + 1):
            self.network.train()
            for index, ids, lengths in batcher.batches(
                rng.permutation(len(train_sequences))
            ):
                optimizer.zero_grad()
                loss = loss_function(self.network(ids, lengths),
                                     torch.from_numpy(y_train[index]))
                loss.backward()
                nn.utils.clip_grad_norm_(self.network.parameters(), 1.0)
                optimizer.step()
            history.append({
                "epoch": epoch,
                **self.epoch_scores(
                    "train", [train_sequences[i] for i in monitor],
                    y_train[monitor], loss_function,
                ),
                **self.epoch_scores("validation", validation_sequences,
                                    y_validation, loss_function),
            })
            score = history[-1]["validation_pr_auc"]
            if score > best_score:
                best_score = score
                best_state = copy.deepcopy(self.network.state_dict())
                patience_left = self.config["patience"]
            else:
                patience_left -= 1
                if patience_left == 0:
                    break
        self.network.load_state_dict(best_state)
        self.history = pd.DataFrame(history)
        return self

    def epoch_scores(self, name: str, sequences: list[list[int]],
                     y: np.ndarray,
                     loss_function: nn.Module) -> dict[str, float]:
        logits = self.logits(sequences)
        return {
            f"{name}_loss": loss_function(logits,
                                          torch.from_numpy(y)).item(),
            f"{name}_pr_auc": average_precision_score(
                y, torch.sigmoid(logits).numpy()
            ),
        }

    def predict_proba(self, texts: pd.Series) -> np.ndarray:
        return torch.sigmoid(self.logits(self.encode(texts))).numpy()

    def save(self, path: Path = NEURAL_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save({
            "config": self.config,
            "vocabulary": self.vocabulary.index,
            "state_dict": self.network.state_dict(),
        }, path)

    @staticmethod
    def load(path: Path = NEURAL_PATH) -> "NeuralSentimentModel":
        saved = torch.load(path, weights_only=True)
        model = NeuralSentimentModel(**saved["config"])
        model.vocabulary.index = saved["vocabulary"]
        model.network = model.build_network()
        model.network.load_state_dict(saved["state_dict"])
        return model


@dataclass
class SentimentResults:
    """Résultats de la comparaison, pour le rapport et le notebook."""

    sizes: dict[str, float]
    tfidf_tuning: pd.DataFrame
    thresholds: dict[str, float]
    validation_scores: pd.DataFrame
    test_scores: pd.DataFrame
    best_model: str
    history: pd.DataFrame
    learning_curve: pd.DataFrame
    top_terms: pd.DataFrame
    test_predictions: pd.DataFrame
    neutral_predictions: pd.DataFrame


class SentimentExperiment:
    """Compare la baseline TF-IDF et le réseau GRU, du réglage au test."""

    def __init__(self, frame: pd.DataFrame) -> None:
        self.parts = ReviewDataset.split(frame)
        self.tfidf = TfidfSentimentModel()
        self.neural = NeuralSentimentModel()

    def sizes(self) -> dict[str, float]:
        sizes = {}
        for name, part in self.parts.items():
            sizes[f"{name}_reviews"] = len(part)
            if name != "neutral":
                sizes[f"{name}_negative_rate"] = part[TARGET].mean()
        return sizes

    def fit(self) -> pd.DataFrame:
        tuning = self.tfidf.tune(self.parts["train"],
                                 self.parts["validation"])
        self.neural.fit(self.parts["train"], self.parts["validation"])
        return tuning

    def models(self) -> dict[str, TfidfSentimentModel |
                             NeuralSentimentModel]:
        return {TFIDF: self.tfidf, NEURAL: self.neural}

    def predictions(self, part: str) -> pd.DataFrame:
        frame = self.parts[part][["review_id", "score", "text",
                                  TARGET]].copy()
        for name, model in self.models().items():
            frame[f"proba_{name}"] = model.predict_proba(frame["text"])
        return frame

    def scores(self, predictions: pd.DataFrame,
               thresholds: dict[str, float]) -> pd.DataFrame:
        y = predictions[TARGET].to_numpy()
        return pd.DataFrame({
            name: SentimentMetrics.compute(
                y, predictions[f"proba_{name}"].to_numpy(),
                thresholds[name],
            )
            for name in self.models()
        }).T

    def choose(self, validation_scores: pd.DataFrame) -> str:
        """Le réseau n'est retenu que s'il gagne au moins 0,01 de PR-AUC
        en validation : sinon, la baseline (plus simple, plus rapide, plus
        explicable) suffit."""
        gain = (validation_scores.loc[NEURAL, "pr_auc"]
                - validation_scores.loc[TFIDF, "pr_auc"])
        return NEURAL if gain >= MIN_NEURAL_GAIN else TFIDF

    def learning_curve(self) -> pd.DataFrame:
        """PR-AUC de validation selon la part des avis d'apprentissage."""
        train, validation = self.parts["train"], self.parts["validation"]
        y = validation[TARGET].to_numpy()
        rows = []
        for share in LEARNING_CURVE_SHARES:
            subset = train.sample(frac=share, random_state=RANDOM_STATE)
            models = (
                self.models() if share == 1.0 else {
                    TFIDF: TfidfSentimentModel(self.tfidf.c).fit(
                        subset["text"], subset[TARGET]
                    ),
                    NEURAL: NeuralSentimentModel().fit(subset, validation),
                }
            )
            for name, model in models.items():
                rows.append({
                    "share": share, "train_reviews": len(subset),
                    "model": name,
                    "validation_pr_auc": average_precision_score(
                        y, model.predict_proba(validation["text"])
                    ),
                })
        return pd.DataFrame(rows)

    def run(self) -> SentimentResults:
        tuning = self.fit()
        validation = self.predictions("validation")
        thresholds = {
            name: SentimentMetrics.best_f1_threshold(
                validation[TARGET].to_numpy(),
                validation[f"proba_{name}"].to_numpy(),
            )
            for name in self.models()
        }
        validation_scores = self.scores(validation, thresholds)
        test = self.predictions("test")
        neutral = self.predictions("neutral")
        return SentimentResults(
            sizes=self.sizes(),
            tfidf_tuning=tuning,
            thresholds=thresholds,
            validation_scores=validation_scores,
            test_scores=self.scores(test, thresholds),
            best_model=self.choose(validation_scores),
            history=self.neural.history,
            learning_curve=self.learning_curve(),
            top_terms=self.tfidf.top_terms(),
            test_predictions=test,
            neutral_predictions=neutral,
        )

    def save_best(self, results: SentimentResults) -> Path:
        """Enregistre le modèle retenu avec son seuil de décision."""
        model = self.models()[results.best_model]
        path = TFIDF_PATH if results.best_model == TFIDF else NEURAL_PATH
        model.save(path)
        joblib.dump({
            "model_name": results.best_model,
            "path": path.name,
            "threshold": results.thresholds[results.best_model],
            "test_scores": results.test_scores.loc[
                results.best_model
            ].to_dict(),
            "trained_at": datetime.now().isoformat(timespec="seconds"),
        }, MODELS_DIR / "sentiment_model.joblib")
        return path


class SentimentReport:
    """Rapport Markdown du modèle de sentiment, régénéré à chaque
    entraînement."""

    def __init__(self, results: SentimentResults) -> None:
        self.results = results

    def to_markdown(self) -> str:
        results, sizes = self.results, self.results.sizes
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [
            "# Modèle de sentiment des avis",
            "",
            (
                f"Généré automatiquement par le pipeline d'entraînement le "
                f"{generated_at}. Ne pas modifier à la main. Analyse "
                "complète : `notebooks/06_modele_sentiment.ipynb`."
            ),
            "",
            "## Données",
            "",
        ]
        for part in ("train", "validation", "test"):
            lines.append(
                f"- {part} : {NumberFormat.thousands(sizes[part + '_reviews'])}"
                f" avis, {NumberFormat.percent(sizes[part + '_negative_rate'])}"
                " négatifs"
            )
        lines += [
            (
                "- notes de 3 (exclues, analysées à part) : "
                f"{NumberFormat.thousands(sizes['neutral_reviews'])} avis"
            ),
            "",
            "## Résultats",
            "",
            (
                f"Modèle retenu (meilleur PR-AUC de validation, le réseau "
                f"devant gagner au moins {MIN_NEURAL_GAIN}) : "
                f"**{results.best_model}**. Régularisation de la baseline "
                f"choisie en validation : C = {self.c()}. Seuils de "
                "décision (F1 maximal en validation) : "
                + ", ".join(f"{name} = {value:.3f}"
                            for name, value in results.thresholds.items())
                + "."
            ),
        ]
        for title, scores in (("Validation", results.validation_scores),
                              ("Test", results.test_scores)):
            lines += ["", f"### {title}", ""]
            lines += self.table(scores)
        lines += ["", "## Mots les plus déterminants (baseline)", ""]
        lines += [
            "| Vers « négatif » | Poids | Vers « positif » | Poids |",
            "|---|---:|---|---:|",
        ]
        for row in results.top_terms.itertuples(index=False):
            lines.append(
                f"| {row[0]} | {row[1]:.2f} | {row[2]} | {row[3]:.2f} |"
            )
        return "\n".join(lines) + "\n"

    def c(self) -> float:
        tuning = self.results.tfidf_tuning
        return float(tuning.loc[tuning["pr_auc"].idxmax(), "C"])

    @staticmethod
    def table(scores: pd.DataFrame) -> list[str]:
        columns = list(scores.columns)
        lines = [
            "| Modèle | " + " | ".join(columns) + " |",
            "|---|" + "---:|" * len(columns),
        ]
        for model, row in scores.iterrows():
            cells = [f"{row[column]:.3f}" for column in columns]
            lines.append(f"| {model} | " + " | ".join(cells) + " |")
        return lines

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_markdown(), encoding="utf-8")
