#!/bin/bash
# A PONTE DO MAESTRI — cole este comando num terminal DENTRO do Maestri:
#
#     bash ~/esteira/maestri-ponte.sh
#
# Por que assim: o CLI `maestri` só funciona de dentro dos terminais do app
# (socket + identidade injetados). Esta ponte fica DENTRO, lendo a fila que a
# ESTEIRA escreve, executando os comandos e devolvendo as respostas.
# A partir do primeiro terminal, o `recruit` cria os outros — só a semente é manual.
FILA="$HOME/esteira/.maestri-fila"
VIVA="$FILA/.ponte-viva"
mkdir -p "$FILA"
if ! command -v maestri >/dev/null && [ -z "$MAESTRI_CLI" ]; then
  echo "❌ isto não é um terminal do Maestri — abra o app, crie um terminal e rode lá."
  exit 1
fi
M="${MAESTRI_CLI:-maestri}"
echo "🟢 ponte da ESTEIRA de pé — deixe este terminal aberto."
while true; do
  date +%s > "$VIVA"
  for cmd in "$FILA"/*.cmd; do
    [ -e "$cmd" ] || continue
    id=$(basename "$cmd" .cmd)
    # o arquivo .cmd tem UMA linha: os argumentos pro maestri (já com aspas)
    linha=$(cat "$cmd")
    echo "▸ maestri $linha"
    eval "\"$M\" $linha" > "$FILA/$id.out" 2>&1
    echo $? > "$FILA/$id.rc"
    rm -f "$cmd"
    mv "$FILA/$id.out" "$FILA/$id.done"
  done
  sleep 2
done
