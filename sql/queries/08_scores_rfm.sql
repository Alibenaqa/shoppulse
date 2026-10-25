-- Titre : Scores RFM des clients (base de la segmentation)
-- Question : Comment se répartissent les clients selon la récence, la
--   fréquence et le montant de leurs achats ?
-- Destinataire : Marketing
-- Techniques : jointure multiple, agrégats, fonction de fenêtre NTILE(5)
-- Note : date de référence = lendemain du dernier achat du jeu de données.
--   R et M sont notés de 1 (faible) à 5 (fort) par quintiles. La fréquence
--   est trop concentrée (97 % des clients n'ont qu'une commande) pour des
--   quintiles : F vaut 1 pour une commande, 2 pour deux, 3 au-delà.
--   Le résultat présente le volume et la valeur de chaque combinaison R-F.
-- Lecture : 97 % des clients n'ont commandé qu'une fois (F = 1) ; les
--   multi-acheteurs dépensent 2 à 4 fois plus et sont la cible fidélité.

WITH reference AS (
    SELECT MAX(purchase_timestamp)::DATE + 1 AS ref_date FROM core.orders
),
customer_rfm AS (
    SELECT c.customer_unique_id,
        (SELECT ref_date FROM reference)
            - MAX(o.purchase_timestamp)::DATE AS recency_days,
        COUNT(DISTINCT o.order_id) AS frequency,
        SUM(p.payment_value) AS monetary
    FROM core.orders AS o
    JOIN core.customers AS c ON c.customer_id = o.customer_id
    JOIN core.order_payments AS p ON p.order_id = o.order_id
    WHERE o.status NOT IN ('canceled', 'unavailable')
    GROUP BY c.customer_unique_id
),
scored AS (
    SELECT *,
        NTILE(5) OVER (ORDER BY recency_days DESC) AS r_score,
        LEAST(frequency, 3) AS f_score,
        NTILE(5) OVER (ORDER BY monetary) AS m_score
    FROM customer_rfm
)
SELECT r_score,
    f_score,
    COUNT(*) AS customers,
    ROUND(AVG(recency_days), 0) AS avg_recency_days,
    ROUND(AVG(monetary), 2) AS avg_monetary,
    ROUND(AVG(m_score), 2) AS avg_m_score
FROM scored
GROUP BY r_score, f_score
ORDER BY r_score DESC, f_score DESC;
