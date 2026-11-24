-- Run this once in the Supabase SQL editor.
-- Creates: products (with embeddings + full-text), conversations, messages,
-- and the hybrid search function used by the suggest_products tool.

create extension if not exists vector;

-- ---------------------------------------------------------------
-- Products
-- ---------------------------------------------------------------
create table if not exists products (
  id                     text primary key,
  name                   text not null,
  slug                   text unique not null,
  description            text not null default '',
  short_description      text not null default '',
  price                  numeric(10, 2) not null,
  compare_at_price       numeric(10, 2),
  images                 text[] not null default '{}',
  category               text not null,
  tags                   text[] not null default '{}',
  benefits               text[] not null default '{}',
  ingredients            jsonb not null default '[]',
  rating                 numeric(2, 1) not null default 0,
  review_count           int not null default 0,
  in_stock               boolean not null default true,
  subscription_available boolean not null default false,
  subscription_discount  int not null default 0,
  servings               int,
  serving_size           text,
  certifications         text[] not null default '{}',
  -- Combined text that gets embedded and keyword-searched (built by seed_products.py)
  search_text            text not null default '',
  -- text-embedding-3-small = 1536 dimensions. Change if you change the model.
  embedding              vector(1536),
  fts                    tsvector generated always as (to_tsvector('english', search_text)) stored
);

create index if not exists products_fts_idx on products using gin (fts);
-- No vector index needed for a small catalog (exact search is fast under ~10k rows).

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

drop policy if exists "Products are public" on products;
create policy "Products are public" on products for select using (true);

-- ---------------------------------------------------------------
-- Hybrid search: hard filters -> keyword + vector -> reciprocal rank fusion
-- ---------------------------------------------------------------
create or replace function search_products(
  query_text      text,
  query_embedding vector(1536),
  match_count     int     default 20,
  filter_category text    default null,
  min_price       numeric default null,
  max_price       numeric default null,
  exclude_ids     text[]  default '{}',
  rrf_k           int     default 50
)
returns table (id text, similarity float, score float)
language sql stable
as $$
  with filtered as (
    -- 1. Hard filters: things that must be exact
    select p.*
    from products p
    where p.in_stock
      and (filter_category is null or p.category = filter_category)
      and (min_price is null or p.price >= min_price)
      and (max_price is null or p.price <= max_price)
      and not (p.id = any (exclude_ids))
  ),
  semantic as (
    -- 2a. Vector search: matches meaning ("can't switch off at night" -> sleep)
    select f.id, row_number() over (order by f.embedding <=> query_embedding) as rank
    from filtered f
    where f.embedding is not null
    order by f.embedding <=> query_embedding
    limit match_count
  ),
  keyword as (
    -- 2b. Keyword search: matches exact terms ("magnesium", "ashwagandha").
    -- Words are OR'ed so a long query still matches products containing any of them.
    select f.id,
           row_number() over (
             order by ts_rank_cd(f.fts, websearch_to_tsquery('english', replace(query_text, ' ', ' or '))) desc
           ) as rank
    from filtered f
    where f.fts @@ websearch_to_tsquery('english', replace(query_text, ' ', ' or '))
    order by rank
    limit match_count
  )
  -- 3. Merge both lists. similarity is returned for every row so the app can apply a threshold.
  select p.id,
         1 - (p.embedding <=> query_embedding) as similarity,
         coalesce(1.0 / (rrf_k + s.rank), 0) + coalesce(1.0 / (rrf_k + k.rank), 0) as score
  from semantic s
  full outer join keyword k on s.id = k.id
  join products p on p.id = coalesce(s.id, k.id)
  order by score desc
  limit match_count;
$$;
