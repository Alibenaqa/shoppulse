"""Données synthétiques pour tester sans la base ni les données Olist."""

import numpy as np
import pandas as pd

STATES = ["SP", "RJ", "MG", "BA", "RS"]
STATE_CENTERS = {
    "SP": (-23.5, -46.6), "RJ": (-22.9, -43.2), "MG": (-19.9, -43.9),
    "BA": (-12.9, -38.5), "RS": (-30.0, -51.2),
}
POSITIVE_PHRASES = [
    "chegou antes do prazo", "produto ótimo recomendo", "adorei muito bom",
    "entrega rápida", "perfeito obrigada", "excelente qualidade",
]
NEGATIVE_PHRASES = [
    "não recebi o produto", "produto quebrado", "péssimo atendimento",
    "chegou atrasado e com defeito", "não recomendo", "muito ruim",
]
FILLER_WORDS = ["loja", "compra", "pedido", "site", "caixa", "cor"]


class SyntheticData:
    """Générateurs déterministes de petites tables réalistes."""

    @staticmethod
    def zip_code(state: str, index: int) -> str:
        return f"{STATES.index(state) + 1}{index:04d}"

    @staticmethod
    def delay_orders(n: int = 600, seed: int = 0) -> pd.DataFrame:
        """Commandes livrées, au format de DELAY_ORDERS_SQL (plus les codes
        postaux, pour le test de cohérence de l'API)."""
        rng = np.random.default_rng(seed)
        purchase = pd.Timestamp("2017-01-05") + pd.to_timedelta(
            np.sort(rng.uniform(0, 600, n)), unit="D"
        )
        sellers = [f"{index:032x}" for index in range(8)]
        seller_ids = rng.choice(sellers, n)
        seller_states = {
            seller: STATES[index % 3] for index, seller in enumerate(sellers)
        }
        customer_states = rng.choice(STATES, n)
        customer_zips = [
            SyntheticData.zip_code(state, int(rng.integers(0, 5)))
            for state in customer_states
        ]
        seller_zips = [
            SyntheticData.zip_code(seller_states[seller], 9)
            for seller in seller_ids
        ]
        promised = rng.integers(8, 30, n)
        delivered = rng.integers(3, 35, n)
        frame = pd.DataFrame({
            "order_id": [f"{index:032x}" for index in range(n)],
            "purchase_timestamp": purchase,
            "delivered_carrier_date": purchase + pd.to_timedelta(
                rng.integers(0, 5, n), unit="D"
            ),
            "estimated_delivery_date": purchase.normalize()
            + pd.to_timedelta(promised, unit="D"),
            "delivered_customer_date": purchase + pd.to_timedelta(
                delivered, unit="D"
            ),
            "customer_state": customer_states,
            "seller_state": [seller_states[seller] for seller in seller_ids],
            "seller_id": seller_ids,
            "customer_zip": customer_zips,
            "seller_zip": seller_zips,
            "n_items": 1,
            "n_sellers": 1,
            "order_value": rng.uniform(20, 300, n).round(2),
            "freight_value": rng.uniform(5, 50, n).round(2),
            "total_weight_g": rng.uniform(100, 5000, n).round(0),
        })
        coordinates = SyntheticData.geolocation(frame)
        for side, column in (("customer", "customer_zip"),
                             ("seller", "seller_zip")):
            frame[f"{side}_lat"] = frame[column].map(coordinates["lat"])
            frame[f"{side}_lng"] = frame[column].map(coordinates["lng"])
        return frame

    @staticmethod
    def geolocation(orders: pd.DataFrame) -> pd.DataFrame:
        """Coordonnées par code postal (centre de l'état + décalage)."""
        rows = {}
        for column, state_column in (("customer_zip", "customer_state"),
                                     ("seller_zip", "seller_state")):
            for zip_code, state in zip(orders[column], orders[state_column]):
                lat, lng = STATE_CENTERS[state]
                offset = int(zip_code[-1]) * 0.05
                rows[zip_code] = {"lat": lat + offset, "lng": lng - offset}
        return pd.DataFrame.from_dict(rows, orient="index").rename_axis(
            "zip_code_prefix"
        )

    @staticmethod
    def sellers(orders: pd.DataFrame) -> pd.DataFrame:
        return (
            orders[["seller_id", "seller_zip", "seller_state"]]
            .drop_duplicates("seller_id")
            .rename(columns={"seller_zip": "zip_code_prefix",
                             "seller_state": "state"})
            .set_index("seller_id")
        )

    @staticmethod
    def reviews(n: int = 400, seed: int = 0) -> pd.DataFrame:
        """Avis au format de ReviewDataset.load() (30 % négatifs, 8 % de
        notes 3)."""
        rng = np.random.default_rng(seed)
        rows = []
        for index in range(n):
            draw = rng.uniform()
            negative = draw < 0.3
            neutral = 0.3 <= draw < 0.38
            phrases = NEGATIVE_PHRASES if negative else POSITIVE_PHRASES
            words = [str(rng.choice(phrases)), str(rng.choice(FILLER_WORDS))]
            if rng.uniform() < 0.5:
                words.append(str(rng.choice(phrases)))
            score = (int(rng.integers(1, 3)) if negative
                     else 3 if neutral else int(rng.integers(4, 6)))
            rows.append({
                "review_id": f"{index:032x}",
                "creation_date": pd.Timestamp("2017-01-01")
                + pd.Timedelta(days=index),
                "score": score,
                "text": " ".join(words),
                "is_negative": 1 if score <= 2 else (0 if score >= 4 else -1),
            })
        return pd.DataFrame(rows)

    @staticmethod
    def rfm(n: int = 400, seed: int = 0) -> pd.DataFrame:
        """Table RFM au format de RfmTable.load() avant les scores."""
        rng = np.random.default_rng(seed)
        frequency = np.where(rng.uniform(size=n) < 0.1,
                             rng.integers(2, 5, n), 1)
        return pd.DataFrame({
            "customer_unique_id": [f"{index:032x}" for index in range(n)],
            "state": rng.choice(STATES, n),
            "recency": rng.integers(30, 700, n),
            "frequency": frequency,
            "monetary": (rng.lognormal(4.5, 0.8, n) * frequency).round(2),
        })

    @staticmethod
    def activity_orders() -> pd.DataFrame:
        """Commandes au format de ActivityData.orders()."""
        return pd.DataFrame({
            "order_id": ["a", "b", "c", "d", "e", "f"],
            "purchase_timestamp": pd.to_datetime([
                "2018-01-05", "2018-01-20", "2018-02-10", "2018-02-15",
                "2017-12-20", "2018-02-20",
            ]),
            "is_valid": [True, True, True, True, True, False],
            "state": ["SP", "SP", "BA", "SP", "SP", "BA"],
            "region": ["Sudeste", "Sudeste", "Nordeste", "Sudeste",
                       "Sudeste", "Nordeste"],
            "revenue": [100.0, 50.0, 200.0, 150.0, 80.0, 999.0],
            "is_late": [False, True, None, False, False, None],
            "score": [5.0, 2.0, 4.0, None, 5.0, 1.0],
        })
