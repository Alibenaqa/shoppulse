-- Alimentation de CORE depuis RAW. Rejouable : on vide CORE puis on
-- recharge, le tout dans la même transaction (gérée côté Python).
--
-- Règles de nettoyage appliquées (tracées ici, rapport qualité à venir) :
--   R1 geolocation : plusieurs points par code postal -> une ligne par code
--      postal (moyenne lat/lng, ville et état les plus fréquents).
--   R2 categories  : les catégories présentes dans products mais absentes
--      de la table de traduction sont ajoutées avec leur nom portugais.
--   R3 products    : colonnes "lenght" renommées en "length", casts en
--      entier, catégorie vide -> NULL.
--   R4 order_reviews : doublons (review_id, order_id) -> on garde la
--      réponse la plus récente ; textes vides -> NULL.
--   R5 casts de types (TEXT -> TIMESTAMP / NUMERIC / INTEGER).

TRUNCATE core.order_reviews, core.order_payments, core.order_items,
    core.orders, core.sellers, core.products, core.categories,
    core.geolocation, core.customers;

INSERT INTO core.customers
SELECT customer_id, customer_unique_id, customer_zip_code_prefix,
    customer_city, customer_state
FROM raw.customers;

-- R1
INSERT INTO core.geolocation
SELECT geolocation_zip_code_prefix,
    AVG(geolocation_lat::DOUBLE PRECISION),
    AVG(geolocation_lng::DOUBLE PRECISION),
    MODE() WITHIN GROUP (ORDER BY geolocation_city),
    MODE() WITHIN GROUP (ORDER BY geolocation_state)
FROM raw.geolocation
GROUP BY geolocation_zip_code_prefix;

-- R2
INSERT INTO core.categories
SELECT product_category_name, product_category_name_english
FROM raw.category_translation
UNION
SELECT DISTINCT p.product_category_name, p.product_category_name
FROM raw.products AS p
LEFT JOIN raw.category_translation AS t
    ON t.product_category_name = p.product_category_name
WHERE p.product_category_name IS NOT NULL
    AND t.product_category_name IS NULL;

-- R3
INSERT INTO core.products
SELECT product_id,
    NULLIF(product_category_name, ''),
    product_name_lenght::NUMERIC::INTEGER,
    product_description_lenght::NUMERIC::INTEGER,
    product_photos_qty::NUMERIC::INTEGER,
    product_weight_g::NUMERIC::INTEGER,
    product_length_cm::NUMERIC::INTEGER,
    product_height_cm::NUMERIC::INTEGER,
    product_width_cm::NUMERIC::INTEGER
FROM raw.products;

INSERT INTO core.sellers
SELECT seller_id, seller_zip_code_prefix, seller_city, seller_state
FROM raw.sellers;

INSERT INTO core.orders
SELECT order_id, customer_id, order_status,
    order_purchase_timestamp::TIMESTAMP,
    order_approved_at::TIMESTAMP,
    order_delivered_carrier_date::TIMESTAMP,
    order_delivered_customer_date::TIMESTAMP,
    order_estimated_delivery_date::TIMESTAMP
FROM raw.orders;

INSERT INTO core.order_items
SELECT order_id, order_item_id::INTEGER, product_id, seller_id,
    shipping_limit_date::TIMESTAMP,
    price::NUMERIC, freight_value::NUMERIC
FROM raw.order_items;

INSERT INTO core.order_payments
SELECT order_id, payment_sequential::INTEGER, payment_type,
    payment_installments::INTEGER, payment_value::NUMERIC
FROM raw.order_payments;

-- R4
INSERT INTO core.order_reviews
SELECT DISTINCT ON (review_id, order_id)
    review_id, order_id, review_score::SMALLINT,
    NULLIF(TRIM(review_comment_title), ''),
    NULLIF(TRIM(review_comment_message), ''),
    review_creation_date::TIMESTAMP,
    review_answer_timestamp::TIMESTAMP
FROM raw.order_reviews
ORDER BY review_id, order_id, review_answer_timestamp DESC;
