-- OndeParei: marcações por conta (fase 2b).
-- Rodar uma única vez no SQL Editor do painel do Supabase (veja o README).
-- Cada pessoa só lê e grava as próprias linhas (RLS com auth.uid()).

create table public.series_tracking (
    user_id     uuid not null default auth.uid() references auth.users (id) on delete cascade,
    tmdb_id     integer not null,
    status      text check (status in ('want', 'watching', 'watched')),  -- null = sem status
    favorite    boolean not null default false,
    name        text not null,
    poster_path text,
    updated_at  timestamptz not null default now(),
    primary key (user_id, tmdb_id)
);

create table public.watched_episodes (
    user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
    tmdb_id    integer not null,
    season     integer not null,
    episode    integer not null,
    watched_at timestamptz not null default now(),
    runtime    integer,  -- minutos; null = ainda não conhecida
    primary key (user_id, tmdb_id, season, episode)
);

alter table public.series_tracking enable row level security;
alter table public.watched_episodes enable row level security;

create policy "cada um com as suas" on public.series_tracking
    for all to authenticated
    using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy "cada um com os seus" on public.watched_episodes
    for all to authenticated
    using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

revoke all on public.series_tracking, public.watched_episodes from anon;
grant select, insert, update, delete on public.series_tracking, public.watched_episodes to authenticated;


-- Uma ação inteira (episódios, status, favorito e snapshot) numa transação só.
create or replace function public.save_tracking(
    p_tmdb_id integer, p_name text, p_poster_path text, p_status text, p_favorite boolean,
    p_add jsonb default '[]'::jsonb, p_remove jsonb default '[]'::jsonb
) returns void
language plpgsql security invoker set search_path = ''
as $$
declare
    uid uuid := auth.uid();
begin
    if uid is null then
        raise exception 'sem sessão' using errcode = '28000';
    end if;

    insert into public.watched_episodes (user_id, tmdb_id, season, episode, runtime)
    select uid, p_tmdb_id, (e ->> 'season')::integer, (e ->> 'episode')::integer, (e ->> 'runtime')::integer
    from jsonb_array_elements(coalesce(p_add, '[]'::jsonb)) as e
    on conflict do nothing;

    delete from public.watched_episodes as w
    using jsonb_array_elements(coalesce(p_remove, '[]'::jsonb)) as e
    where w.user_id = uid and w.tmdb_id = p_tmdb_id
      and w.season = (e ->> 'season')::integer and w.episode = (e ->> 'episode')::integer;

    insert into public.series_tracking (user_id, tmdb_id, status, favorite, name, poster_path, updated_at)
    values (uid, p_tmdb_id, p_status, p_favorite, p_name, p_poster_path, now())
    on conflict (user_id, tmdb_id) do update
        set status = excluded.status, favorite = excluded.favorite, name = excluded.name,
            poster_path = excluded.poster_path, updated_at = excluded.updated_at;

    -- sem status, sem favorito e sem episódios: a linha some
    delete from public.series_tracking as s
    where s.user_id = uid and s.tmdb_id = p_tmdb_id and s.status is null and not s.favorite
      and not exists (select 1 from public.watched_episodes as w where w.user_id = uid and w.tmdb_id = p_tmdb_id);
end;
$$;

create or replace function public.tracking_counts() returns json
language sql stable security invoker set search_path = ''
as $$
    select json_build_object(
        'watching', count(*) filter (where status = 'watching'),
        'want', count(*) filter (where status = 'want'),
        'watched', count(*) filter (where status = 'watched'),
        'favorite', count(*) filter (where favorite))
    from public.series_tracking
    where user_id = (select auth.uid());
$$;

create or replace function public.watch_time() returns json
language sql stable security invoker set search_path = ''
as $$
    select json_build_object('episodes', count(*), 'minutes', coalesce(sum(runtime), 0))
    from public.watched_episodes
    where user_id = (select auth.uid());
$$;

create or replace function public.missing_runtimes() returns json
language sql stable security invoker set search_path = ''
as $$
    select coalesce(json_agg(json_build_object('tmdb_id', t.tmdb_id, 'season', t.season)), '[]'::json)
    from (select distinct tmdb_id, season
          from public.watched_episodes
          where user_id = (select auth.uid()) and runtime is null) as t;
$$;

-- Só preenche durações ainda desconhecidas.
create or replace function public.set_runtimes(p_tmdb_id integer, p_runtimes jsonb) returns void
language sql security invoker set search_path = ''
as $$
    update public.watched_episodes as w
    set runtime = (e ->> 'runtime')::integer
    from jsonb_array_elements(coalesce(p_runtimes, '[]'::jsonb)) as e
    where w.user_id = (select auth.uid()) and w.tmdb_id = p_tmdb_id and w.runtime is null
      and w.season = (e ->> 'season')::integer and w.episode = (e ->> 'episode')::integer;
$$;

revoke execute on function public.save_tracking(integer, text, text, text, boolean, jsonb, jsonb),
    public.tracking_counts(), public.watch_time(), public.missing_runtimes(), public.set_runtimes(integer, jsonb)
    from public, anon;
grant execute on function public.save_tracking(integer, text, text, text, boolean, jsonb, jsonb),
    public.tracking_counts(), public.watch_time(), public.missing_runtimes(), public.set_runtimes(integer, jsonb)
    to authenticated;
