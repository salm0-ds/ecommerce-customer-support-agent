-- Run this once in the Supabase SQL editor.
-- Creates: products, reviews, conversations and messages.

-- ---------------------------------------------------------------
-- Products
-- ---------------------------------------------------------------
create table if not exists products (
  id                text primary key,
  name              text not null,
  category          text not null,           -- sleep | gut-health | focus | energy | stress | hydration
  short_description text not null default '', -- one-line tagline shown on the card
  description       text not null default '', -- longer text, read by the AI to pick products
  benefits          text[] not null default '{}',
  price             numeric(10, 2) not null,
  servings          int,
  -- Display values shown on the product cards, set in products_seed.json.
  rating            numeric(2, 1) not null default 0,
  review_count      int not null default 0,
  in_stock          boolean not null default true
);

-- ---------------------------------------------------------------
-- Reviews (one row per customer review, read by the backend)
-- Independent of products.rating / review_count, which are display values.
-- ---------------------------------------------------------------
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

-- ---------------------------------------------------------------
-- Conversations + messages (agent memory)
-- ---------------------------------------------------------------
create table if not exists conversations (
  id         uuid primary key default gen_random_uuid(),
  -- shown_product_ids: excluded from new searches so the user always sees new options
  state      jsonb not null default '{"shown_product_ids": []}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists messages (
  id              bigint generated always as identity primary key,
  conversation_id uuid not null references conversations (id) on delete cascade,
  role            text not null,   -- human | ai | tool
  content         jsonb not null,  -- full LangChain message (text, tool calls, tool results)
  created_at      timestamptz not null default now()
);

create index if not exists messages_conversation_idx on messages (conversation_id, id);

-- ---------------------------------------------------------------
-- Security: the backend uses the service_role key, which bypasses RLS.
-- With RLS on and no policies, the public anon key cannot read chats.
-- Products are readable by anyone (it's a public catalog).
-- ---------------------------------------------------------------
alter table products      enable row level security;
alter table conversations enable row level security;
alter table messages      enable row level security;
alter table reviews       enable row level security;

drop policy if exists "Products are public" on products;
create policy "Products are public" on products for select using (true);

-- Reviews are readable by anyone. Only the backend (service_role) can write them.
drop policy if exists "Reviews are public" on reviews;
create policy "Reviews are public" on reviews for select using (true);
