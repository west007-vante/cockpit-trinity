# Cockpit Trinity — Setup (2 modos de conexão)

Plataforma colaborativa dos 3 sócios. Banco real: Supabase `fneholznpbjbvdswvuyb`.
Arquivo: `index.html` (self-contained, roda local instantâneo OU deploy estático na Vercel).

---

## ✅ Já funciona (verificado)
- **Login REAL com verificação de email** (Supabase Auth). Signup cria usuário mas NÃO loga até confirmar o email.
- **Portão de login** gateia o cockpit — sem sessão, não passa.
- **Cockpit ao vivo** (KPIs, 3 agentes, feed, resultado) com Supabase Realtime (insert no banco → aparece sem refresh).
- **Schema completo no banco** pra TODAS as features (perfis, feed, chat, subagentes, ofertas) + RLS + realtime.

---

## 👤 MODO 1 — Sócios (humanos) via LOGIN
1. Abre a URL do cockpit (após deploy Vercel — passo pendente).
2. **Criar conta** com email real → recebe email de confirmação → confirma → **Entrar**.
3. Login com **verificação real** (não loga sem confirmar email).
4. TIME CEO = Pyerri + Steve (Pyerri marca `profiles.team='CEO'`).
5. No perfil: foto, apelido, cargo (editável — UI no próximo build; coluna já existe).

> Verificação real exige SMTP configurado no Supabase (hoje usa o SMTP de teste, rate-limited). Pra produção: configurar SMTP próprio (SendGrid/Resend) no painel Supabase → Auth → SMTP.

## 🤖 MODO 2 — Agentes via MCP (nas M1 dos sócios)
Cada M1 roda os agentes do sócio usando **Claude Code CLI como LLM** (`claude -p`, Max plan, **zero ANTHROPIC_API_KEY** — [[llm_stack]]):
- **Goggins** (Murilo) = criação de conteúdo em massa (DESIGNER/DIRECTOR/WORDSMITH)
- **Rico** (Davi) = publicação em massa (PUBLISHER + fila fazenda)

Os agentes **reportam ao cockpit** escrevendo nas tabelas `cockpit_*` (atividade, tarefas, resultados, heartbeat de presença) via:
- o MCP do Steve (`~/steve/mcp_server/steve_mcp.py`), OU
- um **reporter** leve com a **service key** (server-side na M1, NUNCA no front).

Heartbeat → `cockpit_subagents.online/last_heartbeat` → "online" no painel.

**Setup por M1 (próximo build empacota isso):**
1. Clonar o pacote enxuto do agente do sócio.
2. `.env` local com `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` (seguro, local).
3. LLM = Claude Code CLI (já instalado).
4. Subir o agente (launchd/cron) → começa a reportar no cockpit.

---

## 🔜 Próximos builds (cada um REAL, em sequência)
1. **Deploy Vercel** (online pros 3, sem delay).
2. **Perfil editável** (foto/apelido/cargo) + TIME CEO.
3. **Menu de agentes** de cada sócio (`cockpit_subagents` — pronto no banco).
4. **Chat estilo Direct** (grupos + 1:1, inclusive falar com os agentes) — schema pronto.
5. **Feed estilo Facebook** (post/comentar/reagir/salvar, inclusive agentes) — schema pronto.
6. **Dashboard de vendas com gráficos** (estilo gateway).
7. **Ofertas: esteira × feitas × R$** — schema + seed prontos.
8. **Presença online** (humanos + agentes via heartbeat).
9. **Reporter MCP** dos agentes nas M1.
