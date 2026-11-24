-- Run once in the Supabase SQL editor on an existing database, after 001.
-- Adds the reviews table. Does not touch products (ratings stay as seeded).

create table if not exists reviews (
  id          bigint generated always as identity primary key,
  product_id  text not null references products (id) on delete cascade,
  author_name text not null,               -- e.g. 'Sarah M.'
  author_role text not null default '',    -- e.g. 'Wellness Creator'
  rating      smallint not null check (rating between 1 and 5),
  title       text not null default '',    -- headline, e.g. 'Sleep quality improved 85%'
  body        text not null default '',    -- the review text
  created_at  timestamptz not null default now(),
  -- One review per person per product; also lets seed_products.py re-run safely.
  unique (product_id, author_name)
);

create index if not exists reviews_product_idx on reviews (product_id, created_at desc);

-- Readable by anyone; only the backend (service_role) can write.
alter table reviews enable row level security;
drop policy if exists "Reviews are public" on reviews;
create policy "Reviews are public" on reviews for select using (true);
