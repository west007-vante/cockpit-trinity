#!/bin/bash
# Um ciclo do quadro: consome a fila, agenda o que falta, espelha de volta.
# Chamado pelo LaunchAgent a cada 10 min — e dá pra rodar na mão sem medo.
cd "$(dirname "$0")" || exit 0
export TRELLO_ASSINATURA="robô-do-quadro"   # todo card/comentário deste ciclo sai carimbado
LOG=~/.steve/quadro.log
exec >>"$LOG" 2>&1
echo "──── $(date '+%d/%m %H:%M:%S') ────"
python3 roteador.py            || echo "⚠️ roteador falhou"
python3 agendador.py           || echo "⚠️ agendador falhou"
python3 espelho_quadro.py      || echo "⚠️ espelho falhou"
# o log não pode crescer pra sempre
[ "$(wc -l <"$LOG" 2>/dev/null || echo 0)" -gt 4000 ] && tail -1500 "$LOG" >"$LOG.tmp" && mv "$LOG.tmp" "$LOG"
exit 0
