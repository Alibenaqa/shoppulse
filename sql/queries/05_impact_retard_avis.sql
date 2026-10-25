-- Titre : Impact du retard sur la note des avis
-- Question : Les retards de livraison dégradent-ils les avis clients ?
-- Destinataire : Service client, Logistique
-- Techniques : jointure, CASE, agrégats (AVG, part des notes 1-2)
-- Note : retard mesuré en jours entre la livraison réelle et la date
--   estimée. Une note de 1 ou 2 étoiles est considérée comme négative.
-- Lecture : à l'heure, la note moyenne est de 4,3 et 9 % d'avis
--   négatifs ; au-delà de 7 jours de retard, 1,7 et 79 % d'avis négatifs.

WITH reviewed AS (
    SELECT r.score,
        o.delivered_customer_date::DATE - o.estimated_delivery_date::DATE
            AS days_late
    FROM core.order_reviews AS r
    JOIN core.orders AS o ON o.order_id = r.order_id
    WHERE o.status = 'delivered'
        AND o.delivered_customer_date IS NOT NULL
)
SELECT CASE
        WHEN days_late <= 0 THEN '1. à l''heure ou en avance'
        WHEN days_late <= 3 THEN '2. 1 à 3 jours de retard'
        WHEN days_late <= 7 THEN '3. 4 à 7 jours de retard'
        ELSE '4. plus de 7 jours de retard'
    END AS delay_band,
    COUNT(*) AS reviews,
    ROUND(AVG(score), 2) AS avg_score,
    ROUND(100.0 * AVG((score <= 2)::INT), 1) AS negative_pct
FROM reviewed
GROUP BY 1
ORDER BY 1;
