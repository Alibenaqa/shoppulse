-- Titre : Top 10 des catégories par chiffre d'affaires
-- Question : Quelles catégories portent le chiffre d'affaires ?
-- Destinataire : Direction, Marketing
-- Techniques : jointure multiple (4 tables), agrégat, fonction de fenêtre
--   SUM() OVER () pour la part du CA total
-- Lecture : aucune catégorie ne dépasse 10 % du CA ; les 10 premières
--   en font environ 62 %. Santé-beauté et montres-cadeaux mènent.

SELECT COALESCE(c.category_name_english, 'unknown') AS category,
    COUNT(DISTINCT o.order_id) AS orders,
    ROUND(SUM(i.price), 0) AS revenue,
    ROUND(100 * SUM(i.price) / SUM(SUM(i.price)) OVER (), 1) AS revenue_share_pct,
    ROUND(AVG(i.price), 2) AS avg_price
FROM core.order_items AS i
JOIN core.orders AS o ON o.order_id = i.order_id
JOIN core.products AS p ON p.product_id = i.product_id
LEFT JOIN core.categories AS c ON c.category_name = p.category_name
WHERE o.status NOT IN ('canceled', 'unavailable')
GROUP BY 1
ORDER BY revenue DESC
LIMIT 10;
