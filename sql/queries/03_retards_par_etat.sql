-- Titre : Taux de retard de livraison par état
-- Question : Où les commandes arrivent-elles le plus souvent en retard ?
-- Destinataire : Logistique
-- Techniques : jointure, agrégat conditionnel (FILTER), HAVING
-- Note : une commande est en retard si elle est livrée après le jour de
--   livraison estimé annoncé au client. Seules les commandes livrées
--   (avec date de livraison) sont prises en compte. Les états avec moins
--   de 500 commandes sont écartés pour éviter des taux peu fiables.
-- Lecture : les états du Nord-Est (MA, CE, BA) et RJ dépassent 12 % de
--   retards, contre 4,5 % à SP où se trouvent la plupart des vendeurs.

SELECT c.state,
    COUNT(*) AS delivered_orders,
    COUNT(*) FILTER (
        WHERE o.delivered_customer_date::DATE > o.estimated_delivery_date::DATE
    ) AS late_orders,
    ROUND(100.0 * COUNT(*) FILTER (
        WHERE o.delivered_customer_date::DATE > o.estimated_delivery_date::DATE
    ) / COUNT(*), 1) AS late_rate_pct,
    ROUND(AVG(
        o.delivered_customer_date::DATE - o.purchase_timestamp::DATE
    ), 1) AS avg_delivery_days
FROM core.orders AS o
JOIN core.customers AS c ON c.customer_id = o.customer_id
WHERE o.status = 'delivered'
    AND o.delivered_customer_date IS NOT NULL
GROUP BY c.state
HAVING COUNT(*) >= 500
ORDER BY late_rate_pct DESC;
