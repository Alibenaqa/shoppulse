-- Titre : Chiffre d'affaires mensuel et croissance
-- Question : Comment évolue l'activité mois après mois ?
-- Destinataire : Direction
-- Techniques : agrégat (SUM, COUNT DISTINCT), CTE, fonction de fenêtre LAG
-- Note : CA = prix + frais de port des articles, hors commandes annulées
--   ou indisponibles. Les mois incomplets du début (2016) et de la fin
--   (septembre-octobre 2018) sont exclus.
-- Lecture : l'activité a été multipliée par 8 entre janvier 2017 et
--   2018, avec un pic au Black Friday (novembre 2017, +53 %), puis un
--   plateau autour de 1 M par mois en 2018. Panier moyen stable (~160).

WITH monthly AS (
    SELECT DATE_TRUNC('month', o.purchase_timestamp)::DATE AS month,
        COUNT(DISTINCT o.order_id) AS orders,
        SUM(i.price + i.freight_value) AS revenue
    FROM core.orders AS o
    JOIN core.order_items AS i ON i.order_id = o.order_id
    WHERE o.status NOT IN ('canceled', 'unavailable')
        AND o.purchase_timestamp >= '2017-01-01'
        AND o.purchase_timestamp < '2018-09-01'
    GROUP BY 1
)
SELECT month,
    orders,
    ROUND(revenue, 0) AS revenue,
    ROUND(revenue / orders, 2) AS avg_basket,
    ROUND(
        100 * (revenue - LAG(revenue) OVER (ORDER BY month))
        / LAG(revenue) OVER (ORDER BY month), 1
    ) AS growth_pct
FROM monthly
ORDER BY month;
