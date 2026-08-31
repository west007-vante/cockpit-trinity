#!/bin/bash
# Liga, desliga e espia o robô do quadro.
#   ./daemon.sh start | stop | status | now | log
PLIST=~/Library/LaunchAgents/com.pyerri.quadro-trello.plist
ROTULO=com.pyerri.quadro-trello
CICLO="$HOME/trinity/trello/ciclo.sh"

case "${1:-status}" in
  start)
    mkdir -p ~/Library/LaunchAgents
    cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$ROTULO</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$CICLO</string></array>
  <key>StartInterval</key><integer>600</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$HOME/.steve/quadro.daemon.log</string>
  <key>StandardErrorPath</key><string>$HOME/.steve/quadro.daemon.log</string>
</dict></plist>
PLISTEOF
    launchctl unload "$PLIST" 2>/dev/null
    launchctl load "$PLIST" && echo "✅ robô do quadro ligado — roda a cada 10 min"
    ;;
  stop)
    launchctl unload "$PLIST" 2>/dev/null && echo "⏹  robô parado (o plist continua em $PLIST)"
    ;;
  status)
    if launchctl list | grep -q "$ROTULO"; then
      echo "🟢 ligado"; launchctl list | grep "$ROTULO"
    else
      echo "⚪️ desligado — ligue com: ./daemon.sh start"
    fi
    echo "--- últimas linhas ---"; tail -12 ~/.steve/quadro.log 2>/dev/null || echo "(sem log ainda)"
    ;;
  now)  bash "$CICLO" && tail -25 ~/.steve/quadro.log ;;
  log)  tail -60 ~/.steve/quadro.log 2>/dev/null || echo "(sem log ainda)" ;;
  *)    echo "uso: ./daemon.sh start|stop|status|now|log" ;;
esac
