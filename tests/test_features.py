"""Variables du modèle de retard : exactitude et absence de fuite."""

import numpy as np
import pandas as pd
import pytest

from shoppulse.features import (
    FEATURES,
    TARGET,
    DelayFeatureBuilder,
    DelayServingSnapshot,
    TimeAwareHistory,
    UnknownSellerError,
)


class TestTimeAwareHistory:
    @pytest.fixture
    def history(self) -> TimeAwareHistory:
        events = pd.DataFrame({
            "seller_id": ["a", "a", "a", "b"],
            "time": pd.to_datetime(["2018-01-01", "2018-01-10",
                                    "2018-01-20", "2018-01-05"]),
            "value": [1, 0, 1, 1],
        })
        return TimeAwareHistory(events, ["seller_id"], "time", "value")

    @staticmethod
    def query(seller: str, at: str) -> tuple[pd.DataFrame, pd.Series]:
        queries = pd.DataFrame({"seller_id": [seller]})
        return queries, pd.Series(pd.to_datetime([at]))

    def test_counts_only_events_strictly_before(self, history) -> None:
        window = history.window(*self.query("a", "2018-01-10"))
        assert window.loc[0, "count"] == 1
        assert window.loc[0, "sum"] == 1

    def test_counts_all_past_events_of_the_key(self, history) -> None:
        window = history.window(*self.query("a", "2018-02-01"))
        assert (window.loc[0, "count"], window.loc[0, "sum"]) == (3, 2)

    def test_window_drops_old_events(self, history) -> None:
        window = history.window(*self.query("a", "2018-01-25"),
                                pd.Timedelta(days=10))
        assert window.loc[0, "count"] == 1

    def test_unknown_key_has_no_history(self, history) -> None:
        window = history.window(*self.query("z", "2018-02-01"))
        assert window.loc[0, "count"] == 0

    def test_smoothed_mean_moves_toward_the_prior(self) -> None:
        window = pd.DataFrame({"sum": [0.0, 10.0], "count": [0.0, 10.0]})
        smoothed = TimeAwareHistory.smoothed_mean(window, 0.5, weight=10)
        assert smoothed.tolist() == [0.5, 0.75]


class TestDelayFeatureBuilder:
    def test_target_and_known_at(self) -> None:
        raw = pd.DataFrame({
            "purchase_timestamp": pd.to_datetime(["2018-01-01"] * 2),
            "delivered_carrier_date": pd.to_datetime(["2018-01-02"] * 2),
            "estimated_delivery_date": pd.to_datetime(["2018-01-10"] * 2),
            "delivered_customer_date": pd.to_datetime(
                ["2018-01-08 15:00", "2018-01-15 09:00"]
            ),
            "seller_state": ["SP", "SP"],
            "customer_state": ["SP", "RJ"],
        })
        prepared = DelayFeatureBuilder.prepare(raw)
        assert prepared[TARGET].tolist() == [0, 1]
        assert prepared.loc[0, "known_at"] == pd.Timestamp("2018-01-08 15:00")
        assert prepared.loc[1, "known_at"] == pd.Timestamp("2018-01-11")
        assert prepared["estimated_days"].tolist() == [9, 9]
        assert prepared["route"].tolist() == ["SP>SP", "SP>RJ"]

    def test_haversine_sao_paulo_rio(self) -> None:
        distance = DelayFeatureBuilder.haversine_km(-23.55, -46.63,
                                                    -22.91, -43.17)
        assert 350 < distance < 365

    def test_build_returns_sorted_features(self, delay_frame) -> None:
        assert list(delay_frame.columns) == [
            "order_id", "purchase_timestamp", "customer_region",
            *FEATURES, TARGET,
        ]
        assert delay_frame["purchase_timestamp"].is_monotonic_increasing
        assert delay_frame["customer_state"].dtype.name == "category"

    def test_seller_history_never_uses_the_future(self, delay_raw,
                                                  delay_frame) -> None:
        """Le volume passé du vendeur = ses commandes dont le statut était
        connu avant l'achat (recalcul naïf, ligne par ligne)."""
        prepared = DelayFeatureBuilder.prepare(delay_raw)
        for row in delay_frame.sample(30, random_state=0).itertuples():
            seller = prepared.loc[prepared["order_id"] == row.order_id,
                                  "seller_id"].iloc[0]
            same = prepared[prepared["seller_id"] == seller]
            expected = (same["known_at"] < row.purchase_timestamp).sum()
            assert row.seller_past_orders == expected

    def test_promise_slack_is_promise_minus_expected(self,
                                                     delay_frame) -> None:
        slack = delay_frame["estimated_days"] - delay_frame[
            "route_expected_days"
        ]
        assert np.allclose(slack, delay_frame["promise_slack_days"],
                           equal_nan=True)


class TestDelayServingSnapshot:
    def test_online_features_match_training_features(self, delay_raw,
                                                     delay_frame,
                                                     delay_snapshot) -> None:
        """Pas de décalage entre entraînement et API."""
        batch = delay_frame.set_index("order_id")
        for row in delay_raw.sample(20, random_state=1).itertuples():
            order = {
                "customer_zip_prefix": row.customer_zip,
                "customer_state": row.customer_state,
                "seller_id": row.seller_id,
                "estimated_days": int(batch.loc[row.order_id,
                                                "estimated_days"]),
                "items": [{"price": row.order_value,
                           "freight_value": row.freight_value,
                           "weight_g": row.total_weight_g}],
            }
            online = delay_snapshot.features(order,
                                             at=row.purchase_timestamp)
            expected = batch.loc[[row.order_id], FEATURES]
            pd.testing.assert_frame_equal(
                online.reset_index(drop=True),
                expected.reset_index(drop=True),
                check_dtype=False,
            )

    def test_unknown_seller_is_rejected(self, delay_snapshot) -> None:
        order = {"customer_zip_prefix": "00000", "customer_state": "SP",
                 "seller_id": "f" * 32, "estimated_days": 10,
                 "items": [{"price": 10.0, "freight_value": 1.0}]}
        with pytest.raises(UnknownSellerError):
            delay_snapshot.features(order)

    def test_unknown_zip_gives_missing_distance(self,
                                                delay_snapshot) -> None:
        seller = delay_snapshot.sellers.index[0]
        order = {"customer_zip_prefix": "99999", "customer_state": "SP",
                 "seller_id": seller, "estimated_days": 10,
                 "items": [{"price": 10.0, "freight_value": 1.0,
                            "weight_g": None}]}
        features = delay_snapshot.features(order)
        assert np.isnan(features.loc[0, "distance_km"])
        assert np.isnan(features.loc[0, "total_weight_g"])
        assert isinstance(delay_snapshot, DelayServingSnapshot)
