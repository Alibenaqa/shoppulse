"""Nettoyage des textes d'avis, partagé par l'entraînement et l'API.

Module volontairement léger (sans PyTorch) : le modèle TF-IDF enregistré y
fait référence, l'API peut donc le charger sans installer PyTorch.
"""

import re
import unicodedata

TOKEN_PATTERN = r"[a-zà-ÿ0-9]+|[!?]"


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
