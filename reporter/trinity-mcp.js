#!/usr/bin/env node
/* ─────────────────────────────────────────────────────────────────────
   TRINITY REPORTER — servidor MCP (stdio) que conecta TEU agente ao
   Cockpit Trinity. Roda na tua máquina (M1), junto do Claude Code CLI.

   Env obrigatórias:
     TRINITY_SUPABASE_URL   → URL do projeto (o Pyerri passa)
     TRINITY_SERVICE_KEY    → chave service (o Pyerri passa EM PRIVADO — nunca commitar)
     TRINITY_OWNER          → quem é você: steve | goggins | rico

   Instalação (1 comando):
     claude mcp add trinity \
       -e TRINITY_SUPABASE_URL=<url> -e TRINITY_SERVICE_KEY=<chave> -e TRINITY_OWNER=goggins \
       -- node ~/trinity-mcp.js

   Depois é só falar pro teu Claude: "registra o agente DESIGNER no Trinity"
   e ele aparece AO VIVO na aba Agentes do cockpit.
   ───────────────────────────────────────────────────────────────────── */
'use strict';
const BASE = (process.env.TRINITY_SUPABASE_URL || '').replace(/\/$/, '');
const KEY = process.env.TRINITY_SERVICE_KEY || '';
const OWNER = (process.env.TRINITY_OWNER || 'steve').toLowerCase();
if (!BASE || !KEY) { console.error('trinity-mcp: faltam TRINITY_SUPABASE_URL / TRINITY_SERVICE_KEY'); process.exit(1); }

async function db(path, method = 'GET', body, prefer) {
  const headers = { apikey: KEY, Authorization: 'Bearer ' + KEY, 'Content-Type': 'application/json' };
  if (prefer) headers.Prefer = prefer;
  const r = await fetch(BASE + '/rest/v1/' + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  const t = await r.text(); let data; try { data = JSON.parse(t); } catch { data = t; }
  return { http: r.status, data };
}
const now = () => new Date().toISOString();

const TOOLS = [
  { name: 'trinity_register', description: 'Registra teu agente no cockpit (rode 1x no início da sessão). Ele aparece na aba Agentes na hora.',
    inputSchema: { type: 'object', properties: { id: { type: 'string', description: '