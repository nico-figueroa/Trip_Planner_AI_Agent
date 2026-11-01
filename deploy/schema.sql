-- Common schema: apply as a migration administrator before backend-specific grants.
create table if not exists public.planner_accounts (
    owner text primary key check (owner ~ '^[a-f0-9]{64}$'),
    state jsonb not null default '{}'::jsonb
);
create table if not exists public.planner_feedback (
    id uuid primary key default gen_random_uuid(),
    actor text not null,
    plan_id text not null,
    poi_id text not null default '',
    rating text not null check (rating in ('positive', 'negative')),
    comment text not null default '' check (length(comment) <= 2000),
    created_at timestamptz not null default now(),
    unique (actor, plan_id, poi_id)
);
create table if not exists public.planner_guidance (
    id uuid primary key default gen_random_uuid(),
    feedback_id uuid unique not null references public.planner_feedback(id),
    instruction text not null default '' check (length(instruction) <= 300),
    reason text not null check (length(reason) <= 600),
    status text not null check (status in ('pending', 'approved', 'rejected')),
    reviewer text,
    created_at timestamptz not null default now(),
    check (status <> 'approved' or (reviewer is not null and instruction <> ''))
);
alter table public.planner_accounts enable row level security;
alter table public.planner_feedback enable row level security;
alter table public.planner_guidance enable row level security;
revoke all on public.planner_accounts, public.planner_feedback, public.planner_guidance from public;

create or replace function public.planner_poi_scores()
returns table(poi_id text, boost numeric)
language sql stable security invoker set search_path = public
as $$
    select votes.poi_id, sum(case rating when 'positive' then 0.25 else -0.35 end)
    from (
        select distinct on (actor, poi_id) actor, poi_id, rating
        from public.planner_feedback where poi_id <> ''
        order by actor, poi_id, created_at desc, id
    ) votes group by votes.poi_id
$$;
create or replace function public.planner_feedback_stats()
returns table(total bigint, positive bigint, negative bigint)
language sql stable security invoker set search_path = public
as $$
    select count(*), count(*) filter (where rating = 'positive'),
        count(*) filter (where rating = 'negative')
    from public.planner_feedback
$$;
revoke all on function public.planner_poi_scores(), public.planner_feedback_stats() from public;
