-- Apply schema.sql first. Browser Supabase roles have no direct access.
revoke all on public.planner_accounts, public.planner_feedback, public.planner_guidance
    from anon, authenticated;
grant select, insert, update on public.planner_accounts, public.planner_feedback, public.planner_guidance
    to service_role;
revoke all on function public.planner_poi_scores(), public.planner_feedback_stats()
    from anon, authenticated;
grant execute on function public.planner_poi_scores(), public.planner_feedback_stats() to service_role;
