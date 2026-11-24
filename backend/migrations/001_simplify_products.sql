-- Run once in the Supabase SQL editor on an existing database (created from the old schema.sql).
-- Removes product columns nothing uses any more, plus the old hybrid search
-- (search function, search columns and index). Then run `python seed_products.py`.

drop function if exists search_products(text, vector, int, text, numeric, numeric, text[], int);
drop index if exists products_fts_idx;

alter table products
  drop column if exists slug,
  drop column if exists compare_at_price,
  drop column if exists images,
  drop column if exists tags,
  drop column if exists ingredients,
  drop column if exists subscription_available,
  drop column if exists subscription_discount,
  drop column if exists serving_size,
  drop column if exists certifications,
  drop column if exists fts,
  drop column if exists embedding,
  drop column if exists search_text;

-- The vector extension was only used by the search. Remove it unless you use it elsewhere.
drop extension if exists vector;
