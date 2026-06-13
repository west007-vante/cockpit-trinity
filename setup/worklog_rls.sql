-- ============================================================
-- Worklog write-path — deixa o hook do Claude Code dos sócios reportar trabalho
-- no cockpit com a chave PÚBLICA (anon), sem service key na máquina deles.
--
-- Por quê uma FUNÇÃO em vez de policy de INSERT/UPDATE pra anon:
--   • a chave anon é pública (está no index.html) → NÃO pode poder LER a tabela
--     (vazaria títulos/prompts/paths de todo mundo);
--   • mas pra dar UPDATE o Postgres precisa "enxergar" a linha (policy de SELECT),
--     que é authenticated-only → anon não conseguiria atualizar.
--   Saída: uma função SECURITY DEFINER que a anon só EXECUTA. Ela valida o owner e
--   faz o upsert + o evento por dentro (furando o RLS de forma escopada). anon não
--   toca nas tabelas direto. Leitura segue só pra authenticated (cockpit logado lê).
--
-- Aplicar: Supabase Dashboard -> SQL Editor -> cola tudo -> Run.
--   (ou: cd ~/Dev/steve-backend && node _cockpit_worklog_rls.js)
-- ============================================================

-- remove qualquer acesso direto da anon às tabelas (versões antigas desta migração)
drop policy if exists worklog_anon_insert on public.work_sessions;
drop policy if exists worklog_anon_update on public.work_sessions;
drop policy if exists worklog_anon_event  on public.cockpit_events;

create or replace function public.worklog_report(
  p_owner   text,
  p_db_sid  text,
  p_status  text  default null,
  p_title   text  default null,
  p_host    text  default null,
  p_cwd     text  default null,
  p_files   jsonb default '[]'::jsonb,
  p_tools   jsonb default '{}'::jsonb,
  p_summary text  default null,
  p_event   text  default null
) returns void
language plpgsql
security definer
set search_path = public
as $fn$
begin
  if p_owner not in ('steve','goggins','rico') then
    raise exception 'worklog: owner invalido %', p_owner;
  end if;

  if exists (select 1 from work_sessions where session_id = p_db_sid) then
    update work_sessions set
      status     = coalesce(p_status, status),
      title      = coalesce(p_title, title),
      summary    = coalesce(p_summary, summary),
      files      = p_files,
      tools      = p_tools,
      updated_at = now()
    where session_id = p_db_sid;
  else
    insert into work_sessions(owner, host, session_id, title, status, cwd, files, tools, updated_at)
    values (p_owner, p_host, p_db_sid, p_title, coalesce(p_status,'fazendo'), p_cwd, p_files, p_tools, now());
  end if;

  if p_event is not null then
    insert into cockpit_events(agent_id, kind, message) values (p_owner, 'done', p_event);
  end if;
end;
$fn$;

revoke all on function public.worklog_report(text,text,text,text,text,text,jsonb,jsonb,text,text) from public;
grant execute on function public.worklog_report(text,text,text,text,text,text,jsonb,jsonb,text,text) to anon, authenticated, service_role;
