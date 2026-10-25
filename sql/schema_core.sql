-- Couche CORE : modèle relationnel typé (MLD) avec clés primaires et
-- étrangères. Alimentée uniquement depuis RAW par sql/transform_core.sql.
--
-- MLD :
--   customers(customer_id PK, customer_unique_id, zip_code_prefix, city,
--             state)
--   geolocation(zip_code_prefix PK, lat, lng, city, state)
--   categories(category_name PK, category_name_english)
--   products(product_id PK, category_name FK -> categories, ...)
--   sellers(seller_id PK, zip_code_prefix, city, state)
--   orders(order_id PK, customer_id FK -> customers, status, dates...)
--   order_items(order_id FK, order_item_id, product_id FK, seller_id FK)
--       PK (order_id, order_item_id)
--   order_payments(order_id FK, payment_sequential, ...)
--       PK (order_id, payment_sequential)
--   order_reviews(review_id, order_id FK, ...) PK (review_id, order_id)
--
-- Les codes postaux clients/vendeurs ne sont pas tous présents dans
-- geolocation : on ne pose donc pas de FK vers geolocation, la jointure se
-- fait en LEFT JOIN.

CREATE SCHEMA IF NOT EXISTS core;

CREATE TABLE IF NOT EXISTS core.customers (
    customer_id        CHAR(32) PRIMARY KEY,
    customer_unique_id CHAR(32) NOT NULL,
    zip_code_prefix    CHAR(5)  NOT NULL,
    city               TEXT     NOT NULL,
    state              CHAR(2)  NOT NULL
);

CREATE TABLE IF NOT EXISTS core.geolocation (
    zip_code_prefix CHAR(5) PRIMARY KEY,
    lat             DOUBLE PRECISION NOT NULL,
    lng             DOUBLE PRECISION NOT NULL,
    city            TEXT    NOT NULL,
    state           CHAR(2) NOT NULL
);

CREATE TABLE IF NOT EXISTS core.categories (
    category_name         TEXT PRIMARY KEY,
    category_name_english TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS core.products (
    product_id          CHAR(32) PRIMARY KEY,
    category_name       TEXT REFERENCES core.categories (category_name),
    name_length         INTEGER,
    description_length  INTEGER,
    photos_qty          INTEGER,
    weight_g            INTEGER,
    length_cm           INTEGER,
    height_cm           INTEGER,
    width_cm            INTEGER
);

CREATE TABLE IF NOT EXISTS core.sellers (
    seller_id       CHAR(32) PRIMARY KEY,
    zip_code_prefix CHAR(5)  NOT NULL,
    city            TEXT     NOT NULL,
    state           CHAR(2)  NOT NULL
);

CREATE TABLE IF NOT EXISTS core.orders (
    order_id                CHAR(32) PRIMARY KEY,
    customer_id             CHAR(32) NOT NULL
        REFERENCES core.customers (customer_id),
    status                  TEXT      NOT NULL,
    purchase_timestamp      TIMESTAMP NOT NULL,
    approved_at             TIMESTAMP,
    delivered_carrier_date  TIMESTAMP,
    delivered_customer_date TIMESTAMP,
    estimated_delivery_date TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS core.order_items (
    order_id            CHAR(32) REFERENCES core.orders (order_id),
    order_item_id       INTEGER,
    product_id          CHAR(32) NOT NULL
        REFERENCES core.products (product_id),
    seller_id           CHAR(32) NOT NULL
        REFERENCES core.sellers (seller_id),
    shipping_limit_date TIMESTAMP NOT NULL,
    price               NUMERIC(10, 2) NOT NULL,
    freight_value       NUMERIC(10, 2) NOT NULL,
    PRIMARY KEY (order_id, order_item_id)
);

CREATE TABLE IF NOT EXISTS core.order_payments (
    order_id             CHAR(32) REFERENCES core.orders (order_id),
    payment_sequential   INTEGER,
    payment_type         TEXT    NOT NULL,
    payment_installments INTEGER NOT NULL,
    payment_value        NUMERIC(10, 2) NOT NULL,
    PRIMARY KEY (order_id, payment_sequential)
);

CREATE TABLE IF NOT EXISTS core.order_reviews (
    review_id         CHAR(32),
    order_id          CHAR(32) REFERENCES core.orders (order_id),
    score             SMALLINT  NOT NULL CHECK (score BETWEEN 1 AND 5),
    comment_title     TEXT,
    comment_message   TEXT,
    creation_date     TIMESTAMP NOT NULL,
    answer_timestamp  TIMESTAMP,
    PRIMARY KEY (review_id, order_id)
);
