-- Titre : Taux de réachat et délai avant la deuxième commande
-- Question : Combien de clients reviennent, et au bout de combien de temps ?
-- Destinataire : Marketing
-- Techniques : jointure, fonctions de fenêtre ROW_NUMBER() et LEAD(),
--   agrégats conditionnels (FILTER), PERCENTILE_CONT
-- Note : un client réel est identifié par customer_unique_id (Olist crée
--   un customer_id différent à chaque commande).
-- Lecture : seulement 3 % des clients repassent commande ; la moitié
--   de ceux-là le font en moins de 28 jours. Gros levier marketing.

WITH customer_orders AS (
    SELECT c.customer_unique_id,
        o.purchase_timestamp,
        ROW_NUMBER() OVER (
            PARTITION BY c.customer_unique_id
            ORDER BY o.purchase_timestamp
        ) AS order_rank,
        LEAD(o.purchase_timestamp) OVER (
            PARTITION BY c.customer_unique_id
            ORDER BY o.purchase_timestamp
        ) AS next_purchase
    FROM core.orders AS o
    JOIN core.customers AS c ON c.customer_id = o.customer_id
    WHERE o.status NOT IN ('canceled', 'unavailable')
),
first_orders AS (
    SELECT customer_unique_id,
        next_purchase::DATE - purchase_timestamp::DATE AS days_to_second
    FROM customer_orders
    WHERE order_rank = 1
)
SELECT COUNT(*) AS customers,
    COUNT(*) FILTER (WHERE days_to_second IS NOT NULL) AS repeat_customers,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE days_to_second IS NOT NULL)
        / COUNT(*), 2
    ) AS repeat_rate_pct,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days_to_second)
        AS median_days_to_second,
    COUNT(*) FILTER (WHERE days_to_second = 0) AS same_day_second_order
FROM first_orders;
