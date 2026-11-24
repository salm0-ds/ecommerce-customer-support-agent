-- Run once in the Supabase SQL editor on an existing database (created from the old schema.sql).
-- Removes product columns nothing uses any more. Then run `python seed_products.py`
-- so the search text and embeddings are rebuilt from the remaining fields.

alter table products
  drop column if exists slug,
  drop column if exists compare_at_price,
  drop column if exists images,
  drop column if exists tags,
  drop column if exists ingredients,
  drop column if exists subscription_available,
  drop column if exists subscription_discount,
  drop column if exists serving_size,
  drop column if exists certifications;
