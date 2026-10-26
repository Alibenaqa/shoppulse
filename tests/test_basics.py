"""Utilitaires : texte, géographie, formats, configuration."""

from shoppulse.config import DatabaseSettings
from shoppulse.formatting import NumberFormat
from shoppulse.geography import STATE_TO_REGION, BrazilRegions
from shoppulse.text import TextNormalizer


class TestTextNormalizer:
    def test_clean_lowercases_and_collapses_spaces(self) -> None:
        assert TextNormalizer.clean("  Ótimo   PRODUTO\r\n") == "ótimo produto"

    def test_tokenize_keeps_accents_negation_and_exclamations(self) -> None:
        assert TextNormalizer.tokenize("Não gostei!! 10/10") == [
            "não", "gostei", "!", "!", "10", "10",
        ]


class TestGeography:
    def test_brazil_has_27_states_in_5_regions(self) -> None:
        assert len(STATE_TO_REGION) == 27
        assert len(set(STATE_TO_REGION.values())) == 5

    def test_region_of_state(self) -> None:
        assert BrazilRegions.of("SP") == "Sudeste"
        assert BrazilRegions.of("MA") == "Nordeste"
        assert BrazilRegions.of("XX") == "Inconnue"


class TestNumberFormat:
    def test_thousands_use_a_space(self) -> None:
        assert NumberFormat.thousands(1234567) == "1 234 567"

    def test_percent_uses_a_comma(self) -> None:
        assert NumberFormat.percent(0.1234) == "12,3 %"


class TestDatabaseSettings:
    def test_conninfo_contains_every_parameter(self) -> None:
        settings = DatabaseSettings()
        settings.dbname = "shoppulse_test"
        conninfo = settings.conninfo()
        for key in ("host=", "port=", "dbname=shoppulse_test", "user="):
            assert key in conninfo
