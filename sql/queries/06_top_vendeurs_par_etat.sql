-- Titre : Top 3 des vendeurs par état
-- Question : Quels vendeurs dominent chaque marché régional ?
-- Destinataire : Direction (relation vendeurs)
-- Techniques : jointure, agrégat, fonctions de fenêtre RANK() et
--   SUM() OVER (PARTITION BY) pour la part du CA de l'état
-- Note : limité aux 5 états qui comptent le plus de vendeurs.
-- Lecture : à SP le marché est très fragmenté (le n°1 pèse 2,6 % du
--   CA de l'état), alors qu'à RJ les 3 premiers en font près de 40 %.

WITH seller_revenue AS (
    SELECT s.state,
        s.seller_id,
        COUNT(DISTINCT i.order_id) AS orders,
        SUM(i.price) AS revenue
    FROM core.order_items AS i
    JOIN core.orders AS o ON o.order_id = i.order_id
    JOIN core.sellers AS s ON s.seller_id = i.seller_id
    WHERE o.status NOT IN ('canceled', 'unavailable')
    GROUP BY s.state, s.seller_id
),
ranked AS (
    SELECT state,
        seller_id,
        orders,
        revenue,
        RANK() OVER (PARTITION BY state ORDER BY revenue DESC)
            AS rank_in_state,
        100 * revenue / SUM(revenue) OVER (PARTITION BY state)
            AS state_share_pct,
        COUNT(*) OVER (PARTITION BY state) AS sellers_in_state
    FROM seller_revenue
)
SELECT state,
    rank_in_state,
    LEFT(seller_id, 8) AS seller,
    orders,
    ROUND(revenue, 0) AS revenue,
    ROUND(state_share_pct, 1) AS state_share_pct
FROM ranked
WHERE rank_in_state <= 3
    AND state IN (
        SELECT state FROM ranked
        GROUP BY state
        ORDER BY MAX(sellers_in_state) DESC
        LIMIT 5
    )
ORDER BY MAX(sellers_in_state) OVER (PARTITION BY state) DESC,
    state, rank_in_state;
