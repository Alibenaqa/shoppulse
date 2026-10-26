"""Rapports générés : qualité, analyses SQL, tableau de bord."""

import pytest

from shoppulse.analysis import SqlQuery
from shoppulse.quality import (
    QUALITY_CHECKS,
    CheckResult,
    QualityCheck,
    QualityChecker,
    QualityReport,
)


class TestQualityReport:
    @pytest.fixture
    def results(self) -> list[CheckResult]:
        blocking = QualityCheck("doublons", "Doublons", "", "", blocking=True)
        signal = QualityCheck("signal", "Anomalie signalée", "", "")
        return [CheckResult(blocking, 10, 0), CheckResult(signal, 5, 5)]

    def test_blocking_check_fails_only_if_core_is_not_clean(self) -> None:
        check = QualityCheck("x", "x", "", "", blocking=True)
        assert CheckResult(check, 10, 1).failed
        assert not CheckResult(check, 10, 0).failed
        assert not CheckResult(QualityCheck("y", "y", "", ""), 1, 1).failed

    def test_failures_lists_only_failed_checks(self, results) -> None:
        assert QualityChecker.failures(results) == []

    def test_markdown_shows_volumes_and_statuses(self, results) -> None:
        volumes = {"raw": {"raw.orders": 1200}, "core": {"core.orders": 1200}}
        markdown = QualityReport(results, volumes).to_markdown()
        assert "| raw.orders → core.orders | 1 200 | 1 200 |" in markdown
        assert "OK (bloquant)" in markdown
        assert "signalé" in markdown

    def test_every_check_compares_raw_and_core(self) -> None:
        for check in QUALITY_CHECKS:
            assert "raw." in check.raw_sql
            assert "core." in check.core_sql


class TestSqlQuery:
    def test_header_is_parsed_with_continuation_lines(self, tmp_path) -> None:
        path = tmp_path / "01_test.sql"
        path.write_text(
            "-- Titre : Mon titre\n"
            "-- Question : Une question\n"
            "--   sur deux lignes ?\n"
            "-- Techniques : agrégat\n"
            "\n"
            "SELECT 1;\n",
            encoding="utf-8",
        )
        query = SqlQuery(path)
        assert query.title == "Mon titre"
        assert query.metadata["Question"] == "Une question sur deux lignes ?"
        assert "SELECT 1" in query.sql

    def test_title_falls_back_to_the_file_name(self, tmp_path) -> None:
        path = tmp_path / "02_sans_titre.sql"
        path.write_text("SELECT 1;\n", encoding="utf-8")
        assert SqlQuery(path).title == "02_sans_titre"


class TestDashboardHelpers:
    def test_money_and_deltas(self) -> None:
        pytest.importorskip("streamlit")
        from shoppulse.dashboard import Dashboard

        assert Dashboard.money(2_500_000) == "2,50 M R$"
        assert Dashboard.money(85_000) == "85 k R$"
        assert Dashboard.delta_pct(110, 100) == "+10.0 %"
        assert Dashboard.delta_pct(1, 0) is None
