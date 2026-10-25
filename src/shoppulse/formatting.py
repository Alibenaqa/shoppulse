"""Mise en forme des nombres pour les rapports Markdown."""


class NumberFormat:
    """Formats français partagés par les rapports générés."""

    @staticmethod
    def thousands(value: float) -> str:
        """Entier avec une espace comme séparateur de milliers."""
        return f"{value:,.0f}".replace(",", " ")

    @staticmethod
    def percent(value: float, digits: int = 1) -> str:
        """Proportion (entre 0 et 1) affichée en pourcentage."""
        return f"{100 * value:.{digits}f} %".replace(".", ",")
