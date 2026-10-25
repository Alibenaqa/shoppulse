-- Titre : Retard selon la distance client-vendeur
-- Question : La distance entre le client et le vendeur explique-t-elle
--   les retards ? (piste de variable pour le modèle de retard)
-- Destinataire : Logistique, équipe data
-- Techniques : jointure multiple (6 tables dont 2 fois geolocation),
--   formule de haversine, CASE pour les tranches, agrégat
-- Note : distance à vol d'oiseau entre les centres des codes postaux, en km,
--   calculée sur le premier article de chaque commande.
-- Lecture : le taux de retard triple avec la distance (4,4 % sous
--   100 km, 12 % au-delà de 2 000 km) : variable à garder pour le modèle.

WITH order_distance AS (
    SELECT o.order_id,
        o.delivered_customer_date::DATE > o.estimated_delivery_date::DATE
            AS is_late,
        2 * 6371 * ASIN(SQRT(
            POWER(SIN(RADIANS(gs.lat - gc.lat) / 2), 2)
            + COS(RADIANS(gc.lat)) * COS(RADIANS(gs.lat))
            * POWER(SIN(RADIANS(gs.lng - gc.lng) / 2), 2)
        )) AS distance_km
    FROM core.orders AS o
    JOIN core.customers AS c ON c.customer_id = o.customer_id
    JOIN core.order_items AS i
        ON i.order_id = o.order_id AND i.order_item_id = 1
    JOIN core.sellers AS s ON s.seller_id = i.seller_id
    JOIN core.geolocation AS gc ON gc.zip_code_prefix = c.zip_code_prefix
    JOIN core.geolocation AS gs ON gs.zip_code_prefix = s.zip_code_prefix
    WHERE o.status = 'delivered'
        AND o.delivered_customer_date IS NOT NULL
)
SELECT CASE
        WHEN distance_km < 100 THEN '1. < 100 km'
        WHEN distance_km < 500 THEN '2. 100-500 km'
        WHEN distance_km < 1000 THEN '3. 500-1000 km'
        WHEN distance_km < 2000 THEN '4. 1000-2000 km'
        ELSE '5. >= 2000 km'
    END AS distance_band,
    COUNT(*) AS orders,
    ROUND(AVG(distance_km)::NUMERIC, 0) AS avg_distance_km,
    ROUND(100.0 * AVG(is_late::INT), 1) AS late_rate_pct
FROM order_distance
GROUP BY 1
ORDER BY 1;
