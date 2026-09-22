-- 個人用食事ログのクラウド正本。Supabase SQL Editorで一度だけ実行する。
-- すべての行は auth.uid() と一致する本人だけが読書きできる。

create extension if not exists pgcrypto;

create table if not exists public.meal_items (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
  recorded_at timestamptz not null default now(),
  recorded_date date not null,
  meal_type text not null check (meal_type in ('朝食', '昼食', '夕食', '間食')),
  name text not null check (char_length(name) between 1 and 200),
  energy_kcal numeric(8,1) not null check (energy_kcal >= 0),
  protein_g numeric(8,1) not null check (protein_g >= 0),
  fat_g numeric(8,1) not null check (fat_g >= 0),
  carbohydrate_g numeric(8,1) not null check (carbohydrate_g >= 0),
  sugar_g numeric(8,1) check (sugar_g is null or sugar_g >= 0),
  fiber_g numeric(8,1) check (fiber_g is null or fiber_g >= 0),
  salt_g numeric(8,2) check (salt_g is null or salt_g >= 0),
  source text not null default 'manual' check (source in ('manual', 'favorite', 'ai')),
  assumptions jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.favorites (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
  name text not null check (char_length(name) between 1 and 200),
  meal_type text not null check (meal_type in ('朝食', '昼食', '夕食', '間食')),
  energy_kcal numeric(8,1) not null check (energy_kcal >= 0),
  protein_g numeric(8,1) not null check (protein_g >= 0),
  fat_g numeric(8,1) not null check (fat_g >= 0),
  carbohydrate_g numeric(8,1) not null check (carbohydrate_g >= 0),
  sugar_g numeric(8,1) check (sugar_g is null or sugar_g >= 0),
  fiber_g numeric(8,1) check (fiber_g is null or fiber_g >= 0),
  salt_g numeric(8,2) check (salt_g is null or salt_g >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.nutrition_targets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
  effective_from date not null,
  revision integer not null check (revision > 0),
  energy_kcal numeric(8,1) not null check (energy_kcal > 0),
  protein_g numeric(8,1) not null check (protein_g >= 0),
  fat_g numeric(8,1) not null check (fat_g >= 0),
  carbohydrate_g numeric(8,1) not null check (carbohydrate_g >= 0),
  created_at timestamptz not null default now(),
  unique (user_id, effective_from, revision)
);

create table if not exists public.attachments (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
  meal_item_id uuid not null references public.meal_items(id) on delete cascade,
  storage_path text not null unique,
  mime_type text not null check (mime_type in ('image/jpeg', 'image/png', 'image/webp')),
  byte_size integer not null check (byte_size > 0 and byte_size <= 5242880),
  created_at timestamptz not null default now()
);

create table if not exists public.obsidian_sync_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
  entity_type text not null check (entity_type in ('meal_item', 'favorite', 'nutrition_target')),
  entity_id uuid not null,
  operation text not null check (operation in ('upsert', 'delete')),
  occurred_at timestamptz not null default now(),
  delivered_at timestamptz
);

create index if not exists meal_items_user_date_idx on public.meal_items (user_id, recorded_date desc);
create index if not exists sync_events_pending_idx on public.obsidian_sync_events (user_id, occurred_at) where delivered_at is null;

alter table public.meal_items enable row level security;
alter table public.favorites enable row level security;
alter table public.nutrition_targets enable row level security;
alter table public.attachments enable row level security;
alter table public.obsidian_sync_events enable row level security;

create policy "meal_items_own_rows" on public.meal_items for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "favorites_own_rows" on public.favorites for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "nutrition_targets_own_rows" on public.nutrition_targets for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "attachments_own_rows" on public.attachments for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "sync_events_own_rows" on public.obsidian_sync_events for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create or replace function public.queue_obsidian_sync_event() returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.obsidian_sync_events (user_id, entity_type, entity_id, operation)
  values (coalesce(new.user_id, old.user_id), tg_argv[0], coalesce(new.id, old.id), case when tg_op = 'DELETE' then 'delete' else 'upsert' end);
  return coalesce(new, old);
end;
$$;

drop trigger if exists meal_items_queue_sync on public.meal_items;
create trigger meal_items_queue_sync after insert or update or delete on public.meal_items for each row execute function public.queue_obsidian_sync_event('meal_item');
drop trigger if exists favorites_queue_sync on public.favorites;
create trigger favorites_queue_sync after insert or update or delete on public.favorites for each row execute function public.queue_obsidian_sync_event('favorite');
drop trigger if exists targets_queue_sync on public.nutrition_targets;
create trigger targets_queue_sync after insert or update or delete on public.nutrition_targets for each row execute function public.queue_obsidian_sync_event('nutrition_target');

-- Storage > New bucket で meal-photos を private bucket として作成した後に実行する。
create policy "meal_photos_own_objects" on storage.objects for all to authenticated
using (bucket_id = 'meal-photos' and (storage.foldername(name))[1] = auth.uid()::text)
with check (bucket_id = 'meal-photos' and (storage.foldername(name))[1] = auth.uid()::text);
