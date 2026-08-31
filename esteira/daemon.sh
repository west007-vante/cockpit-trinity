#!/bin/bash
# A ESTEIRA — ligar, desligar, espiar e PARAR TUDO.
#   ./daemon.sh servidor | parar-servidor | parar-tudo | soltar-freio | estado | diario
CASA="$HOME/esteira"
PORTA=7717
PID="$CASA/.servidor.pid"
PLIST="$HOME/Library/LaunchAgents/com.pyerri.esteira.plist"
ROTULO="com.pyerri.esteira"

case "${1:-estado}" in
  # LaunchAgent, não "nohup &": processo solto morre quando a máquina reinicia
  # e não volta. Com launchd, ele sobe sozinho no boot (RunAtLoad) e volta se
  # cair (KeepAlive) — igual ao daemon do Quadro da Obra.
  servidor)
    mkdir -p ~/Library/LaunchAgents
    cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$ROTULO</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/python3</string><string>$CASA/servidor.py</string>
    <string>--porta</string><string>$PORTA</string></array>
  <key>WorkingDirectory</key><string>$CASA</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$CASA/servidor.log</string>
  <key>StandardErrorPath</key><string>$CASA/servidor.log</string>
</dict></plist>
PLISTEOF
    launchctl unload "$PLIST" 2>/dev/null
    if launchctl load -w "$PLIST"; then
      sleep 1
      echo "✅ no ar → http://127.0.0.1:$PORTA"
      echo "   volta sozinho quando você religar a máquina."
    else
      echo "❌ o launchd recusou. Veja: $CASA/servidor.log"
    fi
    ;;

  parar-servidor)
    launchctl unload -w "$PLIST" 2>/dev/null && echo "⏹ servidor parado (e não volta no boot)" \
      || echo "não estava rodando"
    # libera a porta de QUALQUER coisa — um servidor solto de outra sessão
    # segurando a 7717 faz o launchd falhar em silêncio com "Address already in use"
    pkill -f "esteira/servidor.py" 2>/dev/null && echo "   (matei um servidor solto que sobrou)"
    ocupa=$(lsof -tnP -iTCP:$PORTA -sTCP:LISTEN 2>/dev/null)
    [ -n "$ocupa" ] && kill $ocupa 2>/dev/null && echo "   (liberei a porta $PORTA)"
    rm -f "$PID"
    ;;

  # ── O BOTÃO DE PÂNICO ──────────────────────────────────────────────
  # Não pede confirmação de propósito: quem digita isto está com pressa.
  parar-tudo)
    python3 - <<'PY'
import sys, os
sys.path.insert(0, os.path.expanduser("~/esteira"))
import guarda
p = guarda.puxar_freio("./daemon.sh parar-tudo")
print(f"🛑 FREIO PUXADO ({p})")
print("   Nenhum fluxo roda até você soltar — nem os que já estavam liberados.")
print("   A rodada em curso para no próximo nó.")
PY
    pkill -f "esteira/motor.py" 2>/dev/null && echo "   (matei o motor que estava rodando)"
    echo "   Pra voltar:  ./daemon.sh soltar-freio"
    ;;

  soltar-freio)
    python3 - <<'PY'
import sys, os
sys.path.insert(0, os.path.expanduser("~/esteira"))
import guarda
print("✅ freio solto — os fluxos voltam a poder rodar" if guarda.soltar_freio()
      else "o freio já estava solto")
PY
    ;;

  estado)
    if launchctl list 2>/dev/null | grep -q "$ROTULO"; then
      echo "🟢 servidor no ar → http://127.0.0.1:$PORTA  (volta sozinho no boot)"
    else
      echo "⚪️ servidor parado — ligue com: ./daemon.sh servidor"
    fi
    python3 - <<'PY'
import sys, os, json, glob
sys.path.insert(0, os.path.expanduser("~/esteira"))
import guarda
if guarda.panico_ligado():
    try:
        d = json.load(open(guarda.PANICO, encoding="utf-8"))
        print(f"🛑 FREIO PUXADO desde {d['quando']} ({d['motivo']})")
    except Exception:
        print("🛑 FREIO PUXADO")
else:
    print("freio: solto")
casa = os.path.expanduser("~/esteira")
fs = sorted(glob.glob(os.path.join(casa, "fluxos", "*.json")))
print(f"\nfluxos ({len(fs)}):")
for f in fs:
    try:
        d = json.load(open(f, encoding="utf-8"))
        estado = "🎭 ensaio" if guarda.em_ensaio(d) else "▶️  SOLTO"
        print(f"  {estado}  {d.get('nome', '?'):22s} {len(d.get('nos', []))} nós")
    except Exception as e:
        print(f"  ⚠️  {os.path.basename(f)}: {e}")
ex = sorted(glob.glob(os.path.join(casa, "execucoes", "*.jsonl")))[-3:]
if ex:
    print("\núltimas rodadas:")
    for e in ex:
        print("  " + os.path.basename(e).replace(".jsonl", ""))
PY
    ;;

  diario)
    ultimo=$(ls -t "$CASA"/execucoes/*.jsonl 2>/dev/null | head -1)
    [ -z "$ultimo" ] && echo "nenhuma rodada ainda" && exit 0
    echo "── $(basename "$ultimo") ──"
    python3 -c "
import json,sys
for ln in open(sys.argv[1],encoding='utf-8'):
    r=json.loads(ln); ev=r.get('evento')
    if ev=='rodada':   print(f\"  {r['quando']} · {r['fluxo']} · {r['modo']}\")
    elif ev=='começou':print(f\"  ▸ {r['titulo']}\")
    elif ev=='terminou':print(f\"    {'✅' if r.get('ok') else '❌'} {(r.get('saida') or '')[:150]}\")
    elif ev=='pulou':  print(f\"    ⤵︎ pulou {r['no']}\")
    elif ev=='gate':   print(f\"    🔴 {r.get('saida')}\")
    elif ev=='parado': print(f\"    🛑 {r['motivo']}\")
    elif ev=='fim':    print(f\"  ── {r['nos_executados']} nó(s)\")
" "$ultimo"
    ;;

  *) echo "uso: ./daemon.sh servidor | parar-servidor | parar-tudo | soltar-freio | estado | diario" ;;
esac
