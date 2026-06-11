#!/bin/bash
# Conecta o STEVE (founder/orquestradora-mãe) ao Cockpit Trinity via o conector MCP.
# Lê a service key do .env do backend em runtime (nunca copia a chave pra disco).
cd "$HOME/Dev/cockpit-trinity/mcp" || exit 1
ENVF="$HOME/Dev/steve-backend/.env"
export TRINITY_URL=$(grep -E '^(SUPABASE_URL|NEXT_PUBLIC_SUPABASE_URL)=' "$ENVF" | head -1 | cut -d= -f2- | tr -d '"' | tr -d '\r')
export TRINITY_SERVICE_KEY=$(grep -E 'SUPABASE_SERVICE' "$ENVF" | head -1 | cut -d= -f2- | tr -d '"' | tr -d '\r')
export TRINITY_AGENT_ID=steve
export TRINITY_OWNER=steve
export TRINITY_AGENT_NAME=Steve
export TRINITY_AGENT_ROLE="Fundador · Orquestradora-Mãe"
exec /usr/bin/python3 trinity_agent.py --beat
