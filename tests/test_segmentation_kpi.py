"""Segmentation RFM, campagnes et indicateurs du tableau de bord."""

from datetime import date

import pytest

from shoppulse.kpi import KpiCalculator
from shoppulse.segmentation import (
    K_CANDIDATES,
    PERSONA_LOST,
    PERSONA_LOYAL,
    Campaign,
    CampaignCatalog,
    CampaignForecast,
    CampaignSimulator,
    CustomerSegmenter,
    RfmTable,
)
from tests.synthetic import SyntheticData


class TestRfm:
    def test_scores_are_between_one_and_five(self) -> None:
        scored = RfmTable.add_scores(SyntheticData.rfm())
        assert scored["r_score"].between(1, 5).all()
        assert scored["m_score"].between(1, 5).all()
        assert scored["f_score"].between(1, 3).all()

    def test_recent_customers_get_high_recency_scores(self) -> None:
        scored = RfmTable.add_scores(SyntheticData.rfm())
        recent = scored.nsmallest(20, "recency")["r_score"]
        assert (recent == 5).all()


class TestCustomerSegmenter:
    def test_four_clusters_get_four_personas(self, segmented) -> None:
        assert segmented["persona"].nunique() == 4

    def test_loyal_persona_has_the_highest_frequency(self,
                                                     segmented) -> None:
        profile = CustomerSegmenter.profile(segmented, by="persona")
        assert profile["frequency"].idxmax() == PERSONA_LOYAL

    def test_predict_matches_training_labels(self, tmp_path) -> None:
        rfm = RfmTable.add_scores(SyntheticData.rfm())
        segmenter = CustomerSegmenter(n_clusters=4)
        segmented = segmenter.fit_predict(rfm)
        path = tmp_path / "segmentation.joblib"
        segmenter.save(path)
        predicted = CustomerSegmenter.load(path).predict(rfm)
        assert (predicted["persona"] == segmented["persona"]).all()

    def test_number_of_clusters_chosen_by_silhouette(self) -> None:
        rfm = RfmTable.add_scores(SyntheticData.rfm())
        segmenter = CustomerSegmenter()
        segmenter.fit_predict(rfm)
        assert segmenter.n_clusters in K_CANDIDATES
        assert set(segmenter.silhouettes) == set(K_CANDIDATES)


class TestCampaigns:
    def test_forecast_arithmetic(self) -> None:
        campaign = Campaign("test", PERSONA_LOYAL, "action",
                            contact_cost=0.05, conversion_rate=0.05,
                            baseline_rate=0.02, incentive_rate=0.10)
        forecast = CampaignForecast(campaign, target_customers=1000,
                                    avg_basket=100.0)
        assert forecast.extra_orders == pytest.approx(30)
        assert forecast.extra_revenue == pytest.approx(3000)
        assert forecast.cost == pytest.approx(550)
        assert forecast.net_gain == pytest.approx(2450)

    def test_lost_customers_get_no_campaign(self) -> None:
        assert CampaignCatalog.for_persona(PERSONA_LOST) is None
        assert CampaignCatalog.for_persona(PERSONA_LOYAL).name == "Club VIP"

    def test_simulator_summarizes_three_campaigns(self, segmented) -> None:
        summary = CampaignSimulator(segmented).summary()
        assert len(summary) == 3
        assert (summary["clients ciblés"] > 0).all()


class TestKpiCalculator:
    @pytest.fixture
    def calculator(self) -> KpiCalculator:
        return KpiCalculator(SyntheticData.activity_orders())

    def test_kpis_ignore_cancelled_orders(self, calculator) -> None:
        kpis = calculator.period(date(2018, 1, 1), date(2018, 2, 28))
        assert kpis.orders == 4
        assert kpis.revenue == 500.0
        assert kpis.avg_basket == 125.0
        assert kpis.late_rate == pytest.approx(100 / 3)
        assert kpis.avg_score == pytest.approx(3.0)

    def test_region_filter(self, calculator) -> None:
        kpis = calculator.period(date(2018, 1, 1), date(2018, 2, 28),
                                 ["Nordeste"])
        assert kpis.orders == 1

    def test_previous_period_has_the_same_length(self, calculator) -> None:
        kpis = calculator.previous_period(date(2018, 1, 1),
                                          date(2018, 1, 31))
        assert kpis.orders == 1
        assert kpis.revenue == 80.0

    def test_monthly_revenue(self, calculator) -> None:
        monthly = KpiCalculator.monthly(calculator.orders)
        assert monthly["revenue"].sum() == 580.0

    def test_late_rate_by_state(self, calculator) -> None:
        late = KpiCalculator.late_by_state(calculator.orders, min_orders=1)
        assert list(late.index) == ["SP"]
        assert late.loc["SP", "late_rate"] == 25.0
