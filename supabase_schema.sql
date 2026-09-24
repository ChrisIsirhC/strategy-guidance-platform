-- Run this once in the Supabase SQL editor.
-- The app uses the server-side service-role key; the public policy is kept
-- deliberately narrow so only published cases can ever be read anonymously.

create table if not exists public.strategy_cases (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  strategy text not null,
  manager text not null default '',
  case_date date,
  background text not null default '',
  judgement text not null default '',
  action text not null default '',
  result text not null default '',
  review text not null default '',
  source_date_key text not null default '',
  source_cell text not null default '',
  status text not null default 'draft' check (status in ('draft', 'published')),
  created_by text not null default '',
  updated_by text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  published_at timestamptz
);

create index if not exists strategy_cases_public_idx
  on public.strategy_cases (status, case_date desc, updated_at desc);

alter table public.strategy_cases enable row level security;

drop policy if exists "public can read published cases" on public.strategy_cases;
create policy "public can read published cases"
  on public.strategy_cases for select
  using (status = 'published');
