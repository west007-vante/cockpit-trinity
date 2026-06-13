-- ============================================================
-- Schema do Classificador + Analista de operação (cockpit).
-- work_sessions ganha a classificação; cockpit_offers ganha progresso/estagio;
-- cockpit_results recebe as métricas-base (o analista atualiza o generated ao vivo).
-- Aplicar: SQL Editor do Supabase, OU node _cockpit_classifier_migrate.js.
-- ============================================================

alter table work_sessions
  add column if not exists relevante boolean,
  add column if not exists categoria text,
  add column if not exists offer_id bigint,
  add column if not exists offer_label text,
  add column if not exists estagio text,
  add column if not exists progresso int,
  add column if not exists confidence int,
  add column if not exists motivo text,
  add column if not exists classified_at timestamptz,
  add column if not exists classifier text;

alter table cockpit_offers
  add column if not exists progresso int default 0,
  add column if not exists estagio text;

create unique index if not exists cockpit_results_metric_uniq on cockpit_results(metric);

-- métricas-base. expected de Criativos/Posts = META editável do time (alvo), não medição.
insert into cockpit_results(metric, generated, expected, unit) values
  ('Progresso das ofertas', 0, 100, ''),
  ('Criativos / dia', 0, 10, ''),
  ('Posts / dia', 0, 10, ''),
  ('Ofertas no roadmap', 0, (select greatest(count(*),1) from cockpit_offers), ''),
  ('Receita gerada', 0, 0, 'R$')
on conflict (metric) do nothing;
